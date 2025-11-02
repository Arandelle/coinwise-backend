from fastapi import APIRouter, Depends, HTTPException, status
from utils.auth import get_current_user
from database import db
from bson import ObjectId
from models.category import Category_Group


router = APIRouter(prefix="/category-groups", tags=["Category-Groups"])

@router.get("/")
async def get_my_categoryGroup(current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    
    category_group = await db["category_groups"].find({"user_id" : user_id}).to_list(length=None)
    for catGroup in category_group:
        catGroup["_id"] = str(catGroup["_id"])
    
    return category_group

@router.get("/{categoryGroup_id}")
async def get_specific_group(categoryGroup_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    specific_catGroup = await db["category_groups"].find_one(
        {"_id" : ObjectId(categoryGroup_id),
         "user_id" : user_id
         }
    )
    
    if not specific_catGroup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group Category not found or you don't have an access."
        )
    specific_catGroup["_id"] = str(specific_catGroup["_id"])
    
    return specific_catGroup

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_category_group(category_group: Category_Group, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    new_category_group = category_group.dict(by_alias=True, exclude_none=True)
    
    new_category_group["user_id"] = user_id
    
    result = await db["category_groups"].insert_one(new_category_group)
    created = await db["category_groups"].find_one({"_id" : result.inserted_id})
    created["_id"] = str(created["_id"])
    
    return created

@router.put("/{category_group_id}")
async def create_category_group(
    category_group_id: str, 
    category_group: Category_Group, 
    current_user: dict = Depends(get_current_user)
    ):
    
    user_id = current_user["_id"]
    
    existing_group = await db["category_groups"].find_one({
        "_id" : ObjectId(category_group_id),
        "user_id" : user_id
    })
    
    if not existing_group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category Groupt not found or you don't have an access."
        )
    
    updated_group = category_group.dict(by_alias=True, exclude_none=True, exclude={"_id", "created_at"})
    
    result = await db["category_groups"].update_one(
        {"_id" : ObjectId(category_group_id),
          "user_id" : user_id
        }, {"$set" : updated_group}
        )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category Group not found or unchanged"
        )
    
    updated_group = await db["category_groups"].find_one({"_id" : ObjectId(category_group_id)})
    updated_group["_id"] = str(updated_group["_id"])
    
    return updated_group

@router.delete("/{category_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_group(category_group_id: str, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    
    result = await db["category_groups"].delete_one({
        "_id" : ObjectId(category_group_id),
        "user_id" : user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category group not found."
        )
    
    return None