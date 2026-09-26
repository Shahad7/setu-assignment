from datetime import datetime
from typing import List
from sqlalchemy import String, Numeric, DateTime, Enum as SQLEnum, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.payments.schemas import PaymentStatus, EventType

class Merchant(Base):
    __tablename__ = "merchant"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transaction"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String, ForeignKey("merchant.id"), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    current_status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), nullable=False)
    last_event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    merchant: Mapped["Merchant"] = relationship(back_populates="transactions")
    events: Mapped[List["Event"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")

class Event(Base):
    __tablename__ = "event"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String, ForeignKey("transaction.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    transaction: Mapped["Transaction"] = relationship(back_populates="events")
    __table_args__ = (Index("idx_transaction_timestamp", "transaction_id", "timestamp"),)