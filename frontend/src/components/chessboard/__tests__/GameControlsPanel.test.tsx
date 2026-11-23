// Game control buttons (GameControlsPanel): three modes. PvP — abort or resign, draw, berserk, rematch (offer,
// accept, decline, waiting, refusal), "Review" and PGN after the game; bot — take back, resign, rematch, draw, review of
// the saved game; free board — a position from FEN (success and error), take back and reset.

import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {GameControlsPanel} from '../GameControlsPanel';
import type {GameControlsPanelProps} from '../GameControlsPanel';
import {makeI18n} from '../../../i18n';

const {t} = makeI18n('en');

function setup(over: Partial<GameControlsPanelProps> = {}) {
    const props: GameControlsPanelProps = {
        mode: 'pvp', gameId: 7, savedBotGameId: null, historyLength: 4, gameOverResult: null, rematchStatus: 'none',
        isBotThinking: false, whitePlayer: {username: 'Anya', rating: '1500'}, blackPlayer: {username: 'Bob', rating: ''},
        navigate: vi.fn(), onAbortGame: vi.fn(), onResign: vi.fn(), onOfferDraw: vi.fn(), onAcceptRematch: vi.fn(),
        onDeclineRematch: vi.fn(), onOfferRematch: vi.fn(), onResetSandbox: vi.fn(), onUndoSandboxMove: vi.fn(), ...over,
    };
    render(<GameControlsPanel {...props}/>);
    return props;
}

const button = (name: string) => screen.getByRole('button', {name: new RegExp(name)});

describe('GameControlsPanel: a game with a person', () => {
    it('at the start of the game "Abort" replaces "Resign", and a draw is unavailable', () => {
        const props = setup({historyLength: 1});
        fireEvent.click(button(t('controls.abort')));
        expect(props.onAbortGame).toHaveBeenCalled();
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.resign'))})).toBeNull();
        expect(button(t('controls.offerDraw'))).toBeDisabled();
    });

    it('during the game: resign, draw and berserk', () => {
        const onBerserk = vi.fn();
        const props = setup({onBerserk});
        fireEvent.click(button(t('controls.resign')));
        fireEvent.click(button(t('controls.offerDraw')));
        fireEvent.click(screen.getByTestId('berserk-button'));
        expect(props.onResign).toHaveBeenCalled();
        expect(props.onOfferDraw).toHaveBeenCalled();
        expect(onBerserk).toHaveBeenCalled();
    });

    it('after the end there is no berserk, and the resign and draw buttons are unavailable', () => {
        setup({onBerserk: vi.fn(), gameOverResult: '1-0'});
        expect(screen.queryByTestId('berserk-button')).toBeNull();
        expect(button(t('controls.resign'))).toBeDisabled();
        expect(button(t('controls.offerDraw'))).toBeDisabled();
    });

    it('after the game: rematch, "To the lobby", review with the route state and a PGN link', () => {
        const props = setup({gameOverResult: '1-0'});
        fireEvent.click(button(t('controls.rematch')));
        fireEvent.click(button(t('controls.toLobby')));
        expect(props.onOfferRematch).toHaveBeenCalled();
        expect(props.onResetSandbox).toHaveBeenCalled();
        fireEvent.click(button(t('common.gameReview')));
        expect(props.navigate).toHaveBeenCalledWith('/game/7', {state: {game: expect.objectContaining({
            game_id: 7, white_username: 'Anya', white_rating: 1500, black_rating: 1200, result: '1-0',
        })}});
        expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringMatching(/\/profile\/games\/7\/pgn$/));
    });

    it('the opponent offered a rematch: accept and decline', () => {
        const props = setup({gameOverResult: '0-1', rematchStatus: 'offered_by_opponent'});
        fireEvent.click(button(t('controls.acceptRematch')));
        fireEvent.click(button(t('common.decline')));
        expect(props.onAcceptRematch).toHaveBeenCalled();
        expect(props.onDeclineRematch).toHaveBeenCalled();
    });

    it('waiting for an answer and a refusal block a repeated offer', () => {
        setup({gameOverResult: '1/2-1/2', rematchStatus: 'offered_by_me'});
        expect(button(t('controls.waitingAnswer'))).toBeDisabled();
    });

    it('the refusal of a rematch is shown on the button', () => {
        setup({gameOverResult: '1/2-1/2', rematchStatus: 'declined'});
        expect(button(t('controls.rematchDeclined'))).toBeDisabled();
    });

    it('a cancelled game has no review and no PGN', () => {
        setup({gameOverResult: '*'});
        expect(screen.queryByRole('button', {name: new RegExp(t('common.gameReview'))})).toBeNull();
        expect(screen.queryByRole('link')).toBeNull();
    });

    it('a review without a game number leads nowhere', () => {
        const props = setup({gameOverResult: '1-0', gameId: null});
        fireEvent.click(button(t('common.gameReview')));
        expect(props.navigate).not.toHaveBeenCalled();
    });
});

describe('GameControlsPanel: a game with a bot', () => {
    it('take back, resign and draw', () => {
        const props = setup({mode: 'bot'});
        fireEvent.click(button(t('controls.undoMove')));
        fireEvent.click(button(t('controls.resign')));
        fireEvent.click(screen.getByTestId('bot-offer-draw'));
        expect(props.onUndoSandboxMove).toHaveBeenCalled();
        expect(props.onResign).toHaveBeenCalled();
        expect(props.onOfferDraw).toHaveBeenCalled();
    });

    it('a ladder game: take back is closed; the bot is thinking — take back and draw are unavailable', () => {
        setup({mode: 'bot', undoLocked: true, isBotThinking: true});
        expect(button(t('controls.undoMove'))).toBeDisabled();
        expect(screen.getByTestId('bot-offer-draw')).toBeDisabled();
    });

    it('after the game: rematch and review of the saved game with a fallback Black rating', () => {
        const props = setup({mode: 'bot', gameOverResult: '0-1', savedBotGameId: 12});
        expect(screen.queryByTestId('bot-offer-draw')).toBeNull();
        fireEvent.click(button(t('controls.rematch')));
        expect(props.onOfferRematch).toHaveBeenCalled();
        fireEvent.click(button(t('common.gameReview')));
        expect(props.navigate).toHaveBeenCalledWith('/game/12', {state: {game: expect.objectContaining({
            game_id: 12, black_rating: 1850, site: 'Regence Bot Arena',
        })}});
        expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringMatching(/\/games\/12\/pgn$/));
    });

    it('a tournament game (hideRematch): after the end the row of buttons is hidden', () => {
        setup({mode: 'bot', gameOverResult: '1-0', hideRematch: true});
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.rematch'))})).toBeNull();
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.undoMove'))})).toBeNull();
    });
});

describe('GameControlsPanel: free board', () => {
    it('without moves take back and reset are unavailable, with a custom position reset is available', () => {
        setup({mode: 'sandbox', historyLength: 0, hasCustomPosition: true});
        expect(button(t('controls.undoSandbox'))).toBeDisabled();
        expect(button(t('controls.resetBoard'))).toBeEnabled();
    });

    it('take back and reset call the handlers', () => {
        const props = setup({mode: 'sandbox'});
        fireEvent.click(button(t('controls.undoSandbox')));
        fireEvent.click(button(t('controls.resetBoard')));
        expect(props.onUndoSandboxMove).toHaveBeenCalled();
        expect(props.onResetSandbox).toHaveBeenCalled();
    });

    it('a position from FEN: the error is shown, success clears the field, empty input is ignored', () => {
        const onLoadFen = vi.fn()
            .mockReturnValueOnce('Invalid position')
            .mockReturnValueOnce(null);
        setup({mode: 'sandbox', onLoadFen});
        const input = screen.getByLabelText(t('controls.fenLabel'));
        const form = input.closest('form')!;
        fireEvent.submit(form);
        expect(onLoadFen).not.toHaveBeenCalled();
        expect(button(t('controls.setPosition'))).toBeDisabled();

        fireEvent.change(input, {target: {value: 'bad fen'}});
        fireEvent.submit(form);
        expect(screen.getByRole('alert')).toHaveTextContent('Invalid position');
        fireEvent.change(input, {target: {value: '8/8/8/8/8/8/8/K6k w - - 0 1'}});
        expect(screen.queryByRole('alert')).toBeNull();
        fireEvent.submit(form);
        expect(input).toHaveValue('');
        expect(onLoadFen).toHaveBeenCalledTimes(2);
    });
});
