import json
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
# Import the PostgreSQL specific insert
from sqlalchemy.dialects.postgresql import insert as pg_insert 
from src.database import engine
from src.payments.models import Merchant, Transaction, Event
from datetime import datetime, timedelta, timezone

def chunked_iterable(iterable, size):
    """Yield successive chunks from an iterable."""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

async def seed_database():
    async with AsyncSession(engine) as session:
        # 1. Create the 5 Merchants (Silently skip if they already exist)
        merchants = [{"id": f"merchant_{i}", "name": f"Test Merchant {i}"} for i in range(1, 6)]
        
        merchant_stmt = pg_insert(Merchant).values(merchants).on_conflict_do_nothing()
        await session.execute(merchant_stmt)
        
        # 2. Load JSON
        with open("sample_events.json", "r") as f:
            events_data = json.load(f)
            
        transactions = {}
        events = []

        # 1. Map your exact Event strings to your Transaction Status Enum strings
        # Adjust these values to match exactly what is in your models.py
        EVENT_TO_STATUS_MAP = {
            "PAYMENT_INITIATED": "INITIATED",
            "PAYMENT_PROCESSED": "PROCESSED",
            "PAYMENT_SETTLED": "SETTLED",
            "PAYMENT_FAILED": "FAILED"
        }

        base_ingestion_time = datetime.now(timezone.utc)
        for index,e in enumerate(events_data):
            tx_id = e["transaction_id"]
            parsed_timestamp = datetime.fromisoformat(e["timestamp"])
            
            # Convert the event string to the correct uppercase event format if needed
            raw_event = e["event_type"].upper()
            simulated_ingestion_time = base_ingestion_time + timedelta(milliseconds=index)

            events.append({
                "id": e["event_id"],
                "transaction_id": tx_id,
                "event_type": raw_event,
                "timestamp": parsed_timestamp,
                "created_at":simulated_ingestion_time
            })
            
            # 2. Chronological Safeguard: Only update the parent transaction 
            # if this event is chronologically newer than the one we already processed
            if tx_id not in transactions or parsed_timestamp > transactions[tx_id]["last_event_timestamp"]:
                
                # Apply the mapping here
                mapped_status = EVENT_TO_STATUS_MAP.get(raw_event, raw_event)

                transactions[tx_id] = {
                    "id": tx_id,
                    "merchant_id": e["merchant_id"], 
                    "amount": e["amount"],           
                    "currency": "INR",
                    "current_status": mapped_status, 
                    "last_event_timestamp": parsed_timestamp,
                    "created_at" : simulated_ingestion_time
                }
        
        # 3. Bulk Insert Transactions (Skip existing)
        if transactions:
            tx_list = list(transactions.values())
            for chunk in chunked_iterable(tx_list, 2000):
                tx_stmt = pg_insert(Transaction).values(chunk).on_conflict_do_nothing()
                await session.execute(tx_stmt)
        
        # 4. Bulk Insert Events (Skip existing)
        if events:
            for chunk in chunked_iterable(events, 1000):
                event_stmt = pg_insert(Event).values(chunk).on_conflict_do_nothing()
                await session.execute(event_stmt)
        
        await session.commit()
        print("Successfully seeded data. Duplicate rows were skipped.")

if __name__ == "__main__":
    asyncio.run(seed_database())