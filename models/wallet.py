from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Wallet(BaseModel):
    id: Optional[str] = Field(alias = "_id")
    user_id: str
    name: str = "Wallet"
    balance: float = 0.0
    currency: str = "PHP"
    last_updated: datetime = Field(default_factory=datetime.utcnow)