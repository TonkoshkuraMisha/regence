// --- FILE: frontend/src/components/__tests__/About.test.tsx ---
// The "About" page: every piece set and every portrait is shown with its author and licence;
// a saved choice of a removed (non-free) piece set is switched to a free one.

import {render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import About from '../About';
import {PIECE_SETS, getSavedPieceSetKey} from '../../config/boardAppearance';
import portraitCredits from '../../config/portraitCredits.json';

function renderAbout() {
    return render(
        <MemoryRouter>
            <About/>
        </MemoryRouter>,
    );
}

const ENGINE = {name: 'Stockfish 17.1', source_url: 'https://github.com/official-stockfish/Stockfish/tree/sf_17.1'};

beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ENGINE}) as Response));
});

afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
});

describe('About', () => {
    it('names the engine, its licence and a link to the source code', () => {
        renderAbout();
        expect(screen.getByText(/GNU GPL version 3/)).toBeInTheDocument();
        expect(screen.getByRole('link', {name: /github\.com\/official-stockfish\/Stockfish/})).toBeInTheDocument();
    });

    it('the engine version of this installation and the sources of exactly that version (GPL)', async () => {
        renderAbout();
        const line = await screen.findByTestId('engine-version');
        expect(line).toHaveTextContent('This installation runs Stockfish 17.1');
        expect(within(line).getByRole('link', {name: 'on GitHub'})).toHaveAttribute('href', ENGINE.source_url);
    });

    it('without engine information there is no version line', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: false, json: async () => ({})}) as Response));
        renderAbout();
        await Promise.resolve();
        expect(screen.queryByTestId('engine-version')).toBeNull();
    });

    it('shows the author and licence of each piece set from the interface', () => {
        renderAbout();
        const table = screen.getAllByRole('table')[0];
        for (const set of Object.values(PIECE_SETS)) {
            const row = within(table).getByText(set.shortName).closest('tr') as HTMLElement;
            expect(within(row).getByText(set.author)).toBeInTheDocument();
            expect(within(row).getByText(set.license)).toBeInTheDocument();
        }
    });

    it('shows a source record for every portrait', () => {
        renderAbout();
        const table = screen.getAllByRole('table')[1];
        const rows = within(table).getAllByRole('row');
        expect(rows).toHaveLength(Object.keys(portraitCredits).length + 1);
        // The chess player's name leads to the file page on Wikimedia Commons.
        const carlsen = within(table).getByRole('link', {name: 'Magnus Carlsen'});
        expect(carlsen.getAttribute('href')).toContain('commons.wikimedia.org');
    });
});

describe('piece sets', () => {
    it('the interface has no sets with a non-commercial licence', () => {
        for (const set of Object.values(PIECE_SETS)) {
            expect(set.license).not.toMatch(/NC/i);
            expect(set.author).not.toBe('');
        }
    });

    it.each([
        ['maestro', 'fantasy'],
        ['alpha', 'merida'],
        ['cardinal', 'outline'],
        ['unknown-set', 'merida'],
    ])('the saved set %s is replaced by %s', (saved, expected) => {
        localStorage.setItem('regence_piece_set', saved);
        expect(getSavedPieceSetKey()).toBe(expected);
    });
});
