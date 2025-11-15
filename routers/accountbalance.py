from fastapi import APIRouter, Depends, status, HTTPException
from utils.auth import get_current_user
from database import db
from models.account import Account
from bson import ObjectId

router = APIRouter(prefix="/account", tags=["Account Balance"])


@router.get("/my-balance")
async def get_my_balance(current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    account = await db["account"].find({"user_id": user_id}).to_list(length=None)

    for acc in account:
        acc["_id"] = str(acc["_id"])

    return account


@router.post("/my-balance", status_code=status.HTTP_201_CREATED)
async def create_balance(balanceData: Account, current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    new_balance = balanceData.dict(by_alias=True, exclude_none=True)
    new_balance["user_id"] = user_id

    result = await db["account"].insert_one(new_balance)

    created_data = await db["account"].find_one({"_id": result.inserted_id})

    created_data["_id"] = str(created_data["_id"])

    return created_data


@router.put("/my-balance/{wallet_id}")
async def update_my_balance(wallet_id: str, balanceData: Account, current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    existing_balance = await db["account"].find_one({"_id": ObjectId(wallet_id), "user_id": user_id})

    if not existing_balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Balance id not found or you don't have an access"
        )
        
    updated_balance = balanceData.dict(by_alias=True, exclude_none=True, exclude={"_id", "created_at"})

    result = await db["account"].update_one({
        "_id" : ObjectId(wallet_id),
        "user_id" : user_id
    }, {
        "$set" : updated_balance
    })
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_304_NOT_MODIFIED,
            detail="Balance not found or unchanged"
        )
    
    get_updatedBalance = await db["account"].find_one({
        "_id" : ObjectId(wallet_id)
    })
    
    get_updatedBalance["_id"] = str(get_updatedBalance["_id"])
    
    return get_updatedBalance