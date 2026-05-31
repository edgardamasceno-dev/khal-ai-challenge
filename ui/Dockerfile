# Build estatico do console (Vite) e serve via nginx.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# npm install (nao ci): o lockfile gerado no host nao traz as deps nativas
# opcionais do Linux (engine oxide do Tailwind v4). Resolve por plataforma.
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
