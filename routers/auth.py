from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from models.user import UserCreate, UserLogin, Token, UserResponse
from utils.auth import (
    get_password_hash, 
    verify_password, 
    create_access_token,
)
from database import db
from utils.auth import get_current_user
from models.category import Category_Group

router = APIRouter(prefix="/auth", tags=["Authentication"])

async def create_default_category_groups_and_categories(user_id: str):
    """Create default category groups and their categories for a new user"""
    
    # Define default structure matching your schema
    defaults = [
        {
            "group": {
                "name": "Essential Expenses",
                "description": "Basic living expenses",
                "type" : "expense"
            },
            "categories": [
                {"category_name": "Housing", "type": "expense", "icon": "Home"},
                {"category_name": "Groceries", "type": "expense", "icon": "ShoppingCart"},
                {"category_name": "Transportation", "type": "expense", "icon": "Car"},
                {"category_name": "Healthcare", "type": "expense", "icon": "Heart"}
            ]
        },
        {
            "group": {
                "name": "Lifestyle",
                "description": "Personal and entertainment expenses",
                "type" : "expense"
            },
            "categories": [
                {"category_name": "Dining Out", "type": "expense", "icon": "Utensils"},
                {"category_name": "Entertainment", "type": "expense", "icon": "Film"},
                {"category_name": "Shopping", "type": "expense", "icon": "ShoppingBag"},
                {"category_name": "Travel", "type": "expense", "icon": "Plane"}
            ]
        },
        {
            "group": {
                "name": "Income",
                "description": "Sources of income",
                "type" : "income"
            },
            "categories": [
                {"category_name": "Salary", "type": "income", "icon": "Briefcase"},
                {"category_name": "Freelance", "type": "income", "icon": "Code"},
                {"category_name": "Investments", "type": "income", "icon": "TrendingUp"},
                {"category_name": "Other Income", "type": "income", "icon": "DollarSign"}
            ]
        },
        {
            "group": {
                "name": "Savings & Goals",
                "description": "Long-term financial goals",
                "type" : "expense"
            },
            "categories": [
                {"category_name": "Emergency Fund", "type": "expense", "icon": "Shield"},
                {"category_name": "Retirement", "type": "expense", "icon": "Palmtree"},
                {"category_name": "Investment Fund", "type": "expense", "icon": "PiggyBank"},
                {"category_name": "Debt Payment", "type": "expense", "icon": "CreditCard"}
            ]
        },
        {
            "group": {
                "name": "Others",
                "description": "Other expenses",
                "type" : "expense"
            },
            "categories": [
                {"category_name": "Others", "type": "expense", "icon": "Ellipsis"}
            ]
        },
        {
            "group": {
                "name": "Others",
                "description": "Other income",
                "type" : "income"
            },
            "categories": [
                {"category_name": "Others", "type": "income", "icon": "Ellipsis"}
            ]
        }
    ]
    
    # Create category groups and their categories
    for default in defaults:
        # Create category group
        group_doc = {
            "user_id" : user_id,
            "group_name" : default["group"]["name"],
            "description" : default["group"]["description"],
            "type" : default["group"]["type"],
        }
        
        
        group_result = await db.category_groups.insert_one(group_doc)
        group_id = str(group_result.inserted_id)
        
        # Create categories for this group using YOUR schema
        categories = []
        for cat in default["categories"]:
            category_doc = {
                "user_id": user_id,
                "group_id": group_id,  # Note: using "group_id" not "category_group_id"
                "category_name": cat["category_name"],
                "type": cat["type"],
                "icon": cat["icon"],
            }
            categories.append(category_doc)
        
        # Insert all categories for this group
        if categories:
            await db.categories.insert_many(categories)

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
        user_id = str(result.inserted_id)
        print("Inserted ID:", user_id)
        
        await create_default_category_groups_and_categories(user_id)

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
async def get_current_user(current_user: dict = Depends(get_current_user)):
    """Return the currently logged-in user"""
    return current_user
    