import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import engine

async def wipe_database():
    async with AsyncSession(engine) as session:
        # TRUNCATE CASCADE instantly empties the tables and handles all foreign key dependencies
        # Adjust table names if they differ in your database (e.g., 'merchants', 'transactions', 'events')
        wipe_query = text("TRUNCATE TABLE setu.event, setu.transaction, setu.merchant CASCADE;")
        
        await session.execute(wipe_query)
        await session.commit()
        
        print("Database wiped successfully. All tables are now empty.")

if __name__ == "__main__":
    asyncio.run(wipe_database())