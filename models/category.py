from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Category_Group(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: Optional[str] = Field(default=None, alias="user_id")
    group_name: str
    type: str
    created_at: datetime = Field(default_factory=datetime.now)

class Category(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: Optional[str] = Field(default=None, alias="user_id")
    group_id: str
    category_name: str
    type: str # expenses or income
    icon: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
