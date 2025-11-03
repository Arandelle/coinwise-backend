from fastapi import APIRouter, Depends, HTTPException, status
from utils.auth import get_current_user
from database import db
from bson import ObjectId
from models.category import Category

router = APIRouter(prefix="/categories", tags=["Category"])

@router.get("/")
async def get_my_category(current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    category = await db["categories"].find({"user_id" : user_id}).to_list(length=None)
    
    for cat in category:
        cat["_id"] = str(cat["_id"])
        
    return category


@router.get("/{categoryId}")
async def get_specific_category(categoryId: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    specific_category = await db["categories"].find_one({
        "_id" : ObjectId(categoryId),
        "user_id" : user_id
    })
        
    if not specific_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Category not found or you don't have an access."
            )
    
    specific_category["_id"] = str(specific_category["_id"])
    
    return specific_category

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_category(category: Category, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]

    new_category = category.dict(by_alias=True, exclude_none=True)
    
    # Let Pydantic handle default values like created_at
    new_category["user_id"] = user_id
    
    result = await db["categories"].insert_one(new_category)
    created_category = await db["categories"].find_one({
        "_id" : result.inserted_id
    })
    
    created_category["_id"] = str(created_category["_id"])
    
    return created_category


@router.put("/{category_id}")
async def update_category(
    category_id: str,
    category_body: Category, 
    current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    
    # check if category exist and belong to user
    existing_category = await db["categories"].find_one({
        "_id" : ObjectId(category_id),
        "user_id" : user_id
    })
    
    if not existing_category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found or you don't have access"
        )
    
    updated_category = category_body.dict(by_alias=True, exclude_none=True, exclude={"_id", "created_at"})
    
    result = await db["categories"].update_one(
        {"_id": ObjectId(category_id),
         "user_id" : user_id
         },
        {"$set" : updated_category}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_304_NOT_MODIFIED,
            detail="Category not found or unchanged"
        )
    
    updated = await db["categories"].find_one({
        "_id" : ObjectId(category_id)
    })
    
    updated["_id"] = str(updated["_id"])
    
    return updated

@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    
    result = await db["categories"].delete_one({
        "_id" : ObjectId(category_id),
        "user_id" : user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    
    return None