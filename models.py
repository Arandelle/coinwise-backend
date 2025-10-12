from pydantic import BaseModel, Field
from typing import Optional
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectID")
        return str(v)

class Transaction(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: int
    amount: float
    type: str
    category: str
    name: str

    class Config:
        populate_by_name = True
        extra = "ignore"
