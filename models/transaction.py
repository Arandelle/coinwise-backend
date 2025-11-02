from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId
from datetime import datetime

class PyObjectId(ObjectId): # Custom Pydantic type for MongoDB ObjectId
    @classmethod # to get validators for this custom type
    def __get_validators__(cls): 
        yield cls.validate

    @classmethod
    def validate(cls, value, info):
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectID")
        return str(value)

class Transaction(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: Optional[str] = Field(default=None, alias="user_id")
    category_id: str
    name: str
    amount: float
    type: str
    category: str
    label: Optional[str] = None
    note: Optional[str] = None

    balance_after : Optional[str] = None
    date: datetime = Field(default_factory=datetime.utcnow)
    date_only : Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True # Allow population by field name
        extra = "ignore" # ignore extra fields in the input data
