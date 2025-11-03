from fastapi import APIRouter, Depends, HTTPException, status
from utils.auth import get_current_user
from database import db
from bson import ObjectId

router = APIRouter(prefix="/group-with-category", tags=["Group Category with categories"])

@router.get("/")
async def get_groupcategory(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    
    # Get all category groups
    groups = await db["category_groups"].find({"user_id" : user_id}).to_list(length=None)
    
    result = []
    for group in groups:
        group["_id"] = str(group["_id"])
        
        # get categories for this group
        categories = await db["categories"].find({"user_id": user_id, "group_id" : group["_id"]}).to_list(length=None)

        for cat in categories:
            cat["_id"] = str(cat["_id"])
        
        group["categories"] = categories 
        result.append(group)
    
    return result

@router.get("/{categorygroup_id}")
async def get_cat_id(categorygroup_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    
    group_found = await db["category_groups"].find_one({"_id": ObjectId(categorygroup_id), "user_id" : user_id})
    
   
    if not group_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    group_found["_id"] = str(group_found["_id"])
    
    categories = await db["categories"].find({"group_id" : group_found["_id"]}).to_list(length=None)

    for cat in categories:
        cat["_id"] = str(cat["_id"])
    
    group_found["categories"] = categories
    
    return group_found