from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.payments import schemas, service

router = APIRouter(
    prefix="/api/v1/payments", 
    tags=["Payments Integration"]
)

@router.get("/")
def dummy():
    return {"hello":"from the other side"}