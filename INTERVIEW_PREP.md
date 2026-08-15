# Interview Prep — AI Code Review Platform

Chapter-by-chapter prep for talking through this project. Each chapter covers
one development phase: easy questions (say these fast, no hesitation),
medium questions (expect a follow-up), and a couple of real challenges you
hit while building it, with the trade-off you accepted and why.

Branches referenced below (in case a question asks "is this merged"):
- `master` — Phases 1–3
- `feat/websocket-realtime-reviews` — Phase 4
- `feat/multitenant-billing-rbac` — Phase 5
- `feat/aws-ecs-cicd` — Phase 6

---

## Chapter 1 — Auth + Database Scaffold

**Stack:** FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, JWT via `python-jose`, `passlib`/bcrypt for password hashing.

### Easy

**Q: Why JWT instead of server-side sessions?**
Stateless — no session store to keep in sync once you have multiple backend replicas (which this app does, behind the ALB in Phase 6). The token carries the user id (`sub` claim) and an expiry; any replica can verify it without a shared session table.

**Q: Access token vs refresh token — why two?**
Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, 24h here) and sent on every request, so keeping them short limits the damage if one leaks. The refresh token (30 days) is only sent to `/auth/refresh` to mint a new access token, so it's exposed far less often.

**Q: Where are passwords hashed?**
`security.py`, using `passlib`'s `CryptContext(schemes=["bcrypt"])`. Bcrypt is deliberately slow (adaptive cost factor) to make brute-forcing expensive — this is the standard choice over something fast like SHA-256, which is the wrong tool for password storage.

**Q: What's `CREDENTIALS_EXCEPTION`?**
A shared `HTTPException(401)` raised for any auth failure — expired token, malformed token, wrong token type, user not found. Returning a generic 401 message for all these cases is intentional: you don't want the API telling an attacker whether a *specific* email exists vs. whether their token is just malformed.

### Medium

**Q: Walk me through what happens when a request hits a protected endpoint.**
FastAPI's dependency injection resolves `Depends(get_current_user)`. That pulls the `Authorization: Bearer <token>` header via `HTTPBearer(auto_error=False)`, decodes it with `decode_token()` (verifies signature + expiry via `jose.jwt.decode`), checks `payload["type"] == "access"` (so a refresh token can't be used as an access token), extracts `sub` as the user id, then loads the `User` row from Postgres. Every layer can fail with a 401/403 independently.

**Q: Why check `payload["type"] == "access"` explicitly instead of just trusting any valid signature?**
Because both access and refresh tokens are signed with the same `SECRET_KEY` and would both pass signature verification. Without the type check, a leaked refresh token (30-day lifetime) could be used directly as an API credential instead of only being exchangeable for a short-lived access token — that defeats the entire point of having two token types.

**Q: `bcrypt` has a 72-byte input limit. How does this codebase handle that?**
`hash_password()` explicitly checks `len(password.encode("utf-8")) > 72` and raises a 422 before it ever reaches `passlib`. If you don't do this, bcrypt silently truncates the password, which means `"correcthorsebatterystaple" + anything past byte 72` all hash to the same value — a subtle security bug that's easy to miss because it doesn't error, it just quietly does the wrong thing.

**Q: The `Organization` / `OrganizationMember` tables exist in `models/review.py` from Phase 1, but nothing used them until Phase 5. Why build the schema early?**
It's a judgment call, not a rule — building schema ahead of the feature that uses it works when the shape is already well-understood (an org has members, members have one of three roles) and low-risk to get right early, versus when you're still exploring the domain, where premature schema tends to need painful migrations later. Here it paid off: Phase 5 was mostly wiring up endpoints and RBAC checks against a schema that was already correct, not designing + migrating + wiring in the same PR.

### Challenges

**Challenge: Async SQLAlchemy sessions and background tasks don't mix safely.**
FastAPI's `Depends(get_db)` yields a session scoped to one HTTP request and closes it after. `review_worker.py` (Phase 3) runs as a detached `asyncio.create_task`, outliving the request that triggered it — so it can't reuse the request-scoped session.
- **Solution:** `ReviewWorker.run()` opens its own session directly from `AsyncSessionFactory()` instead of going through the `get_db` dependency.
- **Trade-off:** two different session-acquisition patterns in the codebase (`Depends(get_db)` for routes, `AsyncSessionFactory()` directly for background work) — a new contributor has to know why they're different, since it's not visually obvious that one runs inside a request lifecycle and the other doesn't.
- **Benefit:** the background job's DB session lives exactly as long as the job does, with no risk of a route handler's `finally: await session.close()` yanking the connection out from under a task that's still running the AI review.

---

## Chapter 2 — GitHub OAuth + Webhooks

### Easy

**Q: What OAuth flow does this use?**
Standard OAuth Authorization Code flow: redirect the user to GitHub's `/login/oauth/authorize`, GitHub redirects back with a `code`, the backend exchanges that code server-side for an access token (`auth_service.github_exchange_code`). The access token never touches the browser directly during that exchange.

**Q: How does the backend know a webhook payload really came from GitHub?**
HMAC-SHA256 signature verification (`github.py:verify_webhook_signature`). GitHub signs the raw request body with a shared secret (`GITHUB_WEBHOOK_SECRET`) and sends it as `X-Hub-Signature-256`. The backend recomputes the HMAC over the same bytes and compares with `hmac.compare_digest` — a constant-time comparison, not `==`, specifically to avoid timing attacks that could let someone guess the signature byte-by-byte.

**Q: Why does the webhook handler return 200 immediately instead of waiting for the AI review to finish?**
GitHub expects a fast response and will retry (and eventually disable) a webhook that times out. `queue_review()` just does `asyncio.create_task(review_worker.run(pr.id))` and returns — the actual review runs independently in the background.

### Medium

**Q: What's the actual security property `hmac.compare_digest` buys you over `==`?**
Python's `==` on strings short-circuits at the first mismatched byte, so the time it takes to compare is a signal about *how many leading bytes matched*. An attacker who can measure response timing precisely enough could exploit that to recover the correct signature one byte at a time. `compare_digest` always takes the same time regardless of where the mismatch is, so there's no timing signal to exploit.

**Q: `queue_review` fires an `asyncio.create_task` and returns. What happens if that task raises an exception nobody's awaiting?**
Left unhandled, it'd be swallowed as an "exception never retrieved" warning and the PR would silently stay in `PENDING` forever. That's exactly why `ReviewWorker.run()` wraps the whole pipeline in try/except and calls `_mark_failed()` in the except block — the task is fire-and-forget from the webhook handler's side, but it self-reports failure into the database (and, since Phase 4, over the WebSocket) rather than failing silently.

**Q: Why store `github_access_token` on the `User` row instead of somewhere else?**
It's what's used to call the GitHub API on the user's behalf (fetch diffs, post review comments) — `review_worker.py` looks up the repo owner specifically to get this token. The trade-off is that a long-lived token sits in the primary database rather than a secrets manager; for a real production system you'd want to encrypt it at rest or move it to something like Secrets Manager, which is exactly the kind of thing the Phase 6 Terraform does for the *application's own* secrets but doesn't (yet) do for *user* GitHub tokens.

### Challenges

**Challenge: Webhook delivery is at-least-once, not exactly-once.**
GitHub retries webhooks that don't get acknowledged fast enough or that fail. A naive handler would create a duplicate `PullRequest` row (or trigger a duplicate AI review, burning OpenAI tokens) every time the same event got redelivered.
- **Solution:** `handle_pull_request_event` looks up the existing `PullRequest` by `github_pr_id` (which has a `unique=True` constraint) before deciding whether to insert or update.
- **Trade-off:** every webhook event does a DB read before any write, adding a small amount of latency to a path that's already trying to be fast for GitHub's sake.
- **Benefit:** idempotency — replaying the same webhook event any number of times converges to the same DB state instead of piling up duplicate reviews.

---

## Chapter 3 — AI Review Engine

### Easy

**Q: Which model does this use and why GPT-4o specifically?**
`OPENAI_MODEL` defaults to `gpt-4o` — good code-reasoning quality with lower latency/cost than the largest reasoning models, which matters here because review latency directly affects developer experience (nobody wants to wait 3 minutes for a PR comment).

**Q: What does the AI actually return — free text or something structured?**
Structured JSON: `summary`, `findings` (file/line/severity/message/suggestion), `security_issues`, `architecture_suggestions`, `overall_quality`. `review_worker.py` counts severities out of that structure (`critical_count`, `warning_count`, `info_count`) rather than trying to parse them out of prose.

**Q: Where does the review end up?**
Two places: persisted as a `CodeReview` row in Postgres (so the dashboard can show history), and — if the repo's `review_config.auto_post` is true — formatted as Markdown and posted back as an actual GitHub PR review comment via `github_service.post_review_comment`.

### Medium

**Q: Why structured JSON output instead of just asking the model to write a nice comment directly?**
Two different consumers need two different shapes from the same review: the dashboard wants queryable severity counts and per-finding metadata, GitHub wants a nicely formatted Markdown comment. Structured JSON lets `_format_github_comment()` render the Markdown from the same data that populates `critical_count`/`warning_count` in the DB — one AI call, two presentations, instead of asking the model twice or fragile-parsing a comment string back into structured data.

**Q: What happens if `post_review_comment` fails — does the whole review fail?**
No — it's wrapped in its own try/except inside `_process()`, separate from the outer pipeline try/except. A GitHub API hiccup while posting the comment logs a warning but doesn't roll back the `CodeReview` row that's already been persisted, and doesn't flip the PR to `FAILED`. The review itself succeeded; only the "tell GitHub about it" step didn't, and that's a meaningfully different failure than "the AI call itself failed."

**Q: `review_worker.py` counts severities with `sum(1 for f in findings + security if ...)`. Any concerns with that at scale?**
It's fine at the size these lists actually are (a PR review producing thousands of findings would be useless to a human anyway), but it's doing three passes over the combined list for three severities. Not a real bottleneck here — worth mentioning if asked to nitpick, but not worth "fixing" pre-emptively into a single-pass counter given how small `findings` realistically is.

### Challenges

**Challenge: LLM output isn't guaranteed to be valid, well-formed JSON matching your schema.**
Even asking for JSON, the model can occasionally return malformed output, omit a field, or use an unexpected severity string.
- **Solution:** the code defensively uses `.get()` with defaults everywhere it reads from `review_data` (`review_data.get("findings", [])`, `f.get("severity", "info")`) instead of direct dict indexing — so a missing field degrades gracefully (empty list, default severity) rather than throwing a `KeyError` mid-pipeline.
- **Trade-off:** you lose an immediate, loud failure if the model's output format drifts — a `KeyError` would tell you fast; silent defaulting could mask a real regression in prompt quality until someone notices reviews look thinner than expected.
- **Benefit:** one malformed AI response doesn't take down the whole pipeline or leave a PR stuck in `REVIEWING` — worse review quality is a much better failure mode than a 500.

---

## Chapter 4 — Real-Time Delivery (WebSockets)

*This was the feature I built to close the "real-time review delivery via WebSockets" gap in the original resume bullet — the platform existed but reviews only showed up if you refreshed the page.*

### Easy

**Q: Why WebSockets instead of polling?**
A review can take anywhere from a few seconds to over a minute depending on diff size. Polling means either hammering the API every couple seconds (wasteful, and adds load precisely when the backend is already busy running the AI pipeline) or a noticeably laggy UI. A WebSocket push means the dashboard updates the instant `review_worker` finishes a stage — no polling interval to tune.

**Q: How does the frontend authenticate the WebSocket connection?**
The JWT access token is passed as a query parameter: `/api/v1/ws/reviews?token=<jwt>`. Browsers can't attach custom headers (like `Authorization: Bearer`) to the WebSocket handshake request, so query param is the standard workaround. The server decodes it with the same `decode_token()` used everywhere else and closes the socket with code `1008` (policy violation) if it's invalid.

**Q: What happens on the frontend if the connection drops?**
`useReviewEvents.ts` reconnects automatically with exponential backoff (starts at 1s, doubles up to a 15s cap) rather than either reconnecting instantly in a tight loop (hammers the server during an outage) or not reconnecting at all (user has to manually refresh).

### Medium

**Q: The backend runs multiple ECS replicas behind an ALB (Phase 6). A naive in-memory `dict` of WebSocket connections breaks in that setup — why, and what's done instead?**
If `review_worker` finishes processing a PR on replica A, but the client's WebSocket is connected to replica B, an in-memory dict on replica A has no way to reach that client — it doesn't even know the connection exists. `ws_manager.py` solves this by having every replica subscribe to a shared Redis pub/sub channel (`ws:review-events`). `publish()` doesn't touch local sockets at all — it always goes through Redis, and every replica's `_listen()` loop picks up the message and dispatches it to whichever locally-connected sockets match that `user_id`. It works correctly with one replica or fifty without any code change.

**Q: Why publish through Redis unconditionally, even in a single-replica dev setup where it isn't strictly needed?**
Two reasons. One: it's the *same code path* in dev and production, so there's no "works locally, breaks in prod" surprise the first time it actually runs behind two ECS tasks. Two: Redis was already a hard dependency (session/cache), so this doesn't add new infrastructure — it reuses what's there instead of building two different connection-manager implementations gated behind an environment flag.

**Q: Sticky sessions were added to the ALB target group in Phase 6, specifically called out for the backend. Why does a Redis pub/sub design still need that?**
Redis pub/sub solves "which replica needs to deliver this event" — it doesn't change the fact that a WebSocket is a long-lived TCP connection pinned to whichever replica accepted it. If the ALB round-robins a *reconnect* to a different task than the one holding the original session context mid-handshake, that's not itself broken (this endpoint is stateless per-connection — auth is just a JWT, no server-side session), but sticky sessions plus a generous `deregistration_delay` (60s) specifically protect against ECS killing an old task mid-deploy and abruptly cutting active WebSocket connections instead of letting them drain.

### Challenges

**Challenge: verifying a WebSocket feature is much harder than verifying a REST endpoint — you can't just `curl` it.**
There was no live GitHub webhook flowing through the dev stack to trigger a real review and prove the event actually reaches the browser.
- **Solution:** published a fake event directly onto the Redis channel from the CLI (`redis-cli PUBLISH ws:review-events '{"user_id": 1, "type": "review_completed", ...}'`) and watched it show up live in the dashboard's accessibility-tree snapshot. This exercises the exact same code path `review_worker` would use — `ws_manager`'s listener doesn't know or care whether the publish came from the app or a raw redis-cli command.
- **Trade-off:** this proves the transport (Redis → backend listener → WebSocket → UI) works, but it doesn't exercise the *real* trigger path from an actual GitHub webhook through the AI pipeline to the publish call — that would need a real OpenAI key and a real webhook delivery, neither of which were available in this environment.
- **Benefit:** fast, deterministic, repeatable verification of the part of the system that was actually new and risky (multi-replica fan-out), without being blocked on external services that weren't in scope to configure.

---

## Chapter 5 — Multi-Tenant Orgs, RBAC, and Stripe Billing

*The `Organization`/`OrganizationMember`/`OrgRole` schema already existed from Phase 1 (see Chapter 1) but had zero endpoints and zero enforcement — this phase wired it up.*

### Easy

**Q: What are the three roles and what can each do?**
`OWNER`, `ADMIN`, `MEMBER`. Owner and admin can invite/remove members and change roles; members can only view. An owner's role can never be changed or removed via the API — every mutating endpoint explicitly checks for and blocks that (`if member.role == OrgRole.OWNER: raise HTTPException(400, ...)`), so an org can't accidentally end up without an owner.

**Q: How does Stripe Checkout know which plan the user picked?**
The tier (`"pro"` or `"team"`) is attached as `metadata` on the Checkout Session *and* on `subscription_data.metadata` when the session is created. Stripe copies that metadata onto the resulting Subscription object, so both the initial `checkout.session.completed` webhook and any later `customer.subscription.updated` webhook (e.g. from a plan change in the customer portal) carry the tier directly — no separate lookup needed.

**Q: What's the customer portal, and why offer it instead of building a "cancel subscription" page?**
Stripe's hosted billing portal — handles plan changes, cancellation, and payment method updates without the app needing to build or PCI-scope any of that UI itself. `create_portal_session()` just asks Stripe for a URL and redirects the user there.

### Medium

**Q: Why carry the tier in Checkout/Subscription metadata instead of mapping Stripe price IDs back to tiers?**
An inverse map (`price_xyz → "pro"`) has to be kept in sync by hand every time someone changes a price in the Stripe dashboard, and silently goes stale if they forget — the webhook would then either upgrade someone to the wrong tier or do nothing at all. Metadata is set once, at Checkout creation time, from the same `tier` variable the endpoint already validated (`if data.tier not in ("pro", "team")`) — there's no second source of truth that can drift from the first.

**Q: Walk me through how `require_org_role` enforces RBAC — what actually stops a plain member from inviting someone?**
It's a dependency factory: `require_org_role(OrgRole.OWNER, OrgRole.ADMIN)` returns an async function that itself depends on `get_org_membership` (which 403s outright if the caller isn't a member of that org at all), then checks `if membership.role not in allowed_roles: raise HTTPException(403)`. FastAPI resolves this *before* the endpoint body runs at all — a member calling `POST /organizations/{id}/members` never reaches the invite logic; the dependency graph rejects them first. This was verified directly: registered a fresh user, added them as a plain `member`, and confirmed their own invite attempt came back 403.

**Q: What stops someone from inviting a new member directly as `owner`?**
Explicit check in `invite_member`: `if data.role == OrgRole.OWNER: raise HTTPException(400, "Cannot invite a member directly as owner")`. Combined with `update_member_role` also refusing to touch an existing owner's role, there's exactly one way to become an owner — creating the org — and no way to make someone else one after the fact through this API surface. That's a deliberate simplification (no "transfer ownership" flow yet), not an oversight.

### Challenges

**Challenge (the good story — use this one for "tell me about a bug you found"): a pre-existing auth-guard race condition.**
While manually verifying the new billing/team pages, a full browser refresh on `/dashboard`, `/dashboard/billing`, or `/dashboard/team` intermittently bounced a logged-in user straight back to `/auth/login` — even with a perfectly valid token sitting in `localStorage`.
- **Root cause:** the Zustand auth store's `loading` flag started as `false`. The page's redirect effect — `if (!loading && !user) router.replace("/auth/login")` — ran on mount using that initial `false`/`null` state, *before* `loadMe()`'s async fetch had a chance to resolve and flip `loading` to `true`. It's a classic React effect-ordering race: two `useEffect`s fire in the same commit, one kicks off an async check, the other reads stale state from before that check started.
- **Solution:** added an explicit `checked: boolean` field to the auth store, set `true` only once `loadMe()` has actually completed (success *or* failure — including the "no token at all" case). The redirect effect changed from `if (!loading && !user)` to `if (checked && !user)` — it now waits for a definitive answer instead of racing an in-flight request.
- **Trade-off:** one more piece of state to keep in sync (`loading`, `checked`, and `user` all have to move together correctly), and every page using the guard pattern had to be updated in lockstep — a missed page would still have the bug.
- **Benefit:** this was a pattern copied into two brand-new pages from the original dashboard page — fixing it once at the store level, rather than patching each page's local effect logic, meant all three pages (and any future page reusing the same guard) got the fix for free.
- **Why this is worth bringing up in an interview:** it wasn't something the task asked for — it surfaced during manual verification of an unrelated feature, and shipping the two new pages without noticing it would have meant landing a subtly broken login experience. Good story for "how do you handle finding something out of scope."

---

## Chapter 6 — AWS ECS, Auto-Scaling, and CI/CD

*Written as Terraform + GitHub Actions, validated with `terraform validate`/`plan` and local YAML parsing — no live AWS account was used, so nothing here has actually been deployed. Say that up front if asked; don't overclaim "I deployed this to production."*

### Easy

**Q: Why ECS Fargate instead of EKS (Kubernetes) or EC2?**
Fargate is serverless containers — no EC2 instances or Kubernetes control plane to patch and manage. For a project this size, Kubernetes' extra flexibility (custom schedulers, operators, multi-cluster) isn't needed, and it comes with real operational overhead that isn't worth paying for two services and a straightforward scaling story.

**Q: What's the auto-scaling actually scaling on?**
Three target-tracking policies on the backend service: CPU utilization (60%), memory utilization (75%), and ALB requests-per-target (1000). Frontend just scales on CPU, since it's a stateless Next.js server with no long-lived connections.

**Q: Why does the backend get a third scaling metric (ALB requests) that the frontend doesn't?**
Because of the WebSocket work in Chapter 4 — a burst of concurrent long-lived WebSocket connections can tie up backend task capacity without necessarily spiking CPU or memory (a connection can just be idle, waiting for the next event). Request-count-per-target catches that kind of load that CPU/memory-based scaling alone would miss.

### Medium

**Q: How do secrets (DB password, JWT signing key, OpenAI/Stripe keys) get into the running containers?**
AWS Secrets Manager, not plain environment variables in the task definition. The ECS task execution role has an inline IAM policy scoped to exactly one secret ARN (`secretsmanager:GetSecretValue` on the backend secret only), and the container definition references each key with `valueFrom: "${secret_arn}:${key}::"` — ECS resolves that at container start, so the values never appear in the Terraform state's task-definition JSON as plaintext the way a plain `environment` block would.

**Q: Why does the Terraform `aws_secretsmanager_secret_version` have `lifecycle { ignore_changes = [secret_string] }`?**
`terraform apply` creates the secret with placeholder values so the very first apply doesn't fail on a missing resource, but real values (GitHub client secret, OpenAI key, Stripe keys) get set out-of-band with `aws secretsmanager put-secret-value` after deploy — those are never meant to live in `terraform.tfvars` or git. Without `ignore_changes`, every subsequent `terraform apply` would see the live secret value differs from what's in the `.tf` file and try to stomp it back to the placeholder, undoing whatever was set manually.

**Q: A subtle one — does setting `NEXT_PUBLIC_API_URL` as an ECS task environment variable actually work for a Next.js app?**
No, and this was worth catching before it became a "works in Terraform plan, breaks in prod" surprise. Next.js inlines any `NEXT_PUBLIC_*` variable into the client JS bundle *at build time* — by the time the container is running, `.next/static` is already compiled and that env var is baked into static files, not read at runtime. Setting it as an ECS runtime env var has zero effect on an already-built bundle. The actual fix is in `frontend/Dockerfile`: `ARG NEXT_PUBLIC_API_URL` in the `builder` stage, set before `RUN npm run build`, and the CD workflow passes it via `docker build --build-arg`. The runtime ECS env var is still set for parity/documentation, but a comment in `ecs.tf` explicitly flags that it's the build arg that matters.

**Q: Why is `deploy.yml` (`terraform apply`) a manual `workflow_dispatch` instead of running automatically on merge to master, when `cd.yml` (build + push images) does run automatically?**
Building and pushing an image to ECR is low-risk and easily reversible — it's just an artifact sitting in a registry until something references it. Actually rolling that image out to production ECS, or applying any other infra change, is a different risk category — deliberately kept as a manual trigger (with an `image_tag` input and a GitHub Environment that can require reviewers) so a production infra change is always a decision someone makes, not an automatic side effect of a merge. This came out of an actual guardrail: an early draft that ran `terraform apply -auto-approve` on every push to master got flagged during review as contradicting "code only, no live deploy" scope, and splitting build from deploy was the fix.

**Q: OIDC vs. long-lived AWS access keys in GitHub Actions — why OIDC?**
`aws-actions/configure-aws-credentials` with `role-to-assume` and no access key/secret stored as a GitHub secret at all. GitHub's OIDC token is exchanged for short-lived AWS credentials scoped to whatever IAM role trusts that specific repo/workflow. A long-lived access key sitting in GitHub Secrets is a standing credential that works forever if leaked; OIDC credentials expire in under an hour and are scoped per-workflow-run.

### Challenges

**Challenge: no AWS account was available to actually validate this infrastructure.**
Terraform code that's never been run is worth very little — HCL that "looks right" can still fail on a real `apply` (circular dependencies, wrong argument names, provider quirks).
- **Solution:** downloaded the Terraform CLI directly (no package manager available in the sandbox), ran `terraform init -backend=false` to skip the S3 remote-state backend (which also doesn't exist yet), then `terraform validate` and `terraform plan` with dummy variable values. `plan` got as far as trying to actually talk to AWS and failed only on `No valid credential sources found` — meaning every resource reference, every variable interpolation, and the entire dependency graph resolved correctly; the *only* thing missing was real credentials.
- **Trade-off:** this proves the configuration is internally consistent, not that it will provision successfully end-to-end against a real AWS account — things like IAM permission boundaries, service quotas, or AZ availability for a specific instance type can only surface on a real `apply`.
- **Benefit:** caught real mistakes before they'd have surfaced as a broken `apply` later — an invalid `aws_ecr_lifecycle_policy_document` data source that doesn't actually exist in the AWS provider (fixed by hand-writing the lifecycle policy JSON with `jsonencode` instead), and several `terraform fmt` alignment issues. Cheap to catch locally, much more annoying to debug against a live account mid-deploy.

**Challenge: three feature branches (WebSockets, billing/RBAC, infra) all built off `master` independently instead of stacked on each other.**
- **Solution:** each branch starts from the same `master` baseline rather than branching off the previous feature branch, so none of the three PRs depends on another one merging first — they can be reviewed and merged in any order (though `dashboard/page.tsx` was touched by more than one branch, so expect a small merge conflict there).
- **Trade-off:** exactly that conflict — since the branches aren't stacked, overlapping files touched by two branches (`dashboard/page.tsx` in Phases 4 and 5, for instance) will conflict when merging the second one, and that has to be resolved by hand rather than Terraform/git doing it automatically.
- **Benefit:** no branch is blocked waiting on another to merge first, and a reviewer can approve and ship, say, just the WebSocket work without also having to sign off on the billing changes in the same review.

---

## Cross-Cutting Questions (whole-system)

**Q: Walk me through end-to-end what happens when someone opens a pull request on a connected repo.**
GitHub sends a `pull_request` webhook → `github.py` verifies the HMAC signature → `handle_pull_request_event` upserts a `PullRequest` row (idempotent on `github_pr_id`) → `queue_review()` fires an `asyncio.create_task` and the webhook handler returns 200 immediately → `review_worker.run()` picks it up on its own DB session, marks the PR `REVIEWING`, publishes that status over the WebSocket (Redis pub/sub → whichever ECS replica holds the client's connection) → fetches the diff from GitHub → calls GPT-4o for structured findings → persists a `CodeReview` row → posts a formatted Markdown comment back to the GitHub PR → marks `COMPLETED` and publishes the final event over the WebSocket → dashboard updates live, no refresh needed.

**Q: If this had to handle 10x the traffic tomorrow, what's the first thing that breaks and what would you change?**
Two candidates: OpenAI rate limits (there's no queueing/backpressure — `queue_review` fires a task per PR with no concurrency cap, so a burst of PRs could all hit the OpenAI API at once and start getting rate-limited or erroring), and the single NAT Gateway in the Terraform VPC (a documented cost trade-off, not an accident — real production HA would want one NAT per AZ). I'd add a proper task queue (SQS + a worker fleet, or at minimum a semaphore limiting concurrent `review_worker.run()` calls) before touching infra scaling, since that's the actual bottleneck, not compute capacity.

**Q: What would you point to as the most interesting engineering decision in this project?**
The Redis pub/sub design for WebSockets (Chapter 4) — it's the one piece that had to be designed *for* a requirement (multi-replica auto-scaling) that didn't exist yet when it was built, and it works identically whether there's one backend replica or fifty without any code branching on environment. Close second: keeping the Terraform `deploy.yml` manual instead of auto-applying on merge — a guardrail that came directly out of a review catching scope creep, not something planned from the start.
