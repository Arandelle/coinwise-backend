from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Category(BaseModel):
    id: Optional[str] = Field(alias="_id")
    user_id: str
    name: str
    type: str # expenses or income
    icon: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)