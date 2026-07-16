# syntax=docker/dockerfile:1

# Étape 1 : Build de l'application React
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install --silent

COPY public ./public
COPY src ./src
RUN npm run build

# Étape 2 : Serveur statique avec Nginx
FROM nginx:1.25-alpine

COPY --from=builder /app/build /usr/share/nginx/html

# Configuration nginx minimale pour Single Page Application (SPA)
RUN echo 'server { \
    listen 3000; \
    server_name localhost; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
