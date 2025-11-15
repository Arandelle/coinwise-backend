from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Account(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: Optional[str] = Field(default=None, alias="user_id")
    balance : float
    created_at: datetime = Field(default_factory=datetime.now)