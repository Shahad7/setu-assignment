from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import func, text, cast, Date
from typing import Literal, Optional
import logging

from src.payments import models, schemas
from src.payments.dependencies import TransactionQueryParams

logger = logging.getLogger(__name__)

async def process_event(db: AsyncSession, event: schemas.EventRequest):

    txn_query = select(models.Transaction).where(
        models.Transaction.id == event.transaction_id
    ).with_for_update()
    
    txn_result = await db.execute(txn_query)
    transaction = txn_result.scalar_one_or_none()

    # Determine status mapping
    if event.event_type == schemas.EventType.PAYMENT_PROCESSED:
        new_status = schemas.PaymentStatus.PROCESSED
    elif event.event_type == schemas.EventType.PAYMENT_FAILED:
        new_status = schemas.PaymentStatus.FAILED
    elif event.event_type == schemas.EventType.PAYMENT_SETTLED:
        new_status = schemas.PaymentStatus.SETTLED
    else:
        new_status = schemas.PaymentStatus.INITIATED

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
        if transaction.merchant_id != event.merchant_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Data conflict: Transaction {transaction.id} belongs to merchant {transaction.merchant_id}."
            )
        
        if transaction.amount != event.amount or transaction.currency != event.currency:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Data conflict: Amount/Currency mismatch for transaction {transaction.id}."
            )
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
    processed_event = existing_event
    if not existing_event:
        new_event = models.Event(
            id=event.event_id,
            transaction_id=event.transaction_id,
            event_type=event.event_type,
            timestamp=event.timestamp
        )
        processed_event = new_event
        db.add(new_event)

    try:
        await db.commit()
        await db.refresh(processed_event)
        return {
            "id": processed_event.id,          
            "event_type": processed_event.event_type,
            "timestamp": processed_event.timestamp,
            "created_at": processed_event.created_at
        }
    except IntegrityError as e:
        await db.rollback()
        if "foreign key constraint" in str(e.orig).lower():
            raise ValueError(f"Merchant ID {event.merchant_id} does not exist in the system.")
        raise ValueError("Failed to ingest payment due to data integrity conflict.")

async def get_transaction_with_events(db: AsyncSession, transaction_id: str):

    query = select(models.Transaction).options(
        selectinload(models.Transaction.events),
        selectinload(models.Transaction.merchant)
    ).where(models.Transaction.id == transaction_id)
    
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_reconciliation_summary(
    db: AsyncSession, 
    dimension: Literal["merchant", "status", "date"] = "merchant",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    # Map the requested string dimension to the actual SQLAlchemy column expression
    if dimension == "merchant":
        group_col = models.Transaction.merchant_id
    elif dimension == "status":
        group_col = models.Transaction.current_status
    elif dimension == "date":
        group_col = cast(models.Transaction.created_at, Date)
    
    # Build the dynamic aggregation query
    query = select(
        group_col.label("dimension_value"),
        func.count().label("transaction_count"),
        func.sum(models.Transaction.amount).label("total_volume")
    ).group_by(group_col)

    # Apply date filters if provided
    if start_date:
        query = query.where(cast(models.Transaction.created_at, Date) >= start_date)
    if end_date:
        query = query.where(cast(models.Transaction.created_at, Date) <= end_date)
    
    result = await db.execute(query)
    
    rows = result.all()
    
    return {
        "meta": {
            "dimension": dimension,
            "period_start": start_date or "all_time",
            "period_end": end_date or "all_time",
            "total_records_processed": sum(row.transaction_count for row in rows),
            "total_system_volume": float(sum(row.total_volume for row in rows if row.total_volume) or 0.0)
        },
        "results": [
            {
                "dimension_value": row.dimension_value.name if hasattr(row.dimension_value, 'name') else row.dimension_value,
                "transaction_count": row.transaction_count,
                "total_volume": float(row.total_volume) if row.total_volume else 0.0
            }
            for row in rows
        ]
    }

from sqlalchemy import text
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

async def get_discrepancies(db: AsyncSession) -> List[Dict[str, Any]]:
    raw_query = text("""
        WITH state_transitions AS (
            SELECT 
                transaction_id,
                event_type AS from_state,
                timestamp AS event_time,
                LEAD(event_type) OVER (PARTITION BY transaction_id ORDER BY timestamp ASC) AS to_state,
                LAG(event_type) OVER (PARTITION BY transaction_id ORDER BY timestamp ASC) AS prev_state
            FROM setu.event
        ),
        evaluated_discrepancies AS (
            SELECT 
                transaction_id,
                CASE
                    -- If a transition happens, it MUST be one of these valid paths.
                    WHEN to_state IS NOT NULL AND NOT (
                        (from_state = 'PAYMENT_INITIATED' AND to_state IN ('PAYMENT_PROCESSED', 'PAYMENT_FAILED')) OR
                        (from_state = 'PAYMENT_PROCESSED' AND to_state IN ('PAYMENT_SETTLED', 'PAYMENT_FAILED'))
                    ) THEN 'Invalid transition: ' || from_state || ' ➔ ' || to_state
                    
                    -- Orphan Check
                    -- If there is no previous state, the from_state MUST be PAYMENT_INITIATED
                    WHEN prev_state IS NULL AND from_state != 'PAYMENT_INITIATED'
                    THEN 'Missing initiation: started at ' || from_state
                    
                    -- Stuck Transaction Check
                    -- If there is no next state, it's not terminal, and 24 hours have passed
                    WHEN to_state IS NULL 
                         AND from_state NOT IN ('PAYMENT_SETTLED', 'PAYMENT_FAILED')
                         AND event_time < NOW() - INTERVAL '24 hours'
                    THEN 'Stuck: No terminal state after 24h from ' || from_state
                    
                    ELSE NULL
                END AS discrepancy_reason
            FROM state_transitions
        )
        
        -- Aggregate all reasons per transaction into a clean array
        SELECT 
            transaction_id,
            ARRAY_AGG(discrepancy_reason) AS reasons
        FROM evaluated_discrepancies
        WHERE discrepancy_reason IS NOT NULL
        GROUP BY transaction_id;
    """)
    
    result = await db.execute(raw_query)
    
    return [
        {
            "transaction_id": row.transaction_id,
            "reasons": row.reasons
        }
        for row in result.all()
    ]

async def get_transactions(db: AsyncSession, params: TransactionQueryParams):
    # Build the base query with all dynamic filters
    query = select(models.Transaction)
    
    if params.merchant_id:
        query = query.where(models.Transaction.merchant_id == params.merchant_id)
    if params.status:
        query = query.where(models.Transaction.current_status == params.status)
    if params.start_date:
        query = query.where(models.Transaction.created_at >= params.start_date)
    if params.end_date:
        query = query.where(models.Transaction.created_at <= params.end_date)
        
    # Execute the Count Query (BEFORE adding order_by, limit, or offset)
    # Wrapping the base query in a subquery guarantees the filters apply to the count
    count_query = select(func.count()).select_from(query.subquery())
    total_items = await db.scalar(count_query) or 0
        
    # Apply sorting
    sort_column = getattr(models.Transaction, params.sort_by)
    if params.sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
        
    # Apply pagination limits
    query = query.limit(params.limit).offset(params.offset)
    
    # Fetch the actual data chunk
    result = await db.execute(query)
    items = result.scalars().all()
    
    # Calculate pagination metadata
    current_page = (params.offset // params.limit) + 1
    total_pages = (total_items + params.limit - 1) // params.limit # Integer ceiling math
    
    # Return a structured dictionary
    return {
        "data": items,
        "meta": {
            "total_items": total_items,
            "current_page": current_page,
            "total_pages": total_pages,
            "limit": params.limit,
            "has_next_page": current_page < total_pages,
            "has_previous_page": current_page > 1
        }
    }