from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import func, text, cast, Date
from typing import Literal
import logging

from src.payments import models, schemas
from src.payments.dependencies import PaymentQueryParams

logger = logging.getLogger(__name__)

async def process_event(db: AsyncSession, event: schemas.TransactionRequest):

    txn_query = select(models.Transaction).where(
        models.Transaction.id == event.transaction_id
    ).with_for_update()
    
    txn_result = await db.execute(txn_query)
    transaction = txn_result.scalar_one_or_none()

    # Determine status mapping
    if event.event_type == schemas.EventType.PAYMENT_PROCESSED:
        new_status = schemas.PaymentStatus.SUCCESS
    elif event.event_type == schemas.EventType.PAYMENT_FAILED:
        new_status = schemas.PaymentStatus.FAILED
    elif event.event_type == schemas.EventType.PAYMENT_SETTLED:
        new_status = schemas.PaymentStatus.SUCCESS
    else:
        new_status = schemas.PaymentStatus.PENDING

    if not transaction:
        # First time seeing this transaction
        transaction = models.Transaction(
            id=event.transaction_id,
            merchant_id=event.merchant_id,
            amount=event.amount,
            currency=event.currency,
            current_status=new_status,
            last_event_timestamp=event.timestamp
        )
        db.add(transaction)
    else:
        # Only update the transaction state if this event is chronologically newer 
        # than the highest timestamp we have processed so far.
        if event.timestamp > transaction.last_event_timestamp:
            transaction.current_status = new_status
            transaction.last_event_timestamp = event.timestamp
        else:
            logger.info(f"Stale event {event.event_id} ignored due to High-Water Mark.")

    # Event Insertion (Audit Trail)
    event_query = select(models.Event).where(models.Event.id == event.event_id)
    event_result = await db.execute(event_query)
    existing_event = event_result.scalar_one_or_none()

    if not existing_event:
        new_event = models.Event(
            id=event.event_id,
            transaction_id=event.transaction_id,
            event_type=event.event_type,
            timestamp=event.timestamp
        )
        db.add(new_event)

    try:
        await db.commit()
        await db.refresh(transaction)
        return transaction
    except IntegrityError as e:
        await db.rollback()
        if "foreign key constraint" in str(e.orig).lower():
            raise ValueError(f"Merchant ID {event.merchant_id} does not exist in the system.")
        raise ValueError("Failed to ingest payment due to data integrity conflict.")

async def get_transaction_with_events(db: AsyncSession, transaction_id: str):

    query = select(models.Transaction).options(
        selectinload(models.Transaction.events)
    ).where(models.Transaction.id == transaction_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_reconciliation_summary(
    db: AsyncSession, 
    dimension: Literal["merchant", "status", "date"] = "status"
):
    # Map the requested string dimension to the actual SQLAlchemy column expression
    if dimension == "merchant":
        group_col = models.Transaction.merchant_id
    elif dimension == "status":
        group_col = models.Transaction.current_status
    elif dimension == "date":
        # Group by the day the transaction was created in our system
        group_col = cast(models.Transaction.created_at, Date)
    
    # Build the dynamic aggregation query
    query = select(
        group_col.label("dimension_value"),
        func.count().label("transaction_count"),
        func.sum(models.Transaction.amount).label("total_volume")
    ).group_by(group_col)
    
    result = await db.execute(query)
    
    return [
        {
            # str() ensures Dates and Enums serialize cleanly into JSON
            dimension: str(row.dimension_value) if row.dimension_value else None,
            "count": row.transaction_count,
            "total_volume": float(row.total_volume) if row.total_volume else 0.0
        }
        for row in result.all()
    ]

async def get_discrepancies(db: AsyncSession):

    raw_query = text("""
        WITH transaction_paths AS (
            -- Step 1: Build the chronological timeline of events per transaction
            SELECT 
                transaction_id, 
                STRING_AGG(event_type::text, ' ➔ ' ORDER BY timestamp ASC) as state_path,
                MAX(timestamp) as last_event_time
            FROM event 
            GROUP BY transaction_id
        ),
        evaluated_paths AS (
            -- Step 2: Apply the discrepancy rules sequentially
            SELECT 
                transaction_id,
                state_path,
                CASE
                    -- 1. Missing Initiation (Orphan)
                    -- If it doesn't start exactly with payment_initiated, the first event was dropped or arrived out of order.
                    WHEN state_path NOT LIKE 'payment_initiated%' THEN 'Orphan: Missing or late payment initiation'
                    
                    -- 2. Catch the Zombies (Failed then Settled)
                    WHEN state_path LIKE '%payment_failed% ➔ %settled%' THEN 'Zombie: Settled after failure'
                    
                    -- 3. Conflicting Reversal (Settled then Failed)
                    WHEN state_path LIKE '%settled% ➔ %payment_failed%' THEN 'Conflict: Failed after being settled'
                    
                    -- 4. Catch Skipped Steps
                    WHEN state_path LIKE '%settled%' AND state_path NOT LIKE '%payment_processed%' THEN 'Skipped: Settled without processing'
                    
                    -- 5. Duplicate Terminal Events
                    -- A gateway should never send multiple settlements or multiple failures for the same transaction.
                    WHEN state_path LIKE '%settled% ➔ %settled%' THEN 'Duplicate: Multiple settlement events'
                    WHEN state_path LIKE '%payment_failed% ➔ %payment_failed%' THEN 'Duplicate: Multiple failure events'
                    
                    -- 6. Catch Stuck Transactions (In progress, but too old)
                    WHEN state_path NOT LIKE '%settled%' AND state_path NOT LIKE '%payment_failed%' 
                         AND last_event_time < NOW() - INTERVAL '48 hours' THEN 'Stuck: No terminal state after 48h'
                END as discrepancy_reason
            FROM transaction_paths
        )
      
        SELECT 
            transaction_id, 
            state_path, 
            discrepancy_reason
        FROM evaluated_paths
        WHERE discrepancy_reason IS NOT NULL;
    """)
    
    result = await db.execute(raw_query)
    
    return [
        {
            "transaction_id": row.transaction_id,
            "state_path": row.state_path,
            "reason": row.discrepancy_reason
        }
        for row in result.all()
    ]

async def get_transactions(db: AsyncSession, params: PaymentQueryParams):

    query = select(models.Transaction)
    
    # Apply dynamic filters
    if params.merchant_id:
        query = query.where(models.Transaction.merchant_id == params.merchant_id)
    if params.status:
        query = query.where(models.Transaction.current_status == params.status)
    if params.start_date:
        query = query.where(models.Transaction.created_at >= params.start_date)
    if params.end_date:
        query = query.where(models.Transaction.created_at <= params.end_date)
        
    # Apply sorting dynamically
    sort_column = getattr(models.Transaction, params.sort_by)
    if params.sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
        
    query = query.limit(params.limit).offset(params.offset)
    
    result = await db.execute(query)
    return result.scalars().all()