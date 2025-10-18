from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from models.user import UserCreate, UserLogin, Token, UserResponse
from utils.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    decode_token,
    oauth2_scheme
)
from database import db

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    try:
        # Validate password length BEFORE hashing
        password_bytes = user.password.encode('utf-8')
        
        # DEBUG: Check password byte length
        print(f"Password: {user.password}")
        print(f"Character length: {len(user.password)}")
        print(f"Byte length: {len(password_bytes)}")
        
        # Optional: Warn if password will be truncated
        # (Remove this check if using auto-truncation in get_password_hash)

        # Hash password safely (only after validation passes)
        hashed_password = get_password_hash(user.password)

        # Create user document
        user_dict = {
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow(),
            "is_active": True
        }

        # Insert into database
        result = await db.users.insert_one(user_dict)
        print("Inserted ID:", result.inserted_id)

        # Fetch created user
        created_user = await db.users.find_one({"_id": result.inserted_id})
        print("Created User:", created_user)

        # Convert ObjectId to string for response
        created_user["_id"] = str(created_user["_id"])

        return created_user

    except HTTPException:
        # Re-raise HTTPExceptions (including our password length check)
        raise
    except Exception as e:
        print("Error during signup:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during signup"
        )
@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    """Login user and return JWT token"""
    # Find user by email
    db_user = await db.users.find_one({"email": user.email})
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not db_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": user.email, "username": db_user["username"]}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current logged-in user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
    
    # Get user from database
    user = await db.users.find_one({"email": email})
    if user is None:
        raise credentials_exception
    
    # Convert ObjectId to string
    user["_id"] = str(user["_id"])
    
    return user