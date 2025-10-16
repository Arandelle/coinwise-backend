from fastapi import FastAPI, HTTPException
from database import db, test_connection
from models import Transaction
from bson import ObjectId
from routers import all_routers

app = FastAPI()

# include all routers
for router in all_routers:
    app.include_router(router)

@app.on_event("startup")
async def startup_db_client():
    await test_connection()

@app.get("/")
async def root():
    return {"message" : "Welcome to the Coinwise API. Visit /docs for API documentation."}

# ✅ READ ALL
@app.get("/transactions")
async def get_transactions():
    transactions = await db["transactions"].find().to_list(length=100)
    for tx in transactions:
        tx["_id"] = str(tx["_id"])
    return transactions

# ✅ READ ONE
@app.get("/transactions/{transaction_id}")
async def get_transaction(transaction_id: str):
    transaction = await db["transactions"].find_one({"_id": ObjectId(transaction_id)})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    transaction["_id"] = str(transaction["_id"])
    return transaction

# ✅ CREATE
@app.post("/transactions")
async def create_transaction(transaction: Transaction):
    # ✅ Convert the Pydantic model to a Python dict
    #    - by_alias=True → use MongoDB field name "_id" instead of "id"
    #    - exclude_unset=True → skip fields that weren’t provided
    new_tx = transaction.dict(by_alias=True, exclude_unset=True)

    # ✅ Insert the document into the "transactions" collection
    #    - MongoDB automatically generates an "_id" since it’s missing
    result = await db["transactions"].insert_one(new_tx)

    # ✅ Retrieve the newly inserted document using the generated "_id"
    created_tx = await db["transactions"].find_one({"_id": result.inserted_id})

    # ✅ Convert MongoDB's ObjectId to string for JSON serialization
    created_tx["_id"] = str(created_tx["_id"])

    # ✅ Return the created document as the API response
    return created_tx


# ✅ UPDATE
@app.put("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, transaction: Transaction):
    updated_tx = transaction.dict(by_alias=True, exclude_unset=True)
    result = await db["transactions"].update_one(
        {"_id": ObjectId(transaction_id)}, {"$set": updated_tx}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found or unchanged")

    updated = await db["transactions"].find_one({"_id": ObjectId(transaction_id)})
    updated["_id"] = str(updated["_id"])
    return updated

# ✅ DELETE
@app.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str):
    result = await db["transactions"].delete_one({"_id": ObjectId(transaction_id)})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Transaction deleted successfully"}
