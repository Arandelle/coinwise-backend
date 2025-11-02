from .gemini import router as ai_router
from .auth import router as auth
from .transactions import router as transactions
from .category import router as category
from .categoryGroup import router as categoryGroup

all_routers = [ai_router, auth, transactions, category, categoryGroup]