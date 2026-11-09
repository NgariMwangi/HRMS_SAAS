FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN node --version && npm --version \
    && npm ping --fetch-timeout=20000 --fetch-retries=1 \
    && npm ci --include=dev --no-audit --no-fund \
       --fetch-timeout=60000 --fetch-retries=1 --loglevel=verbose
COPY . .
RUN npm run build

FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
