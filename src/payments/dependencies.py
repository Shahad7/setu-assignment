from fastapi import Query
from typing import Optional, Literal
from datetime import datetime

class TransactionQueryParams:
    """
    Consolidated dependency for listing transactions.
    Handles filtering, sorting, and pagination in one place.
    """
    def __init__(
        self,
        # Filtering
        merchant_id: Optional[str] = Query(None, description="Filter by exact Merchant ID"),
        status: Optional[str] = Query(None, description="Filter by payment status (e.g., SETTLED)"),
        start_date: Optional[datetime] = Query(None, description="Filter payments created after this date (ISO 8601)"),
        end_date: Optional[datetime] = Query(None, description="Filter payments created before this date (ISO 8601)"),
        
        # Sorting
        sort_by: Literal["created_at", "amount"] = Query("created_at", description="Field to sort by"),
        sort_order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
        
        # Pagination
        limit: int = Query(50, ge=1, le=2000, description="Number of records to return"),
        offset: int = Query(0, ge=0, description="Number of records to skip")
    ):
        self.merchant_id = merchant_id
        self.status = status
        self.start_date = start_date
        self.end_date = end_date
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.limit = limit
        self.offset = offset