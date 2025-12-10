from fastapi import APIRouter, HTTPException, Depends, status, Query
from bson import ObjectId
from database import db
from models.transaction import Transaction
from utils.auth import get_current_user
from typing import Optional
from datetime import datetime, timedelta

router = APIRouter(prefix="/transactions", tags=["Transactions"])

# READ (user's own transactions only)
# Joining in category collection


@router.get("/")
async def get_my_transactions(
    current_user: dict = Depends(get_current_user),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Items per page"),

    # Filtering
    type: Optional[str] = Query(
        None, description="Filter by type: income or expense"),
    category_id: Optional[str] = Query(
        None, description="Filter by category ID"),
    date_from: Optional[str] = Query(
        None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date"),
    search: Optional[str] = Query(
        None, description="Search in transaction name or note"),

    # Sorting
    sort_by: str = Query("date", description="Sort by date, amount, name"),
    order: str = Query("desc", description="Sort order: desc or asc")
):

    user_id = current_user["_id"]

    # Build match conditions
    match_conditions = {"user_id": user_id}

    # Apply filters
    if type:
        match_conditions["type"] = type
    if category_id:
        match_conditions["category_id"] = category_id

    # Date Range
    if date_from or date_to:
        match_conditions["date"] = {}
        if date_from:
            match_conditions["date"]["$gte"] = datetime.fromisoformat(
                date_from)
        if date_to:
            match_conditions["date"]["$lte"] = datetime.fromisoformat(
                date_to) + timedelta(days=1)  # Include entire end date

    elif date_from and date_to:
        match_conditions["date"] = {
            "$gte": datetime.fromisoformat(date_from),
            # include entire end date
            "$lte": datetime.fromisoformat(date_to) + timedelta(days=1)
        }

    # Search filter (case-insensitive)
    if search:
        match_conditions["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"note": {"$regex": search, "$options": "i"}}
        ]

    # Sorting
    sort_order = -1 if order == "desc" else 1
    sort_field = sort_by if sort_by in ["date", "amount", "name"] else "date"

    # Baseline without pagination
    base_pipeline = [
        # Match the user's transactions with filters
        {"$match": match_conditions},

        # Convert category_id string to ObjectId, handle empty/null values
        {
            "$addFields": {
                "category_object_id": {

                    "$cond": {
                        "if": {
                            "$and": [
                              {"$ne": ["$category_id", ""]},
                              {"$ne": ["$category_id", None]}
                            ]
                        },
                        "then": {"$toObjectId": "$category_id"},
                        "else": None
                    }
                }
            }
        },
        # Join with categories collection
        {
            "$lookup": {
                "from": "categories",
                "localField": "category_object_id",
                "foreignField": "_id",
                "as": "category"
            }
        },

        # flatten an array from lookup result
        # into a single object
        {"$unwind": {
            "path": "$category",
            "preserveNullAndEmptyArrays": True
        }
        },

        # Convert group_id to ObjectId
        {
            "$addFields": {"group_object_id": {
                "$cond": {
                    "if": {"$ne": ["$category.group_id", None]},
                    "then": {"$toObjectId": "$category.group_id"},
                    "else": None
                }
            }
            }
        },

        # Join category_groups collection
        {
            "$lookup": {
                "from": "category_groups",
                "localField": "group_object_id",
                "foreignField": "_id",
                "as": "group"
            }
        },
        {"$unwind": {"path": "$group", "preserveNullAndEmptyArrays": True}},

        # Shape the final output
        {
            "$project": {
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
                        "$ifNull": [{"$toString": "$category_id"}, ""]
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

        # sort by specified field
        {"$sort": {sort_field: sort_order}},
    ]

    # if limit is none, return all data without pagination
    if limit is None:
        transactions = await db["transactions"].aggregate(base_pipeline).to_list(None)
        total_count = len(transactions)

        return {
            "transactions": transactions,
            "pagination": {
                "page": 1,
                "limit": None,
                "total": total_count,
                "total_pages": 1,
                "has_next": False,
                "has_prev": False
            }
        }

    # Otherwise, apply pagination with $facet
    skip = (page - 1) * limit

    pipeline = base_pipeline + [
        {
            '$facet': {
                "transactions": [
                    {"$skip": skip},
                    {"$limit": limit}
                ],
                "total_count": [
                    {"$count": "count"}
                ]
            }
        }
    ]

    result = await db["transactions"].aggregate(pipeline).to_list(None)
    transactions = result[0]["transactions"] if result else []
    total_count = result[0]["total_count"][0]["count"] if result and result[0]["total_count"] else 0

    return {
        "transactions": transactions,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total_count,
            "total_pages": (total_count + limit - 1) // limit,
            "has_next": page * limit < total_count,
            "has_prev": page > 1
        }
    }


@router.get("/summary")
async def get_transaction_summary(
    current_user: dict = Depends(get_current_user),
    mode: str = Query(
        "monthly",
        description="Time period. daily, weekly, monthly, yearly, custom, all",
        regex="^(daily|weekly|monthly|yearly|custom|all)$"
    ),
    month: Optional[int] = Query(
        None, ge=1, le=12, description="Month (1-12). If not provided, uses current month"),
    year: Optional[int] = Query(
        None, ge=2000, le=2100, description="Year for monthly/yearly mode. If not provided, uses current year"),
    date_from: Optional[str] = Query(
        None, description="Start date for custom mode (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(
        None, description="End date for custome mode (YYYY-MM-DD)")
):
    user_id = current_user["_id"]
    match_conditions = {"user_id": user_id}

    # Calculate date based on mode
    now = datetime.now()

    if mode == "daily":
        # Today only
        start_date = datetime(now.year, now.month, now.day)
        end_date = start_date + timedelta(days=1)

    elif mode == "weekly":
        # Current week (Mon - Sun)
        start_of_week = now - timedelta(days=now.weekday())
        start_date = datetime(start_of_week.year,
                              start_of_week.month, start_of_week.day)
        end_date = start_date + timedelta(days=7)

    elif mode == "monthly":
        # Specific month or current month
        target_year = year if year else now.year
        target_month = month if month else now.month

        start_date = datetime(target_year, target_month, 1)

        # Get first day of next month
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1)
        else:
            end_date = datetime(target_year, target_month + 1, 1)

    elif mode == "yearly":

        # Specific year or current year
        target_year = year if year else now.year
        start_date = datetime(target_year, 1, 1)
        end_date = datetime(target_year + 1, 1, 1)

    elif mode == "custom":
        # Custom date range
        if not date_from and not date_to:
            raise HTTPException(
                status_code=400,
                detail="date_from/date_to required for custom mode"
            )

        if date_from or date_to:
            start_date = datetime.fromisoformat(
                date_from) if date_from else datetime(2000, 1, 1)
            end_date = datetime.fromisoformat(
                date_to) + timedelta(days=1) if date_to else now + timedelta(days=1)
    elif mode == "all":
        # No date filter
        start_date = None
        end_date = None

    # Apply date filter if not in "all" mode
    if mode != "all":
        match_conditions["date"] = {}
        if start_date:
            match_conditions["date"]["$gte"] = start_date
        if end_date:
            match_conditions["date"]["$lte"] = end_date

    # Aggregation pipeline
    pipeline = [
        {"$match": match_conditions},
        {
            "$group": {
                "_id": None,
                "total_income": {
                    "$sum": {
                        "$cond": [{"$eq": ["$type", "income"]}, "$amount", 0]
                    }
                },
                "total_expense": {
                    "$sum": {
                        "$cond": [{"$eq": ["$type", "expense"]}, "$amount", 0]
                    }
                },
                "income_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$type", "income"]}, 1, 0]
                    }
                },
                "expense_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$type", "expense"]}, 1, 0]
                    }
                }
            }
        },

        {
            "$project": {
                "_id": 0,
                "total_income": 1,
                "total_expense": 1,
                "income_count": 1,
                "cash_flow": {
                    "$subtract": ["$total_income", "$total_expense"]
                },
                "expense_count": 1,
                "date_range": {
                    "from": start_date.strftime("%Y-%m-%d") if start_date else None,
                    "to": (end_date - timedelta(days=1)).strftime("$Y-%m-%d") if end_date else None
                }
            }
        }
    ]

    result = await db["transactions"].aggregate(pipeline).to_list(1)

    # Prepare response with date range info

    response = result[0] if result else {
        "total_income": 0,
        "total_expense": 0,
        "cash_flow": 0,
        "income_count": 0,
        "expense_count": 0,
        "date_range": {
            "from":  None,
            "to": None
        }
    }

    return response


# ✅ READ ONE (user's own transactions only)


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: str, current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    pipeline = [
        # Match user id and transaction id
        {"$match": {
            "user_id": user_id,
            "_id": ObjectId(transaction_id)
        }},

        # addField - Convert category_id string to ObjectId, handle empty/null values
        {
            "$addFields": {
                "category_object_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$ne": ["$category_id", ""]},
                                {"$ne": ["$category_id", None]}
                            ]
                        },
                        "then": {"$toObjectId": "$category_id"},
                        "else": None
                    }
                }
            }
        },
        # look up - Join with categories collection
        {
            "$lookup": {
                "from": "categories",
                "localField": "category_object_id",
                "foreignField": "_id",
                "as": "category"
            }
        },

        # unwind - flatten an array from lookup result
        # into a single object
        {
            "$unwind": {
                "path": "$category",
                "preserveNullAndEmptyArrays": True
            }
        },

        # addField - Convert group_id to object id
        {
            "$addFields": {"group_object_id": {
                "$cond": {
                    "if": {"$ne": ["$category.group_id", None]},
                    "then": {"$toObjectId": "$category.group_id"},
                    "else": None
                }
            }
            }
        },

        # Join category_groups collection
        {
            "$lookup": {
                "from": "category_groups",
                "localField": "group_object_id",
                "foreignField": "_id",
                "as": "group"
            }
        },
        {"$unwind": {"path": "$group", "preserveNullAndEmptyArrays": True}},


        # Shape the final output
        {
            "$project": {
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
                        "$ifNull": [{"$toString": "$category_id"}, ""]
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
        {"$sort": {"date": -1}}
    ]

    # check if transaction exist AND belongs to user
    existing_transaction = await db["transactions"].aggregate(pipeline).to_list(1)

    if not existing_transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or you don't have access"
        )

    return existing_transaction[0]


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
        "user_id": user_id
    })

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or you don't have access"
        )

    updated_tx = transaction.dict(
        by_alias=True, exclude_none=True, exclude={"_id", "created_at"})

    # prevent user from changing the user_id to someone else's
    result = await db["transactions"].update_one(
        {"_id": ObjectId(transaction_id),
         "user_id": user_id
         },
        {"$set": updated_tx}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED,
                            detail="Transaction not found or unchanged")

    updated = await db["transactions"].find_one({"_id": ObjectId(transaction_id)})
    updated["_id"] = str(updated["_id"])
    return updated

# ✅ DELETE


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(transaction_id: str, current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    # delete only if transactions belongs to user
    result = await db["transactions"].delete_one({"_id": ObjectId(transaction_id), "user_id": user_id})

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    return None
