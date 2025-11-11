from fastapi import APIRouter,HTTPException, Depends, status
from bson import ObjectId
from database import db
from models.transaction import Transaction
from utils.auth import get_current_user

router = APIRouter(prefix="/transactions", tags=["Transactions"])

# READ (user's own transactions only)
# Joining in category collection
@router.get("/")
async def get_my_transactions(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]
    
    pipeline = [
        # Match the user's transactions
        {"$match" : {"user_id" : user_id}},
        
        # Convert category_id string to ObjectId, handle empty/null values
        {
            "$addFields" : {
                "category_object_id" : {
                    
                    "$cond" : {
                      "if" : {
                          "$and" : [
                              {"$ne" : ["$category_id", ""]},
                              {"$ne" : ["$category_id", None]}
                          ]
                      },
                    "then" : {"$toObjectId" : "$category_id"},
                    "else" : None  
                    }
                }
            }
        },
        # Join with categories collection
        {
            "$lookup" :{
                "from" : "categories",
                "localField" : "category_object_id",
                "foreignField" : "_id",
                "as" : "category"
            }
        },
        {"$unwind" : {
                "path" : "$category",
                "preserveNullAndEmptyArrays" : True
            }
        },
        
        # Convert group_id to ObjectId
        {
            "$addFields" : {"group_object_id" : { 
                "$cond" : {
                    "if" : {"$ne" : ["$category.group_id", None]},
                    "then" : {"$toObjectId" : "$category.group_id"},
                    "else" : None
                    }
                }
            }
        },
        
        # Join category_groups collection
        {
            "$lookup" :{
                "from" : "category_groups",
                "localField" : "group_object_id",
                "foreignField" : "_id",
                "as" : "group"
            }
        },
        {"$unwind" : {"path" : "$group", "preserveNullAndEmptyArrays" : True}},
        
        # Shape the final output
        {
            "$project" : {
                "_id": {"$toString": "$_id"},
                "user_id": 1,
                "category_id": 1,
                "name": 1,
                "amount": 1,
                "type": 1,
                "label": 1,
                "note": 1,
                "balance_after": 1,
                "date": 1,
                "date_only": 1,
                "created_at": 1,
                
                # Add enriched category details
                "category_details": {
                    "id": {
                        "$ifNull" : [{"$toString" : "$category_id"}, ""]    
                    },
                   "name": {
                        "$ifNull": ["$category.category_name", "Others"]
                    },
                    "icon": {
                        "$ifNull": ["$category.icon", ""]
                    },
                    "type": {
                        "$ifNull": ["$category.type", "$type"]
                    },
                    "group_id": {
                        "$ifNull": ["$category.group_id", ""]
                    },
                    "group_name": {
                        "$ifNull": ["$group.group_name", "Others"]
                    }
                }
            }
        },
        
        # sort by date (newest first)
        {"$sort" : {"date" : -1}}
    ]
    transactions = await db["transactions"].aggregate(pipeline).to_list(None)
    return transactions

# ✅ READ ONE (user's own transactions only)
@router.get("/{transaction_id}")
async def get_transaction(transaction_id: str, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]
    
    pipeline = [
        {"$match" : {"user_id" : user_id}},
    ]
    
    # check if transaction exist AND belongs to user
    existing_transaction = await db["transactions"].find_one({
        "_id" : ObjectId(transaction_id),
        "user_id" : user_id
    })
    
    if not existing_transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or you don't have access"
        )
    
    existing_transaction["_id"] = str(existing_transaction["_id"])
    return existing_transaction    



# ✅ CREATE - automatically assign to current user
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_transaction(transaction: Transaction, current_user: dict = Depends(get_current_user)):
    
    # ✅ Convert the Pydantic model to a Python dict
    #    - by_alias=True → use MongoDB field name "_id" instead of "id"
    #    - exclude_unset=True → skip fields that weren’t provided
    new_tx = transaction.dict(by_alias=True, exclude_none=True)

    # force the user_id to be the authenticated user (prevent spoofing)
    new_tx["user_id"] = current_user["_id"]
    
    # ✅ Insert the document into the "transactions" collection
    #    - MongoDB automatically generates an "_id" since it’s missing
    result = await db["transactions"].insert_one(new_tx)

    # ✅ Retrieve the newly inserted document using the generated "_id"
    created_tx = await db["transactions"].find_one({"_id": result.inserted_id})

    # ✅ Convert MongoDB's ObjectId to string for JSON serialization
    created_tx["_id"] = str(created_tx["_id"])

    # ✅ Return the created document as the API response
    return created_tx



# ✅ UPDATE - user's own transactions only
@router.put("/{transaction_id}")
async def update_transaction(
    transaction_id: str, 
    transaction: Transaction, 
    current_user: dict = Depends(get_current_user)
    ):
    
    user_id = current_user["_id"]
    
    # check if transaction exist AND belongs to user
    existing = await db["transactions"].find_one({
        "_id": ObjectId(transaction_id),
        "user_id" : user_id
    })
    
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or you don't have access"
        )
    
    updated_tx = transaction.dict(by_alias=True,exclude_none=True, exclude={"_id", "created_at"})
    
    # prevent user from changing the user_id to someone else's
    result = await db["transactions"].update_one(
        {"_id": ObjectId(transaction_id),
         "user_id" : user_id
        }, 
        {"$set": updated_tx}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED, detail="Transaction not found or unchanged")

    updated = await db["transactions"].find_one({"_id": ObjectId(transaction_id)})
    updated["_id"] = str(updated["_id"])
    return updated

# ✅ DELETE
@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(transaction_id: str, current_user: dict = Depends(get_current_user)):
    
    user_id = current_user["_id"]

    # delete only if transactions belongs to user
    result = await db["transactions"].delete_one({"_id": ObjectId(transaction_id), "user_id" : user_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return None
