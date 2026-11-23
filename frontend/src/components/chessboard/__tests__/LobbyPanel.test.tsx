// The "Lobby / Live" tab (LobbyPanel): empty states, rows of challenges and of games in progress, the casual
// game badge, blocking buttons during one's own game, switching tabs. The arena announcement is a fetch stub.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {LobbyPanel} from '../LobbyPanel';
import type {LobbyPanelProps} from '../LobbyPanel';
import {makeI18n} from '../../../i18n';

const {t} = makeI18n('en');

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

const CHALLENGE = {user_id: 5, username: 'Anna', rating: 1500, base_time_ms: 180000, increment_ms: 2000};
const LIVE = {game_id: 9, white_username: 'Whitey', white_rating: 1, black_username: '', black_rating: 2,
    base_time_ms: 300000, increment_ms: 0, spectators_count: 3, is_rated: false};

describe('LobbyPanel', () => {
    it('an empty lobby shows a hint', () => {
        setup();
        expect(screen.getByText(t('lobby.empty'))).toBeInTheDocument();
    });

    it('an empty lobby while searching shows waiting', () => {
        setup({isSearching: true});
        expect(screen.getByText(t('lobby.waiting'))).toBeInTheDocument();
    });

    it('a challenge: accept, the casual badge and a nameless player', () => {
        const props = setup({queuePlayers: [CHALLENGE, {...CHALLENGE, user_id: 6, username: '', rated: false}]});
        expect(screen.getByText('Anna')).toBeInTheDocument();
        expect(screen.getByText(t('lobby.unknownPlayer'))).toBeInTheDocument();
        expect(screen.getAllByText(t('lobby.casualBadge'))).toHaveLength(1);
        fireEvent.click(screen.getAllByRole('button', {name: new RegExp(t('lobby.accept'))})[0]);
        expect(props.onAcceptChallenge).toHaveBeenCalledWith(5);
    });

    it('an own game in progress blocks accepting a challenge', () => {
        setup({queuePlayers: [CHALLENGE], gameId: 3});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.accept'))})).toBeDisabled();
    });

    it('after the game ends a challenge can be accepted', () => {
        setup({queuePlayers: [CHALLENGE], gameId: 3, gameOverResult: '1-0'});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.accept'))})).toBeEnabled();
    });

    it('the Live tab: a game row, watching and returning to challenges', () => {
        const props = setup({lobbyTab: 'live', liveGames: [LIVE]});
        expect(screen.getByText(t('common.black'))).toBeInTheDocument();
        expect(screen.getByText(t('lobby.casualBadge'))).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: new RegExp(t('lobby.watch'))}));
        expect(props.onSpectateGame).toHaveBeenCalledWith(9);
        fireEvent.click(screen.getByRole('button', {name: new RegExp(t('lobby.challenges'))}));
        expect(props.onLobbyTabChange).toHaveBeenCalledWith('lobby');
    });

    it('the Live tab without games and switching to it', () => {
        const props = setup({lobbyTab: 'live'});
        expect(screen.getByText(t('lobby.noLiveGames'))).toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button')[1]);
        expect(props.onLobbyTabChange).toHaveBeenCalledWith('live');
    });

    it('during an own game in progress watching is unavailable', () => {
        setup({lobbyTab: 'live', liveGames: [LIVE], gameId: 3});
        expect(screen.getByRole('button', {name: new RegExp(t('lobby.watch'))})).toBeDisabled();
    });
});
