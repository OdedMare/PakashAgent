# Sandbox frontend image.
#
# Identical to frontend/Dockerfile except that BACKEND_URL is available at
# BUILD time. `next.config.ts` reads it while defining rewrites, so the value
# is baked into the build output — supplying it only as a runtime environment
# variable leaves the compiled rewrite pointing at 127.0.0.1:8000, which
# inside the frontend container is the frontend itself (ECONNREFUSED).
#
# Build context is `frontend/`.

FROM node:20-alpine AS build
WORKDIR /app

ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
RUN npm prune --omit=dev

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production

# Also set at runtime, so any server-side read resolves to the same backend.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "start"]
