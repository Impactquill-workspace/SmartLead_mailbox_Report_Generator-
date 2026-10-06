"""Pydantic schemas for mailboxes."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class MailboxBase(BaseModel):
    email: str
    smartlead_email_account_id: Optional[int] = None
    from_name: Optional[str] = None


class MailboxOut(MailboxBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MailboxStatOut(BaseModel):
    """Aggregated statistics for a single mailbox."""
    model_config = ConfigDict(from_attributes=True)

    email: str
    mailbox_id: Optional[int] = None
    sent: int
    bounced: int
    bounce_rate: float
