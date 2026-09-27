
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from src.payments import schemas
from src.payments import service as sut

class FakeResult:
    """Small stand-in for the SQLAlchemy result methods used by the service."""
    def __init__(self, value=None, rows=None, scalar_rows=None):
        self.value = value
        self.rows = rows or []
        self.scalar_rows = scalar_rows or []

    def scalar_one_or_none(self):
        return self.value

    def all(self):
        return self.rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self.scalar_rows)


@pytest.fixture
def db():
    """Mock AsyncSession. These tests never connect to a database."""
    return SimpleNamespace(
        execute=AsyncMock(),
        scalar=AsyncMock(),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        rollback=AsyncMock(),
    )


def make_event(
    *,
    event_id="event-1",
    transaction_id="txn-1",
    merchant_id="merchant-1",
    event_type=None,
    amount=15248.29,
    currency="INR",
    timestamp=None,
):
    return SimpleNamespace(
        event_id=event_id,
        transaction_id=transaction_id,
        merchant_id=merchant_id,
        event_type=event_type or schemas.EventType.PAYMENT_PROCESSED,
        amount=amount,
        currency=currency,
        timestamp=timestamp or datetime(2026, 1, 8, 12, tzinfo=timezone.utc),
    )


def make_transaction(
    *,
    transaction_id="txn-1",
    merchant_id="merchant-1",
    amount=15248.29,
    currency="INR",
    current_status=schemas.PaymentStatus.INITIATED,
    last_event_timestamp=None,
):
    return SimpleNamespace(
        id=transaction_id,
        merchant_id=merchant_id,
        amount=amount,
        currency=currency,
        current_status=current_status,
        last_event_timestamp=last_event_timestamp
        or datetime(2026, 1, 8, 11, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_process_event_creates_transaction_and_event(db):
    event = make_event()
    db.execute.side_effect = [
        FakeResult(value=None),  # transaction lookup
        FakeResult(value=None),  # event ID lookup
    ]

    response = await sut.process_event(db, event)

    assert response["id"] == event.event_id
    assert response["event_type"] == event.event_type
    assert response["timestamp"] == event.timestamp

    assert db.add.call_count == 2
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_rejects_merchant_mismatch(db):
    transaction = make_transaction(merchant_id="another-merchant")
    db.execute.return_value = FakeResult(value=transaction)

    with pytest.raises(HTTPException) as exc_info:
        await sut.process_event(db, make_event())

    assert exc_info.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_event_rejects_amount_mismatch(db):
    transaction = make_transaction(amount=100.00)
    db.execute.return_value = FakeResult(value=transaction)

    with pytest.raises(HTTPException) as exc_info:
        await sut.process_event(db, make_event(amount=200.00))

    assert exc_info.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_event_is_saved_without_regressing_transaction_status(db):
    newer_time = datetime(2026, 1, 8, 12, tzinfo=timezone.utc)
    older_time = newer_time - timedelta(minutes=5)
    transaction = make_transaction(
        current_status=schemas.PaymentStatus.PROCESSED,
        last_event_timestamp=newer_time,
    )
    event = make_event(
        event_id="older-event",
        event_type=schemas.EventType.PAYMENT_FAILED,
        timestamp=older_time,
    )

    db.execute.side_effect = [
        FakeResult(value=transaction),  # transaction lookup
        FakeResult(value=None),         # event ID lookup
    ]

    await sut.process_event(db, event)

    assert transaction.current_status == schemas.PaymentStatus.PROCESSED
    assert transaction.last_event_timestamp == newer_time
    assert db.add.call_count == 1  # event is retained in the history
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_event_id_is_not_added_again(db):
    timestamp = datetime(2026, 1, 8, 12, tzinfo=timezone.utc)
    transaction = make_transaction(
        current_status=schemas.PaymentStatus.PROCESSED,
        last_event_timestamp=timestamp,
    )
    existing_event = SimpleNamespace(
        id="event-1",
        event_type=schemas.EventType.PAYMENT_PROCESSED,
        timestamp=timestamp,
        created_at=timestamp,
    )
    event = make_event(timestamp=timestamp)

    db.execute.side_effect = [
        FakeResult(value=transaction),     # transaction lookup
        FakeResult(value=existing_event),  # event ID lookup
    ]

    response = await sut.process_event(db, event)

    assert response["id"] == "event-1"
    assert db.add.call_count == 0
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_transaction_with_events_returns_transaction(db):
    transaction = make_transaction()
    db.execute.return_value = FakeResult(value=transaction)

    result = await sut.get_transaction_with_events(db, "txn-1")

    assert result is transaction
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_transaction_with_events_returns_none_when_missing(db):
    db.execute.return_value = FakeResult(value=None)

    result = await sut.get_transaction_with_events(db, "missing-txn")

    assert result is None


@pytest.mark.asyncio
async def test_reconciliation_summary_formats_aggregate_rows(db):
    db.execute.return_value = FakeResult(
        rows=[
            SimpleNamespace(
                dimension_value="merchant-1",
                transaction_count=2,
                total_volume=300.50,
            ),
            SimpleNamespace(
                dimension_value="merchant-2",
                transaction_count=1,
                total_volume=99.50,
            ),
        ]
    )

    result = await sut.get_reconciliation_summary(
        db,
        dimension="merchant",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert result["meta"]["dimension"] == "merchant"
    assert result["meta"]["total_records_processed"] == 3
    assert result["meta"]["total_system_volume"] == pytest.approx(400.00)
    assert result["results"] == [
        {
            "dimension_value": "merchant-1",
            "transaction_count": 2,
            "total_volume": pytest.approx(300.50),
        },
        {
            "dimension_value": "merchant-2",
            "transaction_count": 1,
            "total_volume": pytest.approx(99.50),
        },
    ]


@pytest.mark.asyncio
async def test_get_discrepancies_returns_reasons_per_transaction(db):
    db.execute.return_value = FakeResult(
        rows=[
            SimpleNamespace(
                transaction_id="txn-1",
                reasons=["Stuck: No terminal state after 24h"],
            ),
            SimpleNamespace(
                transaction_id="txn-2",
                reasons=["Missing initiation: started at PAYMENT_SETTLED"],
            ),
        ]
    )

    result = await sut.get_discrepancies(db)

    assert result == [
        {
            "transaction_id": "txn-1",
            "reasons": ["Stuck: No terminal state after 24h"],
        },
        {
            "transaction_id": "txn-2",
            "reasons": ["Missing initiation: started at PAYMENT_SETTLED"],
        },
    ]


@pytest.mark.asyncio
async def test_get_transactions_returns_page_metadata(db):
    params = SimpleNamespace(
        merchant_id="merchant-1",
        status=schemas.PaymentStatus.PROCESSED,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        sort_by="created_at",
        sort_order="desc",
        limit=10,
        offset=10,
    )
    transactions = [
        make_transaction(transaction_id="txn-11"),
        make_transaction(transaction_id="txn-12"),
    ]

    db.scalar.return_value = 23
    db.execute.return_value = FakeResult(scalar_rows=transactions)

    result = await sut.get_transactions(db, params)

    assert result["data"] == transactions
    assert result["meta"] == {
        "total_items": 23,
        "current_page": 2,
        "total_pages": 3,
        "limit": 10,
        "has_next_page": True,
        "has_previous_page": True,
    }
    db.scalar.assert_awaited_once()
    db.execute.assert_awaited_once()