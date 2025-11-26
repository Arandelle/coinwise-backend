from fastapi import FastAPI
from database import test_connection
from routers import all_routers

app = FastAPI(
    title="Coinwise API",
    description="FastAPI backend for coinwise",
    version="1.0.0"
    )

# include all routers
for router in all_routers:
    app.include_router(router)

@app.on_event("startup")
async def startup_db_client():
    await test_connection()

@app.get("/")
async def root():
    return {"message" : "Hi there!, Welcome to the Coinwise API. Visit /docs for API documentation."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)