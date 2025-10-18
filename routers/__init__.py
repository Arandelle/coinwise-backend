from .gemini import router as ai_router
from .auth import router as auth

all_routers = [ai_router, auth]