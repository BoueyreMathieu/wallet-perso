FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# Avec package-lock.json : versions exactes et vérifiées (npm ci). Sans : npm install (à éviter, voir docs/securite.md).
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY . .
RUN npm run build

# nginx sans droits root (écoute sur 8080).
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
