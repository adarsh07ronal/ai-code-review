from fastapi import APIRouter
from app.api.v1.endpoints import auth, billing, github, organizations, repositories, reviews

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(github.router)
api_router.include_router(repositories.router)
api_router.include_router(reviews.router)
api_router.include_router(billing.router)
api_router.include_router(organizations.router)
