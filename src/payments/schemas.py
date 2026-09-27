from decimal import Decimal
from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum

class EventType(str, Enum):
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_PROCESSED = "payment_processed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SETTLED = "payment_settled"

class PaymentStatus(str, Enum):
    PROCESSED = "PROCESSED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    INITIATED = "INITIATED"

class EventRequest(BaseModel):
    event_id: str = Field(..., description="Unique ID for this specific event")
    event_type: EventType = Field(..., description="The event type")
    transaction_id: str = Field(..., description="Unique ID for the transaction")
    merchant_id: str = Field(..., description="ID of the merchant")
    merchant_name: str = Field(..., description="Name of the merchant")
    amount: Decimal = Field(..., gt=0, description="Payment amount must be strictly positive")
    currency: str = Field(default="INR", min_length=3, max_length=3)
    timestamp: datetime = Field(..., description="When the event occurred")

class TransactionResponse(BaseModel):
    id: str
    merchant_id: str
    amount: Decimal
    currency: str
    current_status: PaymentStatus 
    last_event_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class EventResponse(BaseModel):
    id: str
    event_type: EventType
    timestamp: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TransactionDetailResponse(TransactionResponse):
    # Inherits everything from TransactionResponse, but adds the nested events list
    events: list[EventResponse] = []


T = TypeVar('T')

class PaginationMeta(BaseModel):
    total_items: int
    current_page: int
    total_pages: int
    limit: int
    has_next_page: bool
    has_previous_page: bool

class PaginatedResponse(BaseModel, Generic[T]):
    data: List[T]
    meta: PaginationMeta