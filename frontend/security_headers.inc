# --- FILE: frontend/security_headers.inc ---
# Security headers for all nginx responses (included in server and in every location).
#
# CSP is the main protection of the token in localStorage against XSS: even if an attacker injects markup,
# the browser will not run a foreign or inline script and will not send data to a foreign domain.
#   script-src 'self'         - only scripts from the build, no inline and no eval;
#   style-src 'unsafe-inline' - React and libraries set styles via the style attribute;
#   img-src                   - only own images (avatars are our own set, task 18.4), data:/blob: for icons and previews;
#   connect-src 'self' + Sentry - fetch and WebSocket to our own domain (CSP3 includes ws/wss) and error reports to Sentry (EU and US).
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' data: blob:; connect-src 'self' https://*.ingest.de.sentry.io https://*.ingest.sentry.io; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "no-referrer" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
# HSTS: the value is set by the map $hsts_value in nginx.conf - on an HTTPS request the term and includeSubDomains, on HTTP there is no header.
add_header Strict-Transport-Security $hsts_value always;
