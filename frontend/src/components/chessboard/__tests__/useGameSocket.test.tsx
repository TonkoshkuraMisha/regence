// The useGameSocket hook (a game with a person over WebSocket, the lobby, spectating, chat) on a replaced gameSocket and a fetch stub:
// server events (match_found, move_made, game_over, berserk, draw, rematch, invitation, spectating, chat, errors), polling
// of my-active and the lobby lists, catching up the result of a missed game, searching for an opponent and accepting a challenge (WebSocket + HTTP),
// player actions (draw, rematch, chat, berserk, an invitation link) and an invitation by the address /challenge/{code}.

import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useGameSocket} from '../hooks/useGameSocket';
import type {UseGameSocketOptions} from '../hooks/useGameSocket';
import {setToken} from '../../../services/authToken';

const socket = vi.hoisted(() => {
    const handlers = new Map<string, (data: any) => void>();
    return {
        handlers,
        on: vi.fn((event: string, cb: (data: any) => void) => {
            handlers.set(event, cb);
        }),
        off: vi.fn((event: string) => {
            handlers.delete(event);
        }),
        send: vi.fn(),
        connect: vi.fn(),
    };
});

vi.mock('../../../services/gameSocket', () => ({gameSocket: socket}));

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';

function makeOptions(over: Partial<UseGameSocketOptions> = {}) {
    const fn = () => vi.fn();
    const opts = {
        gameId: null, gameIdRef: {current: null}, myColorRef: {current: 'white'}, spectatingGameId: null,
        stateVersionRef: {current: 0}, gameOverResult: null, gameOverResultRef: {current: null}, activeBot: null,
        currentUsernameRef: {current: 'me'}, inviteCode: undefined, navigate: fn(), effectiveWhiteBaseMinutes: 3,
        effectiveIncSeconds: 2, inviteColorPref: 'random', ratedChoice: true, setIsRatedGame: fn(), setHourglass: fn(),
        setGame: fn(), setHistory: fn(), setViewIndex: fn(), setGameId: fn(), setMyColor: fn(), setSpectatingGameId: fn(),
        setActiveBot: fn(), setStateVersion: fn(), setWhitePlayer: fn(), setBlackPlayer: fn(), setRatingInfo: fn(),
        setGameOverResult: fn(), setDrawOfferStatus: fn(), setRematchStatus: fn(), isSearching: false,
        setIsSearching: fn(), setIsManualFlip: fn(), setSelectedSquare: fn(), setPendingPromotion: fn(), clearPremove: fn(),
        setWhiteTimeMs: fn(), setBlackTimeMs: fn(), setLobbyTab: fn(), setIsTimeDropdownOpen: fn(), setShowInvitePanel: fn(),
        moveStartTime: {current: 0}, resetLowTimeWarning: fn(), exitBotGame: fn(), playAudio: fn(), playOutcomeSound: fn(),
        updateSessionStats: fn(), ...over,
    };
    return opts as unknown as Record<string, any>;
}

type Route = (url: string, init?: RequestInit) => unknown;

function stubFetch(route: Route = () => undefined) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const body = route(String(url), init);
        if (body === 'fail') return {ok: false, status: 500, json: async () => ({})} as Response;
        const fallback = String(url).includes('/my-active') ? {active: false}
            : String(url).includes('matchmaking/queue') || String(url).endsWith('/live') ? [] : {};
        return {ok: true, status: 200, json: async () => (body !== undefined ? body : fallback)} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const emit = (event: string, data: any = {}) => act(() => socket.handlers.get(event)!(data));
const flush = () => act(async () => {
    await Promise.resolve();
    await Promise.resolve();
});

function mount(over: Partial<UseGameSocketOptions> = {}) {
    const opts = makeOptions(over);
    const view = renderHook(() => useGameSocket(opts as unknown as UseGameSocketOptions));
    return {opts, ...view};
}

const MATCH = {game_id: 5, color: 'black', state_version: 2, white_username: 'A', white_rating: 1500, black_username: 'B',
    black_rating: 1400, white_time_ms: 100000, black_time_ms: 90000, fen: AFTER_E4, is_rated: false, berserk_allowed: true,
    hourglass: true, opponent_id: 9, draw_offer_from: 9};

beforeEach(() => {
    socket.handlers.clear();
    socket.on.mockClear();
    socket.send.mockClear();
    socket.connect.mockClear();
    setToken('jwt');
    stubFetch();
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
});
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe('useGameSocket: connection', () => {
    it('with a token it connects and subscribes, without a token — no', async () => {
        const {unmount} = mount();
        await flush();
        expect(socket.connect).toHaveBeenCalledWith('jwt');
        expect(socket.handlers.size).toBe(13);
        unmount();
        expect(socket.handlers.size).toBe(0);
        setToken(null);
        mount();
        expect(socket.connect).toHaveBeenCalledTimes(1);
    });
});

describe('useGameSocket: game events', () => {
    it('match_found puts the game on the board: colour, clocks, players, position, draw offer', async () => {
        const {opts, result} = mount();
        await flush();
        await emit('match_found', MATCH);
        expect(opts.setGameId).toHaveBeenCalledWith(5);
        expect(opts.setMyColor).toHaveBeenCalledWith('black');
        expect(opts.setWhiteTimeMs).toHaveBeenCalledWith(100000);
        expect(opts.setWhitePlayer).toHaveBeenCalledWith({username: 'A', rating: '1500'});
        expect(opts.setBlackPlayer).toHaveBeenCalledWith({username: 'B', rating: '1400'});
        expect(opts.setIsRatedGame).toHaveBeenCalledWith(false);
        expect(opts.setHourglass).toHaveBeenCalledWith(true);
        expect(opts.playAudio).toHaveBeenCalledWith('start');
        expect(opts.setGame).toHaveBeenCalled();
        expect(result.current.berserk.allowed).toBe(true);
    });

    it('match_found: a Fischer game goes to its own page, a snapshot without game_id is ignored', async () => {
        const {opts} = mount();
        await flush();
        await emit('match_found', {game_id: 6, variant: 'chess960'});
        expect(opts.navigate).toHaveBeenCalledWith('/play/960/live', {state: {match: {game_id: 6, variant: 'chess960'}}});
        await emit('match_found', {});
        expect(opts.setGameId).not.toHaveBeenCalled();
    });

    it('match_found: restoring by PGN, with a broken PGN — by FEN; the same game without a new start mark', async () => {
        const {opts} = mount();
        await flush();
        await emit('match_found', {game_id: 5, pgn: '1. e4 e5', fen: START_FEN});
        expect(opts.setHistory).toHaveBeenLastCalledWith([expect.anything(), expect.anything()]);
        await emit('match_found', {game_id: 5, pgn: '1. zz9', fen: START_FEN, color: 'white'});
        await emit('match_found', {game_id: 5, color: 'white'});
        opts.playAudio.mockClear();
        opts.gameIdRef.current = 5;
        await emit('match_found', {game_id: 5, color: 'white', draw_offer_from: 9, opponent_id: 9});
        expect(opts.playAudio).not.toHaveBeenCalled();
        expect(opts.setDrawOfferStatus).toHaveBeenCalled();
        await emit('match_found', {game_id: 5, color: 'white'});
    });

    it('match_found while spectating leaves the spectating', async () => {
        mount({spectatingGameId: 8});
        await flush();
        await emit('match_found', MATCH);
        expect(socket.send).toHaveBeenCalledWith('leave_spectate', {game_id: 8});
    });

    it('move_made: position, clocks and version; another game is ignored; a move with the game over — the result', async () => {
        const {opts} = mount();
        await flush();
        opts.gameIdRef.current = 5;
        await emit('move_made', {game_id: 99, fen: AFTER_E4});
        expect(opts.setGame).not.toHaveBeenCalled();
        await emit('move_made', {game_id: 5, state_version: 4, white_time_ms: 1, black_time_ms: 2, san: 'e4', fen: AFTER_E4});
        expect(opts.setStateVersion).toHaveBeenCalledWith(4);
        expect(opts.setWhiteTimeMs).toHaveBeenCalledWith(1);
        expect(opts.playAudio).toHaveBeenCalledWith('move');
        await emit('move_made', {game_id: 5, pgn: '1. e4', game_over: true, result: '1-0'});
        expect(opts.setGameOverResult).toHaveBeenCalledWith('1-0');
        expect(opts.playOutcomeSound).toHaveBeenCalledWith('1-0');
        expect(opts.updateSessionStats).toHaveBeenCalledWith('1-0');
        // A repeated result is not sounded a second time.
        await emit('game_over', {game_id: 5, result: '1-0', reason: 'checkmate', white_time_ms: 3, black_time_ms: 4});
        expect(opts.playOutcomeSound).toHaveBeenCalledTimes(1);
    });

    it('move_made: broken PGN and FEN do not break the board', async () => {
        const {opts} = mount();
        await flush();
        await emit('move_made', {pgn: '1. zz9', fen: 'not a fen'});
        expect(opts.setGame).not.toHaveBeenCalled();
        await emit('move_made', {pgn: '1. zz9', fen: AFTER_E4});
        expect(opts.setGame).toHaveBeenCalled();
    });

    it('a move clears the draw offer: one\'s own move answers an incoming one, the opponent\'s move an outgoing one', async () => {
        const {opts} = mount();
        await flush();
        opts.myColorRef.current = 'white';
        await emit('move_made', {fen: AFTER_E4, san: 'e4'});
        const updater = opts.setDrawOfferStatus.mock.calls.at(-1)![0] as (prev: any) => any;
        expect(typeof updater).toBe('function');
        expect(updater({key: 'status.drawOffered'})).toBeDefined();
        expect(updater(null)).toBeNull();
    });

    it('spectator: the result of another game sounds like a draw and does not go to the statistics', async () => {
        const {opts} = mount({spectatingGameId: 8});
        await flush();
        await emit('game_over', {game_id: 8, result: '0-1', reason: 'resignation'});
        expect(opts.playAudio).toHaveBeenCalledWith('draw');
        expect(opts.updateSessionStats).not.toHaveBeenCalled();
    });

    it('berserk: clocks and a mark; ignored after the game ends', async () => {
        const {opts, result} = mount();
        await flush();
        await emit('berserk', {white_time_ms: 5, black_time_ms: 6, berserk_allowed: false, white_berserk: true});
        expect(opts.setWhiteTimeMs).toHaveBeenCalledWith(5);
        expect(result.current.berserk.white).toBe(true);
        opts.setWhiteTimeMs.mockClear();
        opts.gameOverResultRef.current = '1-0';
        await emit('berserk', {white_time_ms: 7});
        expect(opts.setWhiteTimeMs).not.toHaveBeenCalled();
    });

    it('draw and rematch: events of one\'s own game change the status and sound; foreign ones and those after the result — no', async () => {
        const {opts} = mount();
        await flush();
        await emit('draw_offered', {game_id: 5});
        expect(opts.setDrawOfferStatus).not.toHaveBeenCalled();  // there is no game on the board yet
        opts.gameIdRef.current = 5;
        await emit('draw_offered', {game_id: 5});
        expect(opts.playAudio).toHaveBeenCalledWith('offer');
        await emit('draw_declined', {game_id: 5});
        expect(opts.playAudio).toHaveBeenCalledWith('decline');
        await emit('rematch_offered', {game_id: 5});
        expect(opts.setRematchStatus).toHaveBeenCalledWith('offered_by_opponent');
        await emit('rematch_declined', {});
        expect(opts.setRematchStatus).toHaveBeenCalledWith('declined');
        opts.gameOverResultRef.current = '1-0';
        opts.setDrawOfferStatus.mockClear();
        await emit('draw_offered', {game_id: 5});
        await emit('draw_declined', {game_id: 5});
        expect(opts.setDrawOfferStatus).not.toHaveBeenCalled();
    });

    it('connected returns the challenge to the lobby if a search is on', async () => {
        const {opts, result} = mount();
        await flush();
        await emit('connected');
        expect(socket.send).not.toHaveBeenCalledWith('join_queue', expect.anything());
        await act(async () => result.current.startMatchmaking());
        socket.send.mockClear();
        opts.gameIdRef.current = null;
        await emit('connected');
        expect(socket.send).toHaveBeenCalledWith('join_queue', {base_time_ms: 180000, increment_ms: 2000, rated: true});
    });

    it('invite_created: the code, copying to the clipboard and a "copied" mark', async () => {
        const writeText = vi.fn(async () => undefined);
        Object.defineProperty(navigator, 'clipboard', {value: {writeText}, configurable: true});
        const {result} = mount();
        await flush();
        await emit('invite_created', {});
        expect(result.current.createdInviteCode).toBeNull();
        await emit('invite_created', {code: 'abc'});
        expect(result.current.createdInviteCode).toBe('abc');
        expect(result.current.inviteCopied).toBe(true);
        expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/challenge\/abc$/));
        act(() => result.current.handleCopyInviteLink());
        expect(writeText).toHaveBeenCalledTimes(2);
    });

    it('spectate_started: the board switches to another game; during one\'s own — a refusal', async () => {
        const {opts} = mount();
        await flush();
        opts.gameIdRef.current = 5;
        await emit('spectate_started', {game_id: 8});
        expect(socket.send).toHaveBeenCalledWith('leave_spectate', {game_id: 8});
        expect(opts.setSpectatingGameId).not.toHaveBeenCalled();

        opts.gameIdRef.current = null;
        await emit('spectate_started', {game_id: 8, white_username: 'W', black_username: '', pgn: '1. e4 e5', is_rated: false});
        expect(opts.setSpectatingGameId).toHaveBeenCalledWith(8);
        expect(opts.setMyColor).toHaveBeenCalledWith('white');
        expect(opts.setBlackPlayer).toHaveBeenCalledWith({username: '', rating: '1200'});
        await emit('spectate_started', {game_id: 9, pgn: '1. zz9', fen: START_FEN});
        await emit('spectate_started', {game_id: 9, fen: START_FEN});
        expect(opts.playAudio).toHaveBeenCalledWith('start');
    });

    it('chat: a message goes to the feed, a foreign one sounds, one\'s own — no, empty and another game\'s are ignored', async () => {
        const {opts, result} = mount();
        await flush();
        opts.gameIdRef.current = 5;
        await emit('chat_message', {game_id: 5, sender: 'other', text: 'hello'});
        await emit('chat_message', {game_id: 5, sender: 'me', text: 'reply'});
        await emit('chat_message', {game_id: 5, sender: '', text: ''});
        await emit('chat_message', {game_id: 77, sender: 'other', text: 'miss'});
        expect(result.current.chatMessages.map((m) => m.text)).toEqual(['hello', 'reply']);
        expect(opts.playAudio).toHaveBeenCalledTimes(1);
        expect(opts.playAudio).toHaveBeenCalledWith('chat');
    });

    it('server errors: a code leaves the search, "you are already playing" during a game is not an error, a move with a position returns the board', async () => {
        const {opts} = mount();
        await flush();
        await emit('error', {code: 'self_in_game'});
        expect(opts.setIsSearching).toHaveBeenCalledWith(false);
        opts.setIsSearching.mockClear();
        opts.gameIdRef.current = 5;
        await emit('error', {code: 'self_in_game'});
        expect(opts.setIsSearching).not.toHaveBeenCalled();
        await emit('error', {code: 'rate_limited'});
        expect(opts.setIsSearching).not.toHaveBeenCalled();
        expect(opts.playAudio).not.toHaveBeenCalledWith('illegal');

        await emit('error', {code: 'rate_limited', pgn: '1. e4', state_version: 9});
        expect(opts.playAudio).toHaveBeenCalledWith('illegal');
        expect(opts.setStateVersion).toHaveBeenCalledWith(9);
        expect(opts.clearPremove).toHaveBeenCalled();
        await emit('error', {message: 'boom', fen: AFTER_E4});
        await emit('error', {message: 'boom', pgn: '1. zz9', fen: START_FEN});
        expect(opts.setGame).toHaveBeenCalledTimes(3);
    });
});

describe('useGameSocket: server polling', () => {
    it('one\'s own game in progress from the server is put on the board; a fresher version is caught up', async () => {
        const active = {...MATCH, active: true, state_version: 7};
        stubFetch((url) => (url.includes('/my-active') ? active : undefined));
        const {opts} = mount();
        await flush();
        await flush();
        expect(opts.setGameId).toHaveBeenCalledWith(5);

        opts.gameIdRef.current = 5;
        opts.stateVersionRef.current = 3;
        vi.useFakeTimers();
        const {opts: opts2} = mount({gameIdRef: {current: 5}, stateVersionRef: {current: 3}});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1600);
        });
        expect(opts2.setStateVersion).toHaveBeenCalledWith(7);
    });

    it('the active game disappeared: after two polls the result is taken by summary; an unfinished one — waits', async () => {
        vi.useFakeTimers();
        let summary: any = {status: 'IN_PROGRESS'};
        stubFetch((url) => (url.includes('/summary') ? summary : undefined));
        const {opts} = mount({gameIdRef: {current: 5}});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1600);
        });
        expect(opts.setGameOverResult).not.toHaveBeenCalled();
        summary = {status: 'COMPLETED', result: '1-0', termination: 'timeout'};
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1600);
        });
        expect(opts.setGameOverResult).toHaveBeenCalledWith('1-0');
        expect(opts.setDrawOfferStatus).toHaveBeenCalled();
    });

    it('a cancelled game ends with the result "*"; a summary error is ignored', async () => {
        vi.useFakeTimers();
        let summaryReply: any = 'fail';
        stubFetch((url) => (url.includes('/summary') ? summaryReply : undefined));
        const {opts} = mount({gameIdRef: {current: 5}});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3200);
        });
        expect(opts.setGameOverResult).not.toHaveBeenCalled();
        summaryReply = {status: 'ABORTED'};
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1600);
        });
        expect(opts.setGameOverResult).toHaveBeenCalledWith('*');
    });

    it('the lobby and Live lists are read when there is no own game; during a game the challenges are cleared', async () => {
        stubFetch((url) => {
            if (url.includes('matchmaking/queue')) return [{user_id: 1, username: 'X', rating: 1, base_time_ms: 1, increment_ms: 0}];
            if (url.endsWith('/live')) return [{game_id: 3}];
            return undefined;
        });
        const {result} = mount();
        await flush();
        await flush();
        expect(result.current.queuePlayers).toHaveLength(1);
        expect(result.current.liveGames).toHaveLength(1);
        const during = mount({gameIdRef: {current: 5}});
        await flush();
        expect(during.result.current.queuePlayers).toEqual([]);
    });

    it('a network failure during polling is written to the console', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new TypeError('offline');
        }));
        mount();
        await flush();
        await flush();
        expect(console.error).toHaveBeenCalled();
    });

    it('during a game with a bot my-active is not polled', async () => {
        const fetchMock = stubFetch();
        mount({activeBot: 'morphy' as any});
        await flush();
        await flush();
        expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/my-active'))).toBe(false);
    });
});

describe('useGameSocket: player actions', () => {
    it('opponent search: a queue over WebSocket and over HTTP; a snapshot of the active game from the answer is applied', async () => {
        const fetchMock = stubFetch((url, init) => (url.endsWith('/matchmaking/join') && init?.method === 'POST' ? {...MATCH, active: true} : undefined));
        const {opts, result} = mount({spectatingGameId: 8});
        await flush();
        await act(async () => result.current.startMatchmaking());
        expect(socket.send).toHaveBeenCalledWith('leave_spectate', {game_id: 8});
        expect(socket.send).toHaveBeenCalledWith('join_queue', {base_time_ms: 180000, increment_ms: 2000, rated: true});
        expect(opts.setIsSearching).toHaveBeenCalledWith(true);
        expect(opts.setGameId).toHaveBeenCalledWith(5);
        expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/matchmaking/join'))).toBe(true);
    });

    it('a search without minutes of increment and a casual one; an HTTP failure is ignored', async () => {
        const {opts, result} = mount({effectiveIncSeconds: 0, ratedChoice: false});
        await flush();
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new TypeError('offline');
        }));
        await act(async () => result.current.startMatchmaking());
        expect(socket.send).toHaveBeenCalledWith('join_queue', {base_time_ms: 180000, increment_ms: 0, rated: false});
        expect(opts.setIsSearching).toHaveBeenCalledWith(true);
    });

    it('cancelling the search: WebSocket and HTTP leave', async () => {
        const fetchMock = stubFetch();
        const {opts, result} = mount();
        await flush();
        await act(async () => result.current.cancelMatchmaking());
        expect(socket.send).toHaveBeenCalledWith('leave_queue', {});
        expect(opts.setIsSearching).toHaveBeenCalledWith(false);
        expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/matchmaking/leave'))).toBe(true);
    });

    it('accepting a challenge: WebSocket and HTTP; an answer with a snapshot puts the game, an HTTP failure is written to the console', async () => {
        stubFetch((url) => (url.includes('/matchmaking/accept/') ? {...MATCH} : undefined));
        const {opts, result} = mount();
        await flush();
        await act(async () => result.current.acceptChallenge(9));
        expect(socket.send).toHaveBeenCalledWith('accept_challenge', {target_user_id: 9});
        expect(opts.setGameId).toHaveBeenCalledWith(5);

        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new TypeError('offline');
        }));
        await act(async () => result.current.acceptChallenge(9));
        expect(console.error).toHaveBeenCalled();
    });

    it('accepting a challenge without a login sends only the WebSocket message', async () => {
        const fetchMock = stubFetch();
        const {result} = mount();
        await flush();
        fetchMock.mockClear();
        setToken(null);
        await act(async () => result.current.acceptChallenge(9));
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('a draw offer, accepting and declining, a rematch, berserk, spectating', async () => {
        const {opts, result} = mount({gameId: 5});
        await flush();
        act(() => result.current.handleOfferDraw());
        expect(socket.send).toHaveBeenCalledWith('offer_draw', {game_id: 5});
        act(() => result.current.acceptDraw());
        act(() => result.current.declineDraw());
        act(() => result.current.handleAcceptRematch());
        act(() => result.current.handleDeclineRematch());
        act(() => result.current.handleBerserk());
        act(() => result.current.handleSpectateGame(12));
        for (const [action, payload] of [['accept_draw', {game_id: 5}], ['decline_draw', {game_id: 5}],
            ['accept_rematch', {game_id: 5}], ['decline_rematch', {game_id: 5}], ['berserk', {game_id: 5}],
            ['spectate_game', {game_id: 12}]] as const) {
            expect(socket.send).toHaveBeenCalledWith(action, payload);
        }
        expect(opts.setRematchStatus).toHaveBeenCalledWith('none');
    });

    it('without a game or after the result the actions send nothing', async () => {
        const {result} = mount({gameId: null});
        await flush();
        act(() => {
            result.current.handleOfferDraw();
            result.current.acceptDraw();
            result.current.declineDraw();
            result.current.handleAcceptRematch();
            result.current.handleDeclineRematch();
            result.current.handleBerserk();
            result.current.handleCopyInviteLink();
        });
        expect(socket.send).not.toHaveBeenCalled();
        const over = mount({gameId: 5, gameOverResult: '1-0'});
        act(() => {
            over.result.current.handleOfferDraw();
            over.result.current.handleBerserk();
        });
        expect(socket.send).not.toHaveBeenCalled();
    });

    it('an invitation link: ordinary, Fischer and with a handicap', async () => {
        const {result} = mount();
        await flush();
        act(() => result.current.handleCreatePrivateInvite());
        expect(socket.send).toHaveBeenLastCalledWith('create_invite', {
            base_time_ms: 180000, increment_ms: 2000, color_pref: 'random', rated: true,
        });
        const fischer = mount({inviteVariant: 'chess960'});
        act(() => fischer.result.current.handleCreatePrivateInvite());
        expect(socket.send).toHaveBeenLastCalledWith('create_invite', expect.objectContaining({variant: 'chess960'}));
        const odds = mount({inviteOdds: {kind: 'time', ratio: 2} as any});
        act(() => odds.result.current.handleCreatePrivateInvite());
        expect(socket.send).toHaveBeenCalledTimes(3);
    });

    it('chat: text and a quick phrase go to the active game; empty text is not sent', async () => {
        const {result} = mount({gameId: null, spectatingGameId: 8});
        await flush();
        act(() => result.current.handleSendChatMessage());
        expect(socket.send).not.toHaveBeenCalled();
        act(() => result.current.setChatInput('  hello '));
        act(() => result.current.handleSendChatMessage());
        expect(socket.send).toHaveBeenCalledWith('chat_message', {game_id: 8, text: 'hello'});
        expect(result.current.chatInput).toBe('');
        act(() => result.current.handleSendChatPreset('gg' as any));
        expect(socket.send).toHaveBeenLastCalledWith('chat_message', {game_id: 8, preset: 'gg'});
        const idle = mount();
        act(() => idle.result.current.handleSendChatPreset('gg' as any));
        expect(socket.send).toHaveBeenCalledTimes(2);
    });
});

describe('useGameSocket: invitation by address', () => {
    it('after 450 ms it accepts the invitation and removes the code from the address; without a login — no', async () => {
        vi.useFakeTimers();
        const {opts} = mount({inviteCode: 'xyz'});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(500);
        });
        expect(socket.send).toHaveBeenCalledWith('accept_invite', {code: 'xyz'});
        expect(opts.navigate).toHaveBeenCalledWith('/', {replace: true});
        socket.send.mockClear();
        setToken(null);
        mount({inviteCode: 'xyz'});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(500);
        });
        expect(socket.send).not.toHaveBeenCalled();
    });
});
