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
| Realtime | WebSockets (Redis pub/sub fan-out across replicas) |
| Deploy | AWS ECS Fargate + ALB + auto-scaling, Terraform, GitHub Actions CI/CD |

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
└── infra/
    └── terraform/    # AWS ECS/RDS/ElastiCache/ALB — see Deployment below
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

## Deployment

Infrastructure lives in [`infra/terraform`](infra/terraform) — VPC, ECS Fargate services (backend + frontend) behind an ALB, RDS Postgres, ElastiCache Redis, and target-tracking auto-scaling on CPU/memory/ALB-requests-per-target.

```bash
cd infra/terraform
terraform init
terraform plan -var db_password=... -var app_secret_key=...
```

CI/CD is split across three workflows:

- **`.github/workflows/ci.yml`** — lint/type-check/build on every push and PR.
- **`.github/workflows/cd.yml`** — on merge to `master`, builds and pushes backend/frontend images to ECR (doesn't touch live infra).
- **`.github/workflows/deploy.yml`** — manually triggered (`workflow_dispatch`) `terraform apply` that rolls the chosen image tag out to ECS. Kept manual and gated behind a GitHub Environment on purpose — an infra rollout is a decision, not an automatic side effect of merging.

## Development Phases

- [x] Phase 1: Auth + DB scaffold
- [x] Phase 2: GitHub OAuth + Webhook
- [x] Phase 3: AI Review Engine
- [x] Phase 4: Real-time review delivery (WebSockets)
- [x] Phase 5: Multi-tenant orgs, RBAC, Stripe billing
- [x] Phase 6: AWS ECS deploy, auto-scaling, GitHub Actions CI/CD
