# --- FILE: frontend/nginx_locations.inc ---
# Site routes (API, WebSocket, static files): shared by the server on 80 (nginx.conf) and on 443 (nginx-tls.conf), so that
# they do not diverge. Included inside server.

# --- API and WebSocket ------------------------------------------------------------------
location /api/ {
    proxy_pass http://regence_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    # We overwrite rather than append: the client cannot inject its own X-Forwarded-For
    # and bypass the per-IP limits.
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    # The game WebSocket lives long; the server itself drops dead connections by ping/pong.
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
}

location = /health {
    proxy_pass http://regence_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    access_log off;
}

# --- Static files ---------------------------------------------------------------------------
# Vite build files with a hash in the name do not change, so we cache them for a long time.
location /assets/ {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "public, max-age=31536000, immutable";
    try_files $uri =404;
}

# The app on a phone (task 24.2). The browser rechecks the service worker itself, but without a cache a new version
# arrives at once; the manifest gets its type (it may be missing from the nginx image's mime.types).
location = /sw.js {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "no-cache";
    try_files $uri =404;
}

location = /manifest.webmanifest {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "no-cache";
    default_type application/manifest+json;
    types { }
    try_files $uri =404;
}

# SPA: any client routes (/game/123, /profile/...) return index.html.
location / {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "no-cache";
    try_files $uri $uri/ /index.html;
}
