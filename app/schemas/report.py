"""Pydantic schemas for report API responses."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MailboxReportItem(BaseModel):
    """Per-mailbox statistics in the report."""
    email: str
    mailbox_id: Optional[int] = None
    leads_contacted: int = 0
    sent: int
    bounced: int
    bounce_rate: float


class ClientReportItem(BaseModel):
    """Per-client statistics grouping mailboxes."""
    client_id: int
    client_name: str
    mailboxes: list[MailboxReportItem] = []

    @property
    def total_leads_contacted(self) -> int:
        return sum(m.leads_contacted for m in self.mailboxes)

    @property
    def total_sent(self) -> int:
        return sum(m.sent for m in self.mailboxes)

    @property
    def total_bounced(self) -> int:
        return sum(m.bounced for m in self.mailboxes)

    @property
    def overall_bounce_rate(self) -> float:
        if self.total_sent == 0:
            return 0.0
        return round((self.total_bounced / self.total_sent) * 100, 2)


class WeeklyReportResponse(BaseModel):
    """Full weekly report API response."""
    period_start: str
    period_end: str
    generated_at: str
    total_clients: int
    total_mailboxes: int
    total_leads_contacted: int = 0
    total_sent: int
    total_bounced: int
    overall_bounce_rate: float
    data_attribution_note: str
    excel_file_path: Optional[str] = None
    clients: list[ClientReportItem] = []


class GenerateReportRequest(BaseModel):
    """Request body for manual report generation."""
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    client_id: Optional[int] = None
    status_filter: Optional[str] = "ACTIVE"


class ReportSummary(BaseModel):
    """Lightweight report summary."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_start: date
    period_end: date
    generated_at: datetime
    file_path: Optional[str] = None
    total_clients: int
    total_mailboxes: int
    total_sent: int
    total_bounced: int
    overall_bounce_rate: float
