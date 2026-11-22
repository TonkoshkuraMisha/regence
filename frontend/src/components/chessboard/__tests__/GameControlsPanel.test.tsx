// Кнопки управления партией (GameControlsPanel): три режима. PvP — отмена или сдача, ничья, берсерк, реванш (предложить,
// принять, отклонить, ожидание, отказ), «Разбор» и PGN после партии; бот — возврат хода, сдача, реванш, ничья, разбор
// сохранённой партии; свободная доска — позиция из FEN (успех и ошибка), возврат хода и сброс.

import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {GameControlsPanel} from '../GameControlsPanel';
import type {GameControlsPanelProps} from '../GameControlsPanel';
import {makeI18n} from '../../../i18n';

const {t} = makeI18n('ru');

function setup(over: Partial<GameControlsPanelProps> = {}) {
    const props: GameControlsPanelProps = {
        mode: 'pvp', gameId: 7, savedBotGameId: null, historyLength: 4, gameOverResult: null, rematchStatus: 'none',
        isBotThinking: false, whitePlayer: {username: 'Аня', rating: '1500'}, blackPlayer: {username: 'Боб', rating: ''},
        navigate: vi.fn(), onAbortGame: vi.fn(), onResign: vi.fn(), onOfferDraw: vi.fn(), onAcceptRematch: vi.fn(),
        onDeclineRematch: vi.fn(), onOfferRematch: vi.fn(), onResetSandbox: vi.fn(), onUndoSandboxMove: vi.fn(), ...over,
    };
    render(<GameControlsPanel {...props}/>);
    return props;
}

const button = (name: string) => screen.getByRole('button', {name: new RegExp(name)});

describe('GameControlsPanel: партия с человеком', () => {
    it('в начале партии вместо «Сдаться» — «Отменить», а ничья недоступна', () => {
        const props = setup({historyLength: 1});
        fireEvent.click(button(t('controls.abort')));
        expect(props.onAbortGame).toHaveBeenCalled();
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.resign'))})).toBeNull();
        expect(button(t('controls.offerDraw'))).toBeDisabled();
    });

    it('в ходе партии: сдача, ничья и берсерк', () => {
        const onBerserk = vi.fn();
        const props = setup({onBerserk});
        fireEvent.click(button(t('controls.resign')));
        fireEvent.click(button(t('controls.offerDraw')));
        fireEvent.click(screen.getByTestId('berserk-button'));
        expect(props.onResign).toHaveBeenCalled();
        expect(props.onOfferDraw).toHaveBeenCalled();
        expect(onBerserk).toHaveBeenCalled();
    });

    it('после окончания берсерка нет, кнопки сдачи и ничьи недоступны', () => {
        setup({onBerserk: vi.fn(), gameOverResult: '1-0'});
        expect(screen.queryByTestId('berserk-button')).toBeNull();
        expect(button(t('controls.resign'))).toBeDisabled();
        expect(button(t('controls.offerDraw'))).toBeDisabled();
    });

    it('после партии: реванш, «В лобби», разбор со state маршрута и ссылка на PGN', () => {
        const props = setup({gameOverResult: '1-0'});
        fireEvent.click(button(t('controls.rematch')));
        fireEvent.click(button(t('controls.toLobby')));
        expect(props.onOfferRematch).toHaveBeenCalled();
        expect(props.onResetSandbox).toHaveBeenCalled();
        fireEvent.click(button(t('common.gameReview')));
        expect(props.navigate).toHaveBeenCalledWith('/game/7', {state: {game: expect.objectContaining({
            game_id: 7, white_username: 'Аня', white_rating: 1500, black_rating: 1200, result: '1-0',
        })}});
        expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringMatching(/\/profile\/games\/7\/pgn$/));
    });

    it('соперник предложил реванш: принять и отклонить', () => {
        const props = setup({gameOverResult: '0-1', rematchStatus: 'offered_by_opponent'});
        fireEvent.click(button(t('controls.acceptRematch')));
        fireEvent.click(button(t('common.decline')));
        expect(props.onAcceptRematch).toHaveBeenCalled();
        expect(props.onDeclineRematch).toHaveBeenCalled();
    });

    it('ждём ответа и отказ блокируют повторное предложение', () => {
        setup({gameOverResult: '1/2-1/2', rematchStatus: 'offered_by_me'});
        expect(button(t('controls.waitingAnswer'))).toBeDisabled();
    });

    it('отказ от реванша показан на кнопке', () => {
        setup({gameOverResult: '1/2-1/2', rematchStatus: 'declined'});
        expect(button(t('controls.rematchDeclined'))).toBeDisabled();
    });

    it('у отменённой партии разбора и PGN нет', () => {
        setup({gameOverResult: '*'});
        expect(screen.queryByRole('button', {name: new RegExp(t('common.gameReview'))})).toBeNull();
        expect(screen.queryByRole('link')).toBeNull();
    });

    it('разбор без номера партии никуда не ведёт', () => {
        const props = setup({gameOverResult: '1-0', gameId: null});
        fireEvent.click(button(t('common.gameReview')));
        expect(props.navigate).not.toHaveBeenCalled();
    });
});

describe('GameControlsPanel: партия с ботом', () => {
    it('возврат хода, сдача и ничья', () => {
        const props = setup({mode: 'bot'});
        fireEvent.click(button(t('controls.undoMove')));
        fireEvent.click(button(t('controls.resign')));
        fireEvent.click(screen.getByTestId('bot-offer-draw'));
        expect(props.onUndoSandboxMove).toHaveBeenCalled();
        expect(props.onResign).toHaveBeenCalled();
        expect(props.onOfferDraw).toHaveBeenCalled();
    });

    it('партия лестницы: возврат хода закрыт; бот думает — возврат и ничья недоступны', () => {
        setup({mode: 'bot', undoLocked: true, isBotThinking: true});
        expect(button(t('controls.undoMove'))).toBeDisabled();
        expect(screen.getByTestId('bot-offer-draw')).toBeDisabled();
    });

    it('после партии: реванш и разбор сохранённой партии с запасным рейтингом чёрных', () => {
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

    it('партия турнира (hideRematch): после окончания ряд кнопок скрыт', () => {
        setup({mode: 'bot', gameOverResult: '1-0', hideRematch: true});
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.rematch'))})).toBeNull();
        expect(screen.queryByRole('button', {name: new RegExp(t('controls.undoMove'))})).toBeNull();
    });
});

describe('GameControlsPanel: свободная доска', () => {
    it('без ходов возврат и сброс недоступны, со своей позицией сброс доступен', () => {
        setup({mode: 'sandbox', historyLength: 0, hasCustomPosition: true});
        expect(button(t('controls.undoSandbox'))).toBeDisabled();
        expect(button(t('controls.resetBoard'))).toBeEnabled();
    });

    it('возврат хода и сброс вызывают обработчики', () => {
        const props = setup({mode: 'sandbox'});
        fireEvent.click(button(t('controls.undoSandbox')));
        fireEvent.click(button(t('controls.resetBoard')));
        expect(props.onUndoSandboxMove).toHaveBeenCalled();
        expect(props.onResetSandbox).toHaveBeenCalled();
    });

    it('позиция из FEN: ошибка показывается, успех очищает поле, пустой ввод игнорируется', () => {
        const onLoadFen = vi.fn()
            .mockReturnValueOnce('Неверная позиция')
            .mockReturnValueOnce(null);
        setup({mode: 'sandbox', onLoadFen});
        const input = screen.getByLabelText(t('controls.fenLabel'));
        const form = input.closest('form')!;
        fireEvent.submit(form);
        expect(onLoadFen).not.toHaveBeenCalled();
        expect(button(t('controls.setPosition'))).toBeDisabled();

        fireEvent.change(input, {target: {value: 'bad fen'}});
        fireEvent.submit(form);
        expect(screen.getByRole('alert')).toHaveTextContent('Неверная позиция');
        fireEvent.change(input, {target: {value: '8/8/8/8/8/8/8/K6k w - - 0 1'}});
        expect(screen.queryByRole('alert')).toBeNull();
        fireEvent.submit(form);
        expect(input).toHaveValue('');
        expect(onLoadFen).toHaveBeenCalledTimes(2);
    });
});
