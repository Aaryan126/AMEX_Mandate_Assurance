FROM node:22-alpine AS dependencies
WORKDIR /workspace/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /workspace/apps/web
COPY --from=dependencies /workspace/apps/web/node_modules ./node_modules
COPY apps/web ./
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /workspace/apps/web/.next/standalone ./
COPY --from=builder /workspace/apps/web/.next/static ./.next/static
COPY --from=builder /workspace/apps/web/public ./public
EXPOSE 3000
CMD ["node", "server.js"]

