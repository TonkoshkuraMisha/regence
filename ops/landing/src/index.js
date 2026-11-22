// Страница ожидания regence.club (Worker regence-landing, таск «страницы без сайта»).
// Что делает: на любой запрос отдаёт одну страницу «скоро запуск» в стиле сайта (эмблема-пешка, тёмная палитра).
// Только английский, без выбора языка (решение владельца 22.11). Внешних ресурсов и скриптов нет; ответ — 200, noindex.

const TEXT = {
    title: "Regence — coming soon",
    status: "Coming soon",
    heading: "We are getting ready to launch",
    text: "An online chess club to play, train and learn. The doors open shortly.",
};

const STYLE = `
:root { color-scheme: dark; --bg: #1A120B; --gold: #D0A972; --wheat: #F5DEB3; --muted: #A68F6C; }
html, body { margin: 0; min-height: 100%; }
body {
    min-height: 100vh; box-sizing: border-box; padding: 32px 20px; display: flex; align-items: center; justify-content: center;
    color: var(--wheat); font-family: Georgia, 'Times New Roman', serif;
    background:
        radial-gradient(ellipse 70% 45% at 50% 0%, rgba(208, 169, 114, .14), transparent 70%),
        repeating-conic-gradient(rgba(245, 222, 179, .035) 0 25%, transparent 0 50%) 0 0 / 144px 144px,
        var(--bg);
}
main { width: 100%; max-width: 560px; text-align: center; }
.brand { margin: 0 0 28px; font-size: .78rem; letter-spacing: .42em; text-indent: .42em; text-transform: uppercase; color: var(--gold); }
.emblem { width: 76px; height: auto; display: block; margin: 0 auto 26px; }
.status { margin: 0 0 14px; font: 600 .74rem/1 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: .22em;
    text-indent: .22em; text-transform: uppercase; color: var(--muted); }
.rule { width: 56px; height: 1px; margin: 0 auto 28px; background: linear-gradient(90deg, transparent, var(--gold), transparent); }
h1 { margin: 0 0 12px; font-size: 1.6rem; line-height: 1.3; font-weight: 600; }
p { margin: 0; font-size: 1rem; line-height: 1.6; color: #CDB894; }
@media (prefers-reduced-motion: no-preference) { .emblem { animation: glow 3.2s ease-in-out infinite; } }
@keyframes glow { 0%, 100% { filter: drop-shadow(0 0 0 rgba(245, 222, 179, 0)); } 50% { filter: drop-shadow(0 0 14px rgba(245, 222, 179, .28)); } }
`;

const EMBLEM = `<svg class="emblem" viewBox="0 0 100 130" role="img" aria-label="Pawn">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F5DEB3"/><stop offset="1" stop-color="#C9A265"/></linearGradient></defs>
<g fill="url(#g)"><circle cx="50" cy="28" r="15"/><rect x="33" y="44" width="34" height="7" rx="3.5"/>
<path d="M41 51 Q39 78 29 100 L71 100 Q61 78 59 51 Z"/><rect x="23" y="100" width="54" height="9" rx="4.5"/>
<rect x="17" y="109" width="66" height="10" rx="5"/></g></svg>`;

const FAVICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%231A120B'/%3E%3Crect x='6' y='6' width='52' height='52' rx='10' fill='none' stroke='%23D0A972' stroke-width='3'/%3E%3Ctext x='32' y='44' font-family='Georgia,serif' font-size='36' fill='%23F5DEB3' text-anchor='middle'%3E%E2%99%9E%3C/text%3E%3C/svg%3E";

/** HTML страницы. */
export function renderPage() {
    const t = TEXT;
    return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="theme-color" content="#1A120B"/>
<meta name="robots" content="noindex"/>
<link rel="icon" type="image/svg+xml" href="${FAVICON}"/>
<title>${t.title}</title>
<style>${STYLE}</style>
</head>
<body>
<main>
<p class="brand">Regence</p>
${EMBLEM}
<p class="status">${t.status}</p>
<div class="rule"></div>
<h1>${t.heading}</h1>
<p>${t.text}</p>
</main>
</body>
</html>`;
}

export default {
    async fetch(request) {
        return new Response(renderPage(), {
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
