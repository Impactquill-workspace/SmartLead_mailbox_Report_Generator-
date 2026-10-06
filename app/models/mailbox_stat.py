"""
MailboxStat ORM model.
Stores aggregated mailbox-level statistics for a report period.
Unique on (mailbox_id, period_start, period_end).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class MailboxStat(Base):
    __tablename__ = "mailbox_stats"

    __table_args__ = (
        UniqueConstraint(
            "mailbox_id",
            "period_start",
            "period_end",
            name="uq_mailbox_stats_mailbox_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    mailbox_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    sent: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bounced: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bounce_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=4), nullable=False, default=Decimal("0")
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
    mailbox: Mapped["Mailbox"] = relationship(  # noqa: F821
        "Mailbox", back_populates="mailbox_stats"
    )
    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client", back_populates="mailbox_stats"
    )

    def __repr__(self) -> str:
        return (
            f"<MailboxStat mailbox_id={self.mailbox_id} "
            f"period={self.period_start}→{self.period_end} "
            f"sent={self.sent} bounced={self.bounced} "
            f"rate={self.bounce_rate}%>"
        )
