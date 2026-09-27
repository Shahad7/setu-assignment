from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Literal

from src.database import get_db
from src.payments import schemas, service
from src.payments.dependencies import PaymentQueryParams

router = APIRouter()

@router.post("/events", response_model=schemas.TransactionResponse, status_code=201, tags=["Events"])
async def ingest_event(
    payload: schemas.TransactionRequest, 
    db: AsyncSession = Depends(get_db)
):
    try:
        return await service.process_event(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/transactions", response_model=List[schemas.TransactionResponse], tags=["Transactions"])
async def list_transactions(
    params: PaymentQueryParams = Depends(),
    db: AsyncSession = Depends(get_db)
):
    return await service.get_transactions(db, params)

@router.get("/transactions/{transaction_id}", response_model=schemas.TransactionDetailResponse, tags=["Transactions"])
async def get_transaction_detail(
    transaction_id: str, 
    db: AsyncSession = Depends(get_db)
):
    transaction = await service.get_transaction_with_events(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@router.get("/reconciliation/summary", response_model=List[Dict[str, Any]], tags=["Reconciliation"])
async def get_summary(
    dimension: Literal["merchant", "status", "date"] = Query("merchant"),
    db: AsyncSession = Depends(get_db)
):
    return await service.get_reconciliation_summary(db, dimension)

@router.get("/reconciliation/discrepancies", response_model=List[Dict[str, Any]], tags=["Reconciliation"])
async def list_discrepancies(db: AsyncSession = Depends(get_db)):
    return await service.get_discrepancies(db)