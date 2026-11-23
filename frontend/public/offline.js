// --- FILE: frontend/public/offline.js ---
// Offline page (task 24.2): the language is the one chosen on the site (regence_language), otherwise English. The app
// catalogs are inside the build and unavailable without a network, so three short texts are here, in the same three languages.
// A separate file rather than in offline.html: the CSP forbids inline scripts.

(function () {
    var TEXTS = {
        en: {
            title: 'No connection',
            text: 'regence needs the internet: games, puzzles and analysis live on the server. Check the connection and try again.',
            retry: 'Try again',
        },
        uk: {
            title: 'Немає зв’язку',
            text: 'regence працює з інтернетом: партії, задачі й розбір живуть на сервері. Перевірте з’єднання і спробуйте ще раз.',
            retry: 'Спробувати ще раз',
        },
    };

    function language() {
        var saved = null;
        try {
            saved = localStorage.getItem('regence_language');
        } catch {
            saved = null;
        }
        if (saved && TEXTS[saved]) return saved;
        return 'en';  // English by default (owner's decision 22.11); the language chosen on the site is above
    }

    var lang = language();
    var texts = TEXTS[lang];
    document.documentElement.lang = lang;
    document.getElementById('offline-title').textContent = texts.title;
    document.getElementById('offline-text').textContent = texts.text;
    var retry = document.getElementById('offline-retry');
    retry.textContent = texts.retry;
    retry.addEventListener('click', function () {
        window.location.reload();
    });
    // The connection is back: straight to the page that was open.
    window.addEventListener('online', function () {
        window.location.reload();
    });
})();
