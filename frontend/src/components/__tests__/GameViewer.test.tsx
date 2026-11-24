// The game review studio: loading a PGN, navigating by moves (buttons and keyboard), flipping
// the board, a cached and a requested engine analysis, loading and analysis errors.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import GameViewer from '../GameViewer';
import {setLanguage} from '../../i18n';
import {clearToken, setToken} from '../../services/authToken';

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => true), toggleMute: vi.fn(() => false)},
    };
});

const FOOLS_MATE_PGN = [
    '[Event "Casual"]',
    '[Site "Regence"]',
    '[Date "2026.11.01"]',
    '[White "alice"]',
    '[Black "bob"]',
    '[WhiteElo "1500"]',
    '[BlackElo "1480"]',
    '[Result "0-1"]',
    '',
    '1. f3 e5 2. g4 Qh4# 0-1',
].join('\n');

const sideStats = (accuracy: number) => ({
    accuracy, best: 1, good: 0, inaccuracies: 0, mistakes: 1, blunders: 1, avg_cp_loss: 120,
});

const ANALYSIS = {
    game_id: 42,
    engine: 'Stockfish',
    white: sideStats(31.4),
    black: sideStats(97.2),
    moves: ['f3', 'e5', 'g4', 'Qh4#'].map((san, i) => ({
        ply: i + 1, move_number: Math.floor(i / 2) + 1, color: i % 2 ? 'black' : 'white', san, uci: '',
        eval_cp: -50 * i, eval_display: (-0.5 * i).toFixed(1), mate: null, best_move_uci: null,
        cp_loss: 0, classification: 'best', symbol: '',
    })),
};

type Reply = { ok: boolean; status?: number; body?: unknown; text?: string };

function stubApi({pgn, cached, analyze, personal, guess}: { pgn: Reply; cached?: Reply; analyze?: Reply; personal?: Reply; guess?: Reply }) {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = input.toString();
        let reply: Reply = {ok: false, status: 404, body: {}};
        if (url.endsWith('/pgn')) reply = pgn;
        else if (url.includes('/puzzles/personal/game/')) reply = personal ?? reply;
        else if (url.includes('/guess/game/')) reply = guess ?? reply;
        else if (url.includes('/analysis/game/')) reply = (init?.method === 'POST' ? analyze : cached) ?? reply;
        return {
            ok: reply.ok,
            status: reply.status ?? (reply.ok ? 200 : 500),
            json: async () => reply.body,
            text: async () => reply.text ?? '',
        } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const pieceOn = (square: string) =>
    document.querySelector(`[data-square="${square}"] img`)?.getAttribute('alt') ?? null;

/**
 * The position on the board after an action. We wait instead of checking at once: under load (CI, coverage measurement) the render
 * may lag behind the click, and an instant check occasionally failed although the component worked correctly.
 */
const expectPiece = (square: string, piece: string | null) =>
    waitFor(() => expect(pieceOn(square)).toBe(piece));

function renderViewer() {
    return render(
        <MemoryRouter initialEntries={['/game/42']}>
            <Routes>
                <Route path="/game/:gameId" element={<GameViewer/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('ResizeObserver', class {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('GameViewer', () => {
    it('a Fischer random game is handed over to the 960 archive viewer', async () => {
        stubApi({pgn: {ok: true, text: ['[Variant "Chess960"]', '[SetUp "1"]', '[FEN "bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR w HAha - 0 1"]', '', '1. e4 e5'].join('\n')}});
        render(
            <MemoryRouter initialEntries={['/game/42']}>
                <Routes>
                    <Route path="/game/:gameId" element={<GameViewer/>}/>
                    <Route path="/play/960/game/:gameId" element={<p data-testid="archive-960">archive</p>}/>
                </Routes>
            </MemoryRouter>,
        );
        expect(await screen.findByTestId('archive-960')).toBeInTheDocument();
    });

    it('library mode: a PGN from the library, no engine review and no requests about players\' games', async () => {
        const fetchMock = stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        render(
            <MemoryRouter initialEntries={['/library/game/7']}>
                <Routes>
                    <Route path="/library/game/:gameId" element={<GameViewer library/>}/>
                </Routes>
            </MemoryRouter>,
        );
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));
        const urls = fetchMock.mock.calls.map(([url]) => url.toString());
        expect(urls.some((u) => u.endsWith('/api/v1/library/games/7/pgn'))).toBe(true);
        expect(urls.some((u) => u.includes('/analysis/game/') || u.includes('/guess/game/') || u.includes('/profile/games/'))).toBe(false);
        expect(screen.queryByRole('button', {name: 'Computer analysis'})).toBeNull();
    });

    it('a game from another site (24.1): the PGN, the review and puzzle badges from /imports with a token, no requests about the site\'s games', async () => {
        setToken('tok');
        const fetchMock = vi.fn(async (input: string | URL | Request, _init?: RequestInit) => {
            const url = input.toString();
            const body = url.endsWith('/imports/games/7') ? {id: 7, puzzle_plies: [4]}
                : url.endsWith('/imports/games/7/analysis') ? ANALYSIS : {};
            return {ok: true, status: 200, json: async () => body, text: async () => FOOLS_MATE_PGN} as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        try {
            render(
                <MemoryRouter initialEntries={['/import/game/7']}>
                    <Routes>
                        <Route path="/import/game/:gameId" element={<GameViewer imported/>}/>
                    </Routes>
                </MemoryRouter>,
            );
            await waitFor(() => expect(pieceOn('h4')).toBe('b q'));
            expect(await screen.findByTestId('personal-badge-4')).toBeTruthy();
            const calls = fetchMock.mock.calls.map(([url, init]) => [url.toString(), init as RequestInit | undefined] as const);
            const pgnCall = calls.find(([url]) => url.endsWith('/api/v1/imports/games/7/pgn'));
            expect(pgnCall?.[1]?.headers).toMatchObject({Authorization: 'Bearer tok'});
            expect(calls.some(([url]) => url.endsWith('/api/v1/imports/games/7/analysis'))).toBe(true);
            expect(calls.some(([url]) => url.includes('/analysis/game/') || url.includes('/guess/game/')
                || url.includes('/profile/games/') || url.includes('/puzzles/personal/game/'))).toBe(false);
        } finally {
            clearToken();
        }
    });

    it('shows the players from the PGN and the final position', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();

        expect((await screen.findAllByText('alice')).length).toBeGreaterThan(0);
        expect(screen.getAllByText('bob').length).toBeGreaterThan(0);
        expect(pieceOn('h4')).toBe('b q');
        expect(pieceOn('d8')).toBeNull();
        // Accessibility (task 26.3): squares are labelled with words, the board with a description of the position.
        expect(document.querySelector('[data-square="h4"]')).toHaveAttribute('aria-label', 'h4, black queen');
        expect(document.querySelector('[data-square="d8"]')).toHaveAttribute('aria-label', 'd8, empty');
        expect(screen.getByRole('group', {name: /queen/})).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Computer analysis'})).toBeInTheDocument();
    });

    it('navigation buttons: start, forward, back, end', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));

        fireEvent.click(screen.getByTitle('Start of the game'));
        await expectPiece('d8', 'b q');
        await expectPiece('f2', 'w p');

        fireEvent.click(screen.getByTitle('Move forward'));
        await expectPiece('f3', 'w p');
        await expectPiece('f2', null);

        fireEvent.click(screen.getByTitle('End of the game'));
        await expectPiece('h4', 'b q');
        fireEvent.click(screen.getByTitle('Move back'));
        await expectPiece('d8', 'b q');
        await expectPiece('g4', 'w p');
    });

    it('keyboard arrows page through the moves', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));

        fireEvent.keyDown(window, {key: 'ArrowUp'});
        await expectPiece('f2', 'w p');
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        await expectPiece('f3', 'w p');
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        await expectPiece('e5', 'b p');
        fireEvent.keyDown(window, {key: 'ArrowLeft'});
        await expectPiece('e5', null);
        fireEvent.keyDown(window, {key: 'ArrowDown'});
        await expectPiece('h4', 'b q');
    });

    it('paging with arrows does not move the page: only the move list window scrolls', async () => {
        // Earlier the current move was brought into view with scrollIntoView, and the whole page with the board moved along with the list.
        const intoView = vi.spyOn(Element.prototype, 'scrollIntoView');
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));

        for (const key of ['ArrowUp', 'ArrowRight', 'ArrowRight', 'ArrowDown', 'ArrowLeft']) {
            // The key is handled: the browser does not scroll the page itself.
            expect(fireEvent.keyDown(window, {key})).toBe(false);
        }
        await expectPiece('h4', null);
        expect(intoView).not.toHaveBeenCalled();
        // The move list is a window with its own scroll and a limited height.
        expect(screen.getByTestId('move-list').className).toMatch(/max-h-\[50dvh\]/);
        expect(screen.getByTestId('move-list').querySelector('.overflow-y-auto .active-move')).not.toBeNull();
        intoView.mockRestore();
    });

    it('the key handler is registered once and sees the loaded game without re-registration', async () => {
        // Earlier the handler was re-registered after every render and read the history from the closure:
        // a key press between rendering the loaded game and running the effect saw an empty history and was lost.
        const addListener = vi.spyOn(window, 'addEventListener');
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));

        fireEvent.keyDown(window, {key: 'ArrowUp'});
        await expectPiece('f2', 'w p');
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        await expectPiece('f3', 'w p');

        const keydownRegistrations = addListener.mock.calls.filter(([type]) => type === 'keydown');
        expect(keydownRegistrations).toHaveLength(1);
        addListener.mockRestore();
    });

    it('right-button marks — a shared layer: colour by modifier, paging does not clear them, Escape clears them', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));
        const cell = (square: string) => document.querySelector(`[data-square="${square}"]`) as HTMLElement;
        const rightDrag = (from: string, to: string, init: Record<string, unknown> = {}) => {
            document.elementsFromPoint = () => [cell(from)];
            fireEvent.pointerDown(cell(from), {pointerType: 'mouse', button: 2});
            document.elementsFromPoint = () => [cell(to)];
            fireEvent.pointerUp(cell(to), {pointerType: 'mouse', button: 2, ...init});
        };

        rightDrag('g1', 'f3', {shiftKey: true});
        rightDrag('e4', 'e4');
        expect(screen.getByTestId('note-arrow-g1-f3').getAttribute('data-color')).toBe('red');
        expect(screen.getByTestId('note-square-e4').getAttribute('data-color')).toBe('green');

        fireEvent.keyDown(window, {key: 'ArrowLeft'});
        await expectPiece('h4', null);
        expect(screen.getByTestId('note-arrow-g1-f3')).toBeInTheDocument();

        fireEvent.keyDown(window, {key: 'Escape'});
        await waitFor(() => expect(screen.queryByTestId('board-annotations')).toBeNull());
    });

    it('"Guess the master\'s move": the button leads to the first selected moment of the game, without moments — no button', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, guess: {ok: true, body: {positions: [{id: 77, ply: 22, series_id: null}]}}});
        renderViewer();
        expect(await screen.findByTestId('guess-from-game')).toHaveAttribute('href', '/guess/77?whole=1');  // the whole game
    });

    it('the opening explorer opens by a button and requests the moves up to the shown position', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));
        expect(screen.queryByTestId('opening-explorer')).toBeNull();
        fireEvent.click(screen.getByTestId('explorer-toggle'));
        expect(await screen.findByTestId('opening-explorer')).toBeInTheDocument();
        const call = (vi.mocked(fetch).mock.calls as unknown as [string, RequestInit][]).find(([url]) => String(url).includes('opening-explorer'))!;
        expect(JSON.parse(String(call[1].body)).moves).toEqual(['f2f3', 'e7e5', 'g2g4', 'd8h4']);
    });

    it('without selected moments there is no "Guess the move" button', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, guess: {ok: true, body: {positions: []}}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));
        expect(screen.queryByTestId('guess-from-game')).toBeNull();
    });

    it('flipping the board changes the order of the squares', async () => {
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('h4')).toBe('b q'));

        const firstSquare = () => document.querySelector('[data-square]')?.getAttribute('data-square');
        expect(firstSquare()).toBe('a8');
        fireEvent.click(screen.getByTitle('Flip the board'));
        expect(firstSquare()).toBe('h1');
    });

    it('moves from which "Your mistakes" puzzles were made are marked with a badge', async () => {
        setToken('jwt');
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, personal: {ok: true, body: {game_id: 42, plies: [3]}}});
        renderViewer();
        expect(await screen.findByTestId('personal-badge-3')).toBeTruthy();
        expect(screen.queryByTestId('personal-badge-1')).toBeNull();
        clearToken();
    });

    it('a cached analysis is shown at once, without starting the engine', async () => {
        const fetchMock = stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, cached: {ok: true, body: ANALYSIS}});
        renderViewer();

        expect((await screen.findAllByText(/31\.4%/)).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/97\.2%/).length).toBeGreaterThan(0);
        expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
        // An old review without phases — there is no phases row.
        expect(screen.queryByTestId('viewer-phases-white')).toBeNull();
    });

    it('critical moments: the turning point, the worst moves, a missed punishment — a click opens the move', async () => {
        const summary = {
            kind: 'decisive_blunder', turning_point_ply: 3, lead_changes: 0, equal_share: 0.5,
            white: {best_ply: null, worst_ply: 3}, black: {best_ply: 4, worst_ply: null},
            missed: [{ply: 2, color: 'black', cp: 200}],
        };
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, cached: {ok: true, body: {...ANALYSIS, summary}}});
        renderViewer();
        const block = await screen.findByTestId('viewer-moments');
        expect(block.textContent).toBe('Critical momentsMissed punishment: 1… e5Turning point: 2. g4');
        fireEvent.click(screen.getByTestId('moment-3'));
        expect(screen.getByTestId('moment-3').className).toContain('bg-amber-900/50');
    });

    it('accuracy by phases: opening, middlegame, endgame; a phase without moves — a dash', async () => {
        const withPhases = {
            ...ANALYSIS,
            white: {...sideStats(31.4), phases: {opening: 31.4, middlegame: null, endgame: null}},
            black: {...sideStats(97.2), phases: {opening: 97.2, middlegame: null, endgame: null}},
        };
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, cached: {ok: true, body: withPhases}});
        renderViewer();
        const row = await screen.findByTestId('viewer-phases-white');
        expect(row.textContent).toBe('Op. 31.4%Mid. —End. —');
        expect(screen.getByTestId('viewer-phases-black').textContent).toContain('97.2%');
    });

    it('the mentor\'s comment on a move: text, arrows, highlight and the arrows switch', async () => {
        const moves = ANALYSIS.moves.map((m) => ({...m}));
        moves[2] = {
            ...moves[2], classification: 'Blunder', cp_loss: 900,
            coach: {
                comment: [
                    {key: 'coach.verdict.blunder.v1', params: {move: 'g4'}},
                    {key: 'coach.threat.mate_in.v1', params: {n: 1, move: '♛h4#'}},
                    {key: 'coach.best.generic.v1', params: {move: '♘c3'}},
                    {key: 'coach.from.the.future.v9', params: {}},  // an unknown key is skipped
                ],
                arrows: [{from: 'd8', to: 'h4', kind: 'threat'}, {from: 'b1', to: 'c3', kind: 'best'},
                         {from: 'z9', to: 'h4', kind: 'threat'}],
                highlights: [{square: 'e1', kind: 'target'}],
            },
        } as never;
        moves[3] = {...moves[3], coach: {comment: [{key: 'coach.good.checkmate.v1', params: {move: '♛h4#'}}]}} as never;
        stubApi({pgn: {ok: true, text: FOOLS_MATE_PGN}, cached: {ok: true, body: {...ANALYSIS, moves}}});
        renderViewer();

        // The end of the game — mate.
        expect(await screen.findByTestId('coach-comment')).toHaveTextContent('♛h4# — checkmate!');
        fireEvent.click(screen.getByTitle('Move back'));
        const comment = await screen.findByText(
            'g4 is a blunder! Now the opponent has mate in 1: ♛h4#. Stronger was ♘c3.',
        );
        expect(comment).toBeInTheDocument();
        expect(screen.getAllByTestId('coach-arrow-threat')).toHaveLength(1);  // the arrow with the square "z9" is dropped
        expect(screen.getAllByTestId('coach-arrow-best')).toHaveLength(1);
        expect(screen.getAllByTestId('coach-target')).toHaveLength(1);

        fireEvent.click(screen.getByRole('checkbox', {name: 'Coach’s arrows'}));
        expect(screen.queryByTestId('coach-arrow-threat')).not.toBeInTheDocument();
        expect(screen.queryByTestId('coach-target')).not.toBeInTheDocument();

        act(() => setLanguage('uk', {persist: false}));
        expect(screen.getByText('g4 — груба помилка! Тепер у суперника мат у 1 х.: ♛h4#. Сильніше було ♘c3.'))
            .toBeInTheDocument();

        fireEvent.click(screen.getByTitle('Початок партії'));
        expect(screen.queryByTestId('coach-comment')).not.toBeInTheDocument();
    });

    it('the analysis button starts the engine with a token and shows the accuracy', async () => {
        setToken('jwt-abc');
        const fetchMock = stubApi({
            pgn: {ok: true, text: FOOLS_MATE_PGN},
            cached: {ok: false, status: 404, body: {detail: 'Not analysed'}},
            analyze: {ok: true, body: ANALYSIS},
        });
        renderViewer();

        fireEvent.click(await screen.findByRole('button', {name: 'Computer analysis'}));

        expect((await screen.findAllByText(/31\.4%/)).length).toBeGreaterThan(0);
        const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
        expect(post?.[0]).toMatch(/\/api\/v1\/analysis\/game\/42$/);
        expect(post?.[1]?.headers).toEqual({Authorization: 'Bearer jwt-abc', 'X-Request-ID': expect.any(String)});
    });

    it('an analysis error is shown by the server text', async () => {
        stubApi({
            pgn: {ok: true, text: FOOLS_MATE_PGN},
            analyze: {ok: false, status: 429, body: {detail: 'Too many requests to the engine'}},
        });
        renderViewer();

        fireEvent.click(await screen.findByRole('button', {name: 'Computer analysis'}));

        expect(await screen.findByText('Too many requests to the engine')).toBeInTheDocument();
    });

    it('a validation error (detail is a list) does not crash the page', async () => {
        stubApi({
            pgn: {ok: true, text: FOOLS_MATE_PGN},
            analyze: {
                ok: false, status: 422,
                body: {detail: [{type: 'int_parsing', loc: ['path', 'game_id'], msg: 'Input should be a valid integer', params: {}}]},
            },
        });
        renderViewer();

        fireEvent.click(await screen.findByRole('button', {name: 'Computer analysis'}));

        expect(await screen.findByText('game_id: invalid value')).toBeInTheDocument();
    });

    it('an empty analysis of a game with moves — a clear error instead of "100 %" without a chart', async () => {
        const empty = {...ANALYSIS, white: sideStats(100), black: sideStats(100), moves: []};
        stubApi({
            pgn: {ok: true, text: FOOLS_MATE_PGN},
            cached: {ok: true, body: empty},
            analyze: {ok: true, body: empty},
        });
        renderViewer();

        // An empty cache is not shown — the analysis start button is available.
        fireEvent.click(await screen.findByRole('button', {name: 'Computer analysis'}));

        expect(await screen.findByText(/The server returned an empty analysis/)).toBeInTheDocument();
        expect(screen.queryByText(/100(\.0)?%/)).toBeNull();
    });

    it('an unavailable PGN — an error message', async () => {
        stubApi({pgn: {ok: false, status: 404}});
        renderViewer();

        expect(await screen.findByText('Could not load the game data')).toBeInTheDocument();
    });
});

describe('GameViewer: a game from an arbitrary position', () => {
    const FROM_POSITION_PGN = [
        '[Event "Historical Bot Match"]',
        '[White "Alice"]',
        '[Black "Bot"]',
        '[Result "1/2-1/2"]',
        '[SetUp "1"]',
        '[FEN "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 40"]',
        '',
        '40... Kf8 41. Rd8+ Ke7 1/2-1/2',
    ].join('\n');

    it('positions are restored from the start position of the game, moves are numbered by it', async () => {
        stubApi({pgn: {ok: true, text: FROM_POSITION_PGN}});
        renderViewer();

        // The final position: the king on e7, the rook on d8 — not the ordinary setup with these moves.
        await waitFor(() => expect(pieceOn('e7')).toBe('b k'));
        expect(pieceOn('d8')).toBe('w r');
        expect(pieceOn('e2')).toBeNull();
        expect(screen.getByText('40.')).toBeInTheDocument();
        expect(screen.getByText('41.')).toBeInTheDocument();
        expect(screen.getByText('…')).toBeInTheDocument();  // move 40 has no White move

        // To the start of the game — the position from the FEN on the board.
        fireEvent.keyDown(window, {key: 'ArrowUp'});
        await waitFor(() => expect(pieceOn('g8')).toBe('b k'));
        expect(pieceOn('d1')).toBe('w r');
    });

    it('step navigation goes from the position from the FEN, the first move is Black\'s', async () => {
        stubApi({pgn: {ok: true, text: FROM_POSITION_PGN}});
        renderViewer();
        await waitFor(() => expect(pieceOn('e7')).toBe('b k'));
        fireEvent.keyDown(window, {key: 'ArrowUp'});
        await waitFor(() => expect(pieceOn('g8')).toBe('b k'));

        // 40... Kf8 — Black moves, the White rook is still on d1.
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        await waitFor(() => expect(pieceOn('f8')).toBe('b k'));
        expect(pieceOn('g8')).toBeNull();
        expect(pieceOn('d1')).toBe('w r');

        // 41. Rd8+
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        await waitFor(() => expect(pieceOn('d8')).toBe('w r'));

        // Back — again the position after Black's move.
        fireEvent.keyDown(window, {key: 'ArrowLeft'});
        await waitFor(() => expect(pieceOn('d1')).toBe('w r'));
        expect(pieceOn('f8')).toBe('b k');

        // Black's move stands in the Black column: the first row of the journal is "40. … Kf8".
        const firstRow = screen.getByText('40.').parentElement as HTMLElement;
        const cells = Array.from(firstRow.children).map((el) => el.textContent?.trim());
        expect(cells[1]).toContain('…');
        expect(cells[2]).toContain('Kf8');
    });
});
