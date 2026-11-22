// Страница ожидания regence.club (Worker regence-landing): на любой запрос отдаёт одну страницу «скоро запуск».
// HTML собирает scripts/dev/build_error_pages.py (ретро-коллаж из портретов мастеров, общественное достояние и CC0)
// и кладёт в page.js; здесь — только отдача с заголовками безопасности. Только английский, без скриптов и внешних ресурсов.

import { PAGE } from "./page.js";

export default {
    async fetch() {
        return new Response(PAGE, {
            headers: {
                "content-type": "text/html; charset=utf-8",
                "cache-control": "public, max-age=300",
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "referrer-policy": "no-referrer",
                "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'",
            },
        });
    },
};
