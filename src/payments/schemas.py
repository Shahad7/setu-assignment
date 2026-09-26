from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum

class EventType(str, Enum):
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_PROCESSED = "payment_processed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SETTLED = "settled"

class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class TransactionRequest(BaseModel):
    event_id: str = Field(..., description="Unique ID for this specific event")
    event_type: EventType = Field(..., description="The event type")
    transaction_id: str = Field(..., description="Unique ID for the transaction")
    merchant_id: str = Field(..., description="ID of the merchant")
    merchant_name: str = Field(..., description="Name of the merchant")
    amount: float = Field(..., gt=0, description="Payment amount must be strictly positive")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    timestamp: datetime = Field(..., description="When the event occurred")

class TransactionResponse(BaseModel):
    id: str 
    merchant_id: str
    amount: float
    currency: str
    current_status: PaymentStatus 
    last_event_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)