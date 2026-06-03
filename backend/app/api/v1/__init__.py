from fastapi import APIRouter
from app.api.v1.endpoints import auth

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)

# Phase 2: GitHub webhook
# from app.api.v1.endpoints import github
# api_router.include_router(github.router)

# Phase 3: Reviews
# from app.api.v1.endpoints import reviews
# api_router.include_router(reviews.router)

# Phase 4: Repositories
# from app.api.v1.endpoints import repositories
# api_router.include_router(repositories.router)
