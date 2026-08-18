FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# rewrites() is baked into the build output, so the backend URL must be
# known here — not only at container start.
ARG BACKEND_URL=http://127.0.0.1:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build
RUN npm prune --omit=dev

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "start"]
