# --- FILE: frontend/nginx_locations.inc ---
# Маршруты сайта (API, WebSocket, статика): общие для server на 80 (nginx.conf) и на 443 (nginx-tls.conf), чтобы
# они не расходились. Подключается внутри server.

# --- API и WebSocket ------------------------------------------------------------------
location /api/ {
    proxy_pass http://regence_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    # Перезаписываем, а не дописываем: клиент не может подставить свой X-Forwarded-For
    # и обойти лимиты по IP.
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    # WebSocket партии живёт долго; сервер сам рвёт мёртвые соединения по ping/pong.
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
}

location = /health {
    proxy_pass http://regence_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    access_log off;
}

# --- Статика ---------------------------------------------------------------------------
# Файлы сборки Vite с хэшем в имени не меняются — кэшируем надолго.
location /assets/ {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "public, max-age=31536000, immutable";
    try_files $uri =404;
}

# Приложение на телефоне (таск 24.2). Сервис-воркер браузер перепроверяет сам, но без кэша новая версия
# доходит сразу; манифесту — его тип (в mime.types образа nginx его может не быть).
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

# SPA: любые клиентские маршруты (/game/123, /profile/...) отдают index.html.
location / {
    include /etc/nginx/conf.d/security_headers.inc;
    add_header Cache-Control "no-cache";
    try_files $uri $uri/ /index.html;
}
