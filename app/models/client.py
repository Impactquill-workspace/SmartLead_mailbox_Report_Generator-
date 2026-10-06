"""
Client ORM model.
Maps to the 'clients' PostgreSQL table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Client(Base):
    __tablename__ = "clients"

    __table_args__ = (
        UniqueConstraint("smartlead_client_id", name="uq_clients_smartlead_client_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    smartlead_client_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
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
    campaigns: Mapped[list["Campaign"]] = relationship(  # noqa: F821
        "Campaign", back_populates="client", lazy="selectin"
    )
    mailboxes: Mapped[list["Mailbox"]] = relationship(  # noqa: F821
        "Mailbox", back_populates="client", lazy="selectin"
    )
    mailbox_stats: Mapped[list["MailboxStat"]] = relationship(  # noqa: F821
        "MailboxStat", back_populates="client", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Client id={self.id} smartlead_id={self.smartlead_client_id} name={self.name!r}>"
