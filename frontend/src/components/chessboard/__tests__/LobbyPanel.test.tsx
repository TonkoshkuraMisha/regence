// Вкладка «Лобби / Live» (LobbyPanel): пустые состояния, строки вызовов и идущих партий, значок товарищеской
// партии, блокировка кнопок при своей идущей партии, переключение вкладок. Анонс арены — заглушка fetch.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {LobbyPanel} from '../LobbyPanel';
import type {LobbyPanelProps} from '../LobbyPanel';
import {makeI18n} from '../../../i18n';

const {t} = makeI18n('ru');

beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({arena: null}), headers: new Headers()}) as Response));
});
afterEach(() => vi.unstubAllGlobals());

function setup(over: Partial<LobbyPanelProps> = {}) {
    const props: LobbyPanelProps = {
        lobbyTab: 'lobby', onLobbyTabChange: vi.fn(), queuePlayers: [], liveGames: [], isSearching: false,
        gameId: null, gameOverResult: null, onAcceptChallenge: vi.fn(), onSpectateGame: vi.fn(), ...over,
    };
    render(<MemoryRouter><LobbyPanel {...props}/></MemoryRouter>);
    return props;
}

const CHALLENGE = {user_id: 5, username: 'Анна', rating: 1500, base_time_ms: 180000, increment_ms: 2000};
const LIVE = {game_id: 9, white_username: 'Белый', white_rating: 1, black_username: '', black_rating: 2,
    base_time_ms: 300000, increment_ms: 0, spectators_count: 3, is_rated: false};

describe('LobbyPanel', () => {
    it('пустое лобби показывает подсказку', () => {
        setup();
        expect(screen.getByText(t('lobby.empty'))).toBeInTheDocument();
    });

    it('пустое лобби при поиске показывает ожидание', () => {
        setup({isSearching: true});
        expect(screen.getByText(t('lobby.waiting'))).toBeInTheDocument();
    });

    it('вызов: принять, значок товарищеской и безымянный игрок', () => {
        const props = setup({queuePlayers: [CHALLENGE, {...CHALLENGE, user_id: 6, username: '', rated: false}]});
        expect(screen.getByText('Анна')).toBeInTheDocument();
        expect(screen.getByText(t('lobby.unknownPlayer'))).toBeInTheDocument();
        expect(screen.getAllByText(t('lobby.casualBadge'))).toHaveLength(1);
        fireEvent.click(screen.getAllByRole('button', {name: new RegExp(t('lobby.accept'))})[0]);
        expect(props.onAcceptChallenge).toHaveBeenCalledWith(5);
    });

    it('своя идущая партия блокирует принятие вызова', () => {
        setup({queuePlayers: [CHALLENGE], gameId: 3});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.accept'))})).toBeDisabled();
    });

    it('после окончания партии принять вызов можно', () => {
        setup({queuePlayers: [CHALLENGE], gameId: 3, gameOverResult: '1-0'});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.accept'))})).toBeEnabled();
    });

    it('вкладка Live: строка партии, просмотр и возврат к вызовам', () => {
        const props = setup({lobbyTab: 'live', liveGames: [LIVE]});
        expect(screen.getByText(t('common.black'))).toBeInTheDocument();
        expect(screen.getByText(t('lobby.casualBadge'))).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: new RegExp(t('lobby.watch'))}));
        expect(props.onSpectateGame).toHaveBeenCalledWith(9);
        fireEvent.click(screen.getByRole('button', {name: new RegExp(t('lobby.challenges'))}));
        expect(props.onLobbyTabChange).toHaveBeenCalledWith('lobby');
    });

    it('вкладка Live без партий и переход на неё', () => {
        const props = setup({lobbyTab: 'live'});
        expect(screen.getByText(t('lobby.noLiveGames'))).toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button')[1]);
        expect(props.onLobbyTabChange).toHaveBeenCalledWith('live');
    });

    it('при своей идущей партии просмотр недоступен', () => {
        setup({lobbyTab: 'live', liveGames: [LIVE], gameId: 3});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.watch'))})).toBeDisabled();
    });
});
