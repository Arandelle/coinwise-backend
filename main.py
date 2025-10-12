from fastapi import FastAPI, HTTPException
from database import db, test_connection
from models import Transaction
from bson import ObjectId

app = FastAPI()

@app.on_event("startup")
async def startup_db_client():
    await test_connection()

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
    new_tx = transaction.dict(by_alias=True, exclude_unset=True)
    result = await db["transactions"].insert_one(new_tx)
    created_tx = await db["transactions"].find_one({"_id": result.inserted_id})
    created_tx["_id"] = str(created_tx["_id"])
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
