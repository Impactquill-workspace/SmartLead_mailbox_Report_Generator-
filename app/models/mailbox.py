"""
Mailbox ORM model.
Maps to the 'mailboxes' PostgreSQL table.

Deduplication strategy:
  Primary key: smartlead_email_account_id (numeric ID from Smartlead)
  Fallback: normalized email address (lowercased) if ID is unavailable
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Mailbox(Base):
    __tablename__ = "mailboxes"

    __table_args__ = (
        UniqueConstraint(
            "smartlead_email_account_id",
            name="uq_mailboxes_smartlead_email_account_id",
        ),
        UniqueConstraint(
            "normalized_email",
            name="uq_mailboxes_normalized_email",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Smartlead's numeric email account ID — preferred deduplication key
    smartlead_email_account_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    # Display email address
    email: Mapped[str] = mapped_column(String(500), nullable=False)

    # Lowercased for reliable deduplication when ID is absent
    normalized_email: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True
    )

    # From name (display name)
    from_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Which client owns this mailbox
    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client", back_populates="mailboxes"
    )
    campaign_mailboxes: Mapped[list["CampaignMailbox"]] = relationship(  # noqa: F821
        "CampaignMailbox", back_populates="mailbox", lazy="selectin"
    )
    mailbox_stats: Mapped[list["MailboxStat"]] = relationship(  # noqa: F821
        "MailboxStat", back_populates="mailbox", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Mailbox id={self.id} "
            f"smartlead_id={self.smartlead_email_account_id} "
            f"email={self.email!r}>"
        )
