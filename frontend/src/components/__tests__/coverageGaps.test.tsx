// Frontend coverage (tasks 8.7 and 17.6): the appearance dropdown, the tournament history, the diploma, the sound engine.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {AppearancePickerDropdown} from '../chessboard/AppearancePickerDropdown';
import {TournamentHistory} from '../tournaments/TournamentHistory';
import {Diploma} from '../tournaments/Diploma';
import {BOARD_THEMES, PIECE_SETS} from '../../config/boardAppearance';
import {setToken} from '../../services/authToken';
import {SOUND_SETS, resolveMoveSound, soundEngine} from '../../services/soundEngine';

afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
});

describe('board appearance dropdown', () => {
    function picker(isOpen: boolean) {
        const handlers = {
            onToggleOpen: vi.fn(), onClose: vi.fn(), onPieceSetChange: vi.fn(), onThemeChange: vi.fn(), onBoardSizeChange: vi.fn(),
        };
        render(<AppearancePickerDropdown isOpen={isOpen} activeTheme={BOARD_THEMES.walnut} pieceSetKey="merida"
                                         activePieceSetName="Merida" activePieceSetShortName="Merida" boardSize={560}
                                         responsiveBoardPx={560} {...handlers}/>);
        return handlers;
    }

    it('closed — only the button; a click opens it', () => {
        const h = picker(false);
        expect(screen.queryByText('Oak')).toBeNull();
        fireEvent.click(screen.getByTitle('Choose the piece set, theme and size of the board'));
        expect(h.onToggleOpen).toHaveBeenCalled();
    });

    it('open — all the sets and boards, the size and "auto"', () => {
        const h = picker(true);
        expect(screen.getAllByRole('button').length).toBeGreaterThan(Object.keys(PIECE_SETS).length + Object.keys(BOARD_THEMES).length);
        fireEvent.click(screen.getByText('Oak'));
        expect(h.onThemeChange).toHaveBeenCalledWith('oak');
        fireEvent.click(screen.getByTitle(PIECE_SETS.celtic.description));
        expect(h.onPieceSetChange).toHaveBeenCalledWith('celtic');
        const slider = screen.getByRole('slider');
        const middle = Math.round((Number(slider.getAttribute('min')) + Number(slider.getAttribute('max'))) / 2);
        fireEvent.change(slider, {target: {value: String(middle)}});
        expect(h.onBoardSizeChange).toHaveBeenCalledWith(middle);
        fireEvent.click(screen.getByText('Auto'));
        expect(h.onBoardSizeChange).toHaveBeenCalledTimes(2);
    });
});

describe('tournament history in the profile', () => {
    const tournaments = [
        {id: 1, format: 'round_robin', size: 4, status: 'finished', created_at: '2026-11-01', my_place: 2},
        {id: 2, format: 'swiss', size: 8, status: 'active', created_at: '2026-11-02', my_place: null},
    ];

    function stubApi(me: string) {
        vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
            ok: true, status: 200, json: async () => (String(url).includes('/profile/me') ? {username: me} : tournaments),
        } as Response)));
    }

    it('own profile — a list with the place and the status, links to the tournaments', async () => {
        setToken('jwt');
        stubApi('alice');
        render(<MemoryRouter><TournamentHistory username="alice"/></MemoryRouter>);
        const history = await screen.findByTestId('tournament-history');
        expect(history).toHaveTextContent('Place 2 of 4');
        expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual(['/tournaments/1', '/tournaments/2']);
    });

    it('someone else\'s profile and a guest — nothing', async () => {
        setToken('jwt');
        stubApi('bob');
        const {container} = render(<MemoryRouter><TournamentHistory username="alice"/></MemoryRouter>);
        await waitFor(() => expect(fetch).toHaveBeenCalled());
        expect(container).toBeEmptyDOMElement();
        setToken(null);
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        render(<MemoryRouter><TournamentHistory username="alice"/></MemoryRouter>);
        expect(fetchMock).not.toHaveBeenCalled();
    });
});

describe('prizewinner diploma', () => {
    it('name, place, medal; printing opens a window and prints', () => {
        render(<Diploma name="alice" place={1} format="Round robin" size={4} date="15.11.2026"/>);
        const svg = screen.getByRole('img');
        expect(svg).toHaveTextContent('alice');
        expect(screen.getByTestId('diploma-medal').getAttribute('fill')).toBe('#d4a017');
        const win = {document: {write: vi.fn(), close: vi.fn()}, focus: vi.fn(), print: vi.fn()};
        vi.spyOn(window, 'open').mockReturnValue(win as unknown as Window);
        fireEvent.click(screen.getByRole('button', {name: 'Print'}));
        expect(win.document.write.mock.calls[0][0]).toContain('<svg');
        expect(win.print).toHaveBeenCalled();
    });

    it('saving to PNG: the picture is drawn on a canvas and downloaded', () => {
        render(<Diploma name="alice" place={3} format="Swiss" size={8} date="15.11.2026"/>);
        URL.createObjectURL = vi.fn(() => 'blob:x');
        URL.revokeObjectURL = vi.fn();
        const images: { onload: (() => void) | null; src: string }[] = [];
        vi.stubGlobal('Image', class {
            onload: (() => void) | null = null;
            src = '';
            constructor() {
                images.push(this);
            }
        });
        const drawImage = vi.fn();
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({drawImage} as unknown as CanvasRenderingContext2D);
        vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,AA');
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
        fireEvent.click(screen.getByRole('button', {name: 'Save as PNG'}));
        expect(images[0].src).toBe('blob:x');
        act(() => images[0].onload?.());
        expect(drawImage).toHaveBeenCalled();
        expect(click).toHaveBeenCalled();
    });
});

describe('sound engine', () => {
    function fakeAudio() {
        const param = () => ({setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn()});
        const node = () => ({connect: vi.fn(), start: vi.fn(), stop: vi.fn(), frequency: param(), gain: param(), Q: param(), type: '', buffer: null});
        const created = {osc: [] as { frequency: ReturnType<typeof param>; type: string }[]};
        class FakeContext {
            currentTime = 0;
            sampleRate = 8000;
            state = 'running';
            destination = {};
            createOscillator() {
                const osc = node();
                created.osc.push(osc);
                return osc;
            }
            createGain() { return node(); }
            createBiquadFilter() { return node(); }
            createBufferSource() { return node(); }
            createBuffer(_c: number, length: number) { return {getChannelData: () => new Float32Array(length)}; }
            resume() { return Promise.resolve(); }
        }
        vi.stubGlobal('AudioContext', FakeContext);
        return created;
    }

    it('all events sound; without sound — silence; the sound set changes pitch and timbre', () => {
        const created = fakeAudio();
        // A new engine with a replaced AudioContext: the module holds a single instance, the context is created lazily.
        (soundEngine as unknown as { ctx: unknown }).ctx = null;
        soundEngine.setMuted(false);
        soundEngine.setSoundSet('wood');
        for (const event of ['move', 'capture', 'castle', 'check', 'promote', 'premove', 'illegal', 'start', 'chat', 'offer',
            'decline', 'low_time', 'victory', 'defeat', 'draw'] as const) {
            soundEngine.play(event);
        }
        const woodCount = created.osc.length;
        expect(woodCount).toBeGreaterThan(20);
        soundEngine.setMuted(true);
        soundEngine.play('victory');
        expect(created.osc.length).toBe(woodCount);
        expect(soundEngine.toggleMute()).toBe(false);
        soundEngine.setSoundSet('bright');
        soundEngine.play('chat');
        const last = created.osc[created.osc.length - 1];
        expect(last.type).toBe(SOUND_SETS.bright.wave);
        expect(last.frequency.setValueAtTime.mock.calls[0][0]).toBeCloseTo(880 * SOUND_SETS.bright.pitch);
        expect(localStorage.getItem('regence_sound_set')).toBe('bright');
        soundEngine.setSoundSet('wood');
    });

    it('the move sound by notation', () => {
        expect(resolveMoveSound(null)).toBe('move');
        expect(resolveMoveSound('Qh7#')).toBe('move');   // outside training there is no check sound
        expect(resolveMoveSound('e8=Q')).toBe('promote');
        expect(resolveMoveSound('O-O-O')).toBe('castle');
        expect(resolveMoveSound('Nxe5')).toBe('capture');
        expect(resolveMoveSound('e4')).toBe('move');
    });
});
