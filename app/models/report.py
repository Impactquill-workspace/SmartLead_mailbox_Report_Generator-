"""
Report ORM model.
Stores metadata about generated reports.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Path to the generated Excel file
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Summary statistics
    total_clients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_mailboxes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sent: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bounced: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    overall_bounce_rate: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=4), nullable=False, default=0
    )

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} "
            f"period={self.period_start}→{self.period_end} "
            f"clients={self.total_clients} mailboxes={self.total_mailboxes}>"
        )
