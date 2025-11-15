from .gemini import router as ai_router
from .auth import router as auth
from .transactions import router as transactions
from .category import router as category
from .categoryGroup import router as categoryGroup
from .groupWithCategory import router as groupWithCategory
from .accountbalance import router as accountBalance

all_routers = [ai_router, auth, transactions, category, categoryGroup, groupWithCategory, accountBalance]