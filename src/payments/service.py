from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, asc, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy import func, text
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