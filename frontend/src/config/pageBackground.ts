// --- FILE: frontend/src/config/pageBackground.ts ---
// Page background (task 18.1): a quiet tile with an embossed pattern (own SVGs in /assets/patterns, CC0) and a palette.
// The embossing is a light and a dark stroke, so one tile suits any dark palette. "Parchment" is a muted
// warm tone: the interface is dark, and on a light background text outside cards would be unreadable.

export const PAGE_PATTERNS = [
    'none', 'celtic', 'map', 'manuscript', 'circuit', 'bauhaus', 'marble',
    // Task 31.1: autumn leaves, herringbone parquet, squared notebook.
    'leaves', 'parquet', 'notebook',
] as const;
export type PagePattern = (typeof PAGE_PATTERNS)[number];

export const PAGE_PALETTES = {
    room: '#2C221C', teal: '#12323C', parchment: '#3B3022',
    // Task 31.1: autumn park twilight, club bottle green, school notebook ink.
    autumn: '#3A2814', bottle: '#1F3028', ink: '#252C3D',
} as const;
export type PagePalette = keyof typeof PAGE_PALETTES;

const PATTERN_KEY = 'regence_page_pattern';
const PALETTE_KEY = 'regence_page_palette';

function read(key: string): string | null {
    try {
        return localStorage.getItem(key);
    } catch {
        return null;
    }
}

export function getSavedPagePattern(): PagePattern {
    const saved = read(PATTERN_KEY);
    return (PAGE_PATTERNS as readonly string[]).includes(saved ?? '') ? saved as PagePattern : 'none';
}

export function getSavedPagePalette(): PagePalette {
    const saved = read(PALETTE_KEY);
    return saved && saved in PAGE_PALETTES ? saved as PagePalette : 'room';
}

export function pageBackgroundStyle(pattern: PagePattern, palette: PagePalette): { backgroundColor: string; backgroundImage: string } {
    return {
        backgroundColor: PAGE_PALETTES[palette],
        backgroundImage: pattern === 'none' ? 'none' : `url('/assets/patterns/${pattern}.svg')`,
    };
}

/** Apply to the page (at startup and on a settings change) and remember the choice. */
export function applyPageBackground(pattern = getSavedPagePattern(), palette = getSavedPagePalette(), persist = false): void {
    if (persist) {
        try {
            localStorage.setItem(PATTERN_KEY, pattern);
            localStorage.setItem(PALETTE_KEY, palette);
        } catch {
            // Storage unavailable - the background still changes until reload.
        }
    }
    if (typeof document === 'undefined') return;
    const style = pageBackgroundStyle(pattern, palette);
    document.body.style.backgroundColor = style.backgroundColor;
    document.body.style.backgroundImage = style.backgroundImage;
}
