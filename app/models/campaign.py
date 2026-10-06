"""
Campaign ORM model.
Maps to the 'campaigns' PostgreSQL table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    __table_args__ = (
        UniqueConstraint(
            "smartlead_campaign_id", name="uq_campaigns_smartlead_campaign_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smartlead_campaign_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
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
        "Client", back_populates="campaigns"
    )
    campaign_mailboxes: Mapped[list["CampaignMailbox"]] = relationship(  # noqa: F821
        "CampaignMailbox", back_populates="campaign", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Campaign id={self.id} smartlead_id={self.smartlead_campaign_id} "
            f"name={self.name!r} status={self.status}>"
        )
