from .gemini import router as ai_router
from .auth import router as auth
from .transactions import router as transactions

all_routers = [ai_router, auth, transactions]