# AI Code Review Platform

A SaaS platform that delivers AI-powered code reviews, security scans, and architecture suggestions via GitHub PR webhooks.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12, SQLAlchemy 2.0 |
| Database | PostgreSQL 16 + Redis 7 |
| AI | OpenAI GPT-4o with custom prompt chains |
| Auth | GitHub OAuth + JWT (RS256) |
| Billing | Stripe Subscriptions |
| Deploy | GCP Cloud Run + GitHub Actions CI/CD |

## Project Structure

```
ai-code-review/
├── backend/          # FastAPI application
│   ├── app/
│   │   ├── api/v1/   # Route handlers
│   │   ├── core/     # Config, security, dependencies
│   │   ├── db/       # Database engine + session
│   │   ├── models/   # SQLAlchemy ORM models
│   │   ├── schemas/  # Pydantic request/response schemas
│   │   └── services/ # Business logic
│   ├── alembic/      # DB migrations
│   └── Dockerfile
├── frontend/         # Next.js application
│   ├── app/          # App Router pages
│   ├── components/   # React components
│   └── lib/          # API client, utilities
└── infra/            # Docker Compose + GCP configs
```

## Quick Start

```bash
# 1. Clone and enter
git clone <your-repo>
cd ai-code-review

# 2. Copy env files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

# 3. Start everything (Postgres + Redis + Backend + Frontend)
docker compose up --build

# 4. Run DB migrations
docker compose exec backend alembic upgrade head

# 5. Open
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
```

## Development Phases

- [x] Phase 1: Auth + DB scaffold
- [x] Phase 2: GitHub OAuth + Webhook
- [x] Phase 3: AI Review Engine
- [ ] Phase 4: Frontend Dashboard
- [ ] Phase 5: Stripe + GCP Deploy
