# --- build stage ---
FROM node:20-alpine AS builder
WORKDIR /app

# Опционально: если используете pnpm/yarn — раскомментируйте и скорректируйте
# RUN corepack enable

# Сначала только манифесты — чтобы кешировать deps
COPY package.json package-lock.json* ./
RUN npm ci

# Копируем остальной код
COPY . .

# Отключим телеметрию Next
ENV NEXT_TELEMETRY_DISABLED=1

# Важно: URL API пробрасывается из docker-compose через NEXT_PUBLIC_API_BASE
# Сборка
RUN npm run build

# --- run stage ---
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Копируем минимальный runtime, собранный в standalone
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]