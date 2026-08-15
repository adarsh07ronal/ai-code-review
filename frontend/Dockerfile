FROM node:20-alpine AS base
WORKDIR /app
COPY package.json ./

# ── Dev stage ─────────────────────────────────────────────────────────────
FROM base AS development
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Builder ───────────────────────────────────────────────────────────────
FROM base AS builder
# NEXT_PUBLIC_* vars are inlined into the client bundle at build time, so
# this has to be a build arg — setting it as an ECS task env var at runtime
# would have no effect on the already-built .next/static output.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm install --frozen-lockfile
COPY . .
RUN npm run build

# ── Production ────────────────────────────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
