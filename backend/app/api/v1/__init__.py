from fastapi import APIRouter
from app.api.v1.endpoints import auth, github, repositories, reviews

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(github.router)
api_router.include_router(repositories.router)
api_router.include_router(reviews.router)
