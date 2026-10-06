"""Pydantic schemas for clients."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ClientBase(BaseModel):
    smartlead_client_id: int
    name: str


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
