# --- FILE: frontend/Dockerfile ---
# Frontend build and static file serving through nginx, which also proxies the API and WebSocket
# to the backend: the frontend and the API are on one domain, so CORS is not needed.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Sentry project DSN for the page (optional): substituted into the build; without it Sentry is off on the page.
ARG VITE_SENTRY_DSN=
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
# VITE_API_URL / VITE_WS_URL are not set: in the production build the API is taken from the same domain.
# The Sentry token for uploading source maps is a build secret (BuildKit), not an ARG: that way it does not remain in the image layer history.
# If the secret is not passed (CI, development), the file is empty, maps are not created and not uploaded (frontend/vite.config.ts).
RUN --mount=type=secret,id=sentry_auth_token \
    SENTRY_AUTH_TOKEN="$(cat /run/secrets/sentry_auth_token 2>/dev/null || true)" npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
# .inc, not .conf: the stock nginx.conf includes only conf.d/*.conf, and this file
# is included manually inside server and location.
COPY security_headers.inc /etc/nginx/conf.d/security_headers.inc
COPY nginx_locations.inc /etc/nginx/conf.d/nginx_locations.inc
# The server on 443 sits in the image under a name nginx does not load; docker-compose.tls.yml enables it (a certificate and key are needed).
COPY nginx-tls.conf /etc/nginx/nginx-tls.conf.example
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
