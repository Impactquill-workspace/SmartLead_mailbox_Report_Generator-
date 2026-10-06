"""
CampaignMailbox ORM model.
Join table between campaigns and mailboxes.
Tracks which mailboxes belong to which campaigns.
Unique constraint on (campaign_id, mailbox_id) prevents duplicate associations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class CampaignMailbox(Base):
    __tablename__ = "campaign_mailboxes"

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "mailbox_id",
            name="uq_campaign_mailboxes_campaign_mailbox",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mailbox_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship(  # noqa: F821
        "Campaign", back_populates="campaign_mailboxes"
    )
    mailbox: Mapped["Mailbox"] = relationship(  # noqa: F821
        "Mailbox", back_populates="campaign_mailboxes"
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignMailbox campaign_id={self.campaign_id} "
            f"mailbox_id={self.mailbox_id}>"
        )
