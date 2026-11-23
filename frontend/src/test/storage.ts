// --- FILE: frontend/src/test/storage.ts ---
// Node 25+ declares its own global localStorage/sessionStorage (the Web Storage API). Without the
// --localstorage-file key they do not work, and the jsdom environment in vitest does not overwrite already existing global
// names — so all the tests that touch localStorage failed ("Cannot read properties of undefined"), although on Node 24
// (as in CI) they passed. It is attached as the first setup file, before the modules that read the storage on import.

const dom = (globalThis as { jsdom?: { window: Window } }).jsdom;
if (dom) {
    for (const name of ['localStorage', 'sessionStorage'] as const) {
        if (globalThis[name] !== dom.window[name]) {
            Object.defineProperty(globalThis, name, {value: dom.window[name], configurable: true, writable: true});
        }
    }
}
