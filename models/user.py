from pydantic import BaseModel, EmailStr, Field, constr, validator
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=72)  # Add max_length
    
    @validator('password')
    def validate_password_length(cls, v):
        # Check byte length, not character length
        if len(v.encode('utf-8')) > 72:
            raise ValueError('Password cannot be longer than 72 bytes')
        return v

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    email: str                      # ✅ Added
    username: str                   # ✅ Added
    name: Optional[str] = None # ✅ Added
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True  
    
    class Config:
        populate_by_name = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None