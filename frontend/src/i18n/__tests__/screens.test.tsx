// --- FILE: frontend/src/i18n/__tests__/screens.test.tsx ---
// Key screens in both languages: headings and labels come from their own catalog, the data (including
// the config getters — board names, time controls, bot names) is translated together with the interface,
// and the switcher changes the language on the fly, without a reload and without losing the page state.

import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import About from '../../components/About';
import AuthModal from '../../components/AuthModal';
import Leaderboard from '../../components/Leaderboard';
import LanguageSwitcher from '../../components/LanguageSwitcher';
import Settings from '../../components/Settings';
import {GameChatPanel} from '../../components/chessboard/GameChatPanel';
import {HISTORICAL_BOTS, CHAMPIONS_LIST} from '../../config/champions';
import {BOARD_THEMES, PIECE_SETS} from '../../config/boardAppearance';
import {ALL_TIME_CONTROLS, TIME_CONTROLS} from '../../config/timeControls';
import {describeGameOver, renderStatus} from '../../components/chessboard/status';
import {LANGUAGE_STORAGE_KEY, getLanguage, makeI18n, setLanguage, type Language} from '../index';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => []}) as unknown as Response));
});

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
});

const HEADINGS: Record<Language, { settings: string; about: string; login: string; leaderboard: string }> = {
    en: {settings: 'Settings', about: 'About and licenses', login: 'Log in to regence', leaderboard: 'Regence leaderboard'},
    uk: {settings: 'Налаштування', about: 'Про проєкт і ліцензії', login: 'Вхід до regence', leaderboard: 'Таблиця лідерів Regence'},
};

describe.each(['en', 'uk'] as const)('screens in language %s', (language) => {
    beforeEach(() => setLanguage(language, {persist: false}));

    it('settings', () => {
        render(<MemoryRouter><Settings token={null} username={null} onTokenChange={vi.fn()} onLogoutEverywhere={vi.fn()}/></MemoryRouter>);
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent(HEADINGS[language].settings);
        // Board names come from the config — and are also in this language.
        expect(screen.getByRole('button', {name: BOARD_THEMES.walnut.name})).toBeInTheDocument();
    });

    it('about the project', () => {
        render(<MemoryRouter><About/></MemoryRouter>);
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent(HEADINGS[language].about);
        expect(screen.getByRole('link', {name: 'github.com/official-stockfish/Stockfish'})).toBeInTheDocument();
    });

    it('the login window', () => {
        render(<AuthModal onSuccess={vi.fn()}/>);
        expect(screen.getByRole('dialog', {name: HEADINGS[language].login})).toBeInTheDocument();
    });

    it('the leaderboard', async () => {
        render(<MemoryRouter><Leaderboard/></MemoryRouter>);
        expect(await screen.findByRole('heading', {level: 1})).toHaveTextContent(HEADINGS[language].leaderboard);
    });

    it('quick chat phrases — in the reader\'s language', () => {
        render(<GameChatPanel
            messages={[{sender: 'bob', text: '', preset: 'thanks', timestamp: 1}]}
            chatInput="" onChatInputChange={vi.fn()} onSendMessage={vi.fn()} onSendPreset={vi.fn()}
            isSpectator={false} onLeaveSpectate={vi.fn()}/>);
        const thanks = makeI18n(language).t('chat.presets.thanks');
        expect(screen.getAllByText(thanks).length).toBe(2); // the button and the message in the feed
    });
});

describe('config data is translated together with the interface', () => {
    it('bots, champions, boards, pieces and time controls', () => {
        setLanguage('en', {persist: false});
        expect(HISTORICAL_BOTS.morphy.name).toBe('Paul Charles Morphy');
        expect(CHAMPIONS_LIST.find((c) => c.id === 'Ding')!.years).toBe('2023–present');
        expect(PIECE_SETS.cburnett.shortName).toBe('Staunton');
        expect(TIME_CONTROLS[1].title).toBe('Blitz');
        expect(ALL_TIME_CONTROLS.find((o) => o.id === 'blitz-3+2')!.label).toBe('3 min + 2 sec/move');
        expect(ALL_TIME_CONTROLS.find((o) => o.id === 'bullet-manual')!.label).toBe('Manual setup (Bullet)');

        setLanguage('uk', {persist: false});
        expect(HISTORICAL_BOTS.morphy.name).toBe('Пол Чарлз Морфі');
        expect(CHAMPIONS_LIST.find((c) => c.id === 'Ding')!.years).toBe('2023–дотепер');
        expect(BOARD_THEMES.walnut.name).toBe('Горіх');
        expect(ALL_TIME_CONTROLS.find((o) => o.id === 'blitz-3+2')!.label).toBe('3 хв + 2 с/хід');
    });

    it('every champion has a years label, non-champions — "years of play"', () => {
        const careers = CHAMPIONS_LIST.filter((c) => !c.worldChampion).map((c) => c.id);
        expect(careers.sort()).toEqual(['Geller', 'Keres', 'Korchnoi', 'Rubinstein']);
    });

    it('the game result — in the display language, not in the event language', () => {
        const summary = describeGameOver('1-0', 'checkmate')!;
        expect(renderStatus(summary, makeI18n('en').t)).toBe('Game over. Result: 1-0 (checkmate)');
        expect(renderStatus(summary, makeI18n('uk').t)).toBe('Партію закінчено. Результат: 1-0 (мат)');
        expect(renderStatus(describeGameOver('*', 'aborted')!, makeI18n('en').t)).toMatch(/aborted/i);
        // An unknown reason does not break the string — the result is shown without an explanation.
        expect(renderStatus(describeGameOver('0-1', 'something_new')!, makeI18n('en').t)).toBe('Game over. Result: 0-1');
    });
});

describe('language switcher', () => {
    it('changes the language of the whole page without a reload and remembers the choice', () => {
        setLanguage('en', {persist: false});
        render(
            <MemoryRouter>
                <LanguageSwitcher/>
                <Settings token={null} username={null} onTokenChange={vi.fn()} onLogoutEverywhere={vi.fn()}/>
            </MemoryRouter>,
        );
        const select = screen.getAllByRole('combobox')[0];
        expect(within(select).getByRole('option', {name: 'Українська'})).toBeInTheDocument();

        act(() => {
            fireEvent.change(select, {target: {value: 'uk'}});
        });
        expect(getLanguage()).toBe('uk');
        expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('uk');
        expect(document.documentElement.lang).toBe('uk');
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Налаштування');

        act(() => {
            fireEvent.change(select, {target: {value: 'en'}});
        });
        expect(screen.getByRole('heading', {level: 1})).toHaveTextContent('Settings');
    });

    it('an unknown value is ignored', () => {
        setLanguage('en', {persist: false});
        render(<LanguageSwitcher/>);
        act(() => {
            fireEvent.change(screen.getByRole('combobox'), {target: {value: 'de'}});
        });
        expect(getLanguage()).toBe('en');
    });

    it('in the compact switcher Ukrainian is labelled UA, not UK (that is the United Kingdom)', () => {
        render(<LanguageSwitcher compact/>);
        const labels = within(screen.getByRole('combobox')).getAllByRole('option').map((o) => o.textContent);
        expect(labels).toEqual(['EN', 'UA']);
        // The language code in the app stays standard (ISO 639-1).
        expect(within(screen.getByRole('combobox')).getByRole('option', {name: 'UA'})).toHaveAttribute('value', 'uk');
    });
});
