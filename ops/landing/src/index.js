// Waiting page of regence.club (Worker regence-landing): answers any request with a single "launching soon" page.
// The HTML is built by scripts/dev/build_error_pages.py (a retro collage of master portraits, public domain and CC0)
// and put into page.js; here we only serve it with security headers. English only, no scripts or external resources.

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
