// --- FILE: frontend/src/config/__tests__/players.test.ts ---
// Neutral names from the server (bot ids, the shared workshop opponent, archetype keys) and bot lines (keys
// with parameters) are shown in the player's language; ordinary player names — as is.

import {describe, expect, it} from 'vitest';
import {makeI18n, renderUiMessage} from '../../i18n';
import {displayPlayerName, ladderOpponentName} from '../players';
import {botCommentMessage} from '../../components/chessboard/hooks/useBotGame';

const en = makeI18n('en').t;
const uk = makeI18n('uk').t;

describe('player names', () => {
    it('a historical bot — by id, including the service "_bot"', () => {
        expect(displayPlayerName('morphy', en)).toBe('Paul Morphy');
        expect(displayPlayerName('morphy', uk)).toBe('Пол Морфі');
        expect(displayPlayerName('philidor_bot', en)).toBe('F.-A. Philidor');
    });

    it('the shared workshop opponent and an archetype', () => {
        expect(displayPlayerName('workshop_opponent', en)).toBe('Workshop opponent');
        expect(displayPlayerName('archetype:rusher', en)).toBe('Rusher');
        expect(displayPlayerName('archetype:rusher', uk)).toBe('Квапко');
    });

    it('ordinary names and unknown keys — as is', () => {
        expect(displayPlayerName('Misha_K', en)).toBe('Misha_K');
        expect(displayPlayerName('archetype:unknown', en)).toBe('archetype:unknown');
        expect(displayPlayerName(null, en)).toBe('');
    });

    it('a ladder step opponent', () => {
        expect(ladderOpponentName('historical', 'paulsen', en)).toBe('Paulsen');
        expect(ladderOpponentName('archetype', 'quiet', uk)).toBe('Тихоня');
        expect(ladderOpponentName('archetype', 'quiet', en)).toBe('Quiet One');
    });
});

describe('bot lines', () => {
    it('a book move — a bot line with the archive game count', () => {
        const message = botCommentMessage({key: 'book.morphy', params: {games: 42}})!;
        expect(renderUiMessage(message, en)).toBe('A historical move of Paul Morphy (42 games in the archive).');
        expect(renderUiMessage(message, uk)).toBe('Історичний хід Пола Морфі (партій в архіві: 42).');
    });

    it('a signature style line', () => {
        const message = botCommentMessage({key: 'philidor.pawnCenter', params: {}})!;
        expect(renderUiMessage(message, en)).toBe('Pawns are the soul of chess! A powerful thrust into the center.');
        expect(renderUiMessage(message, uk)).toBe('Пішаки — душа шахів! Потужний удар у центр дошки.');
    });

    it('an unknown key, the old text format and junk — no line', () => {
        expect(botCommentMessage({key: 'nobody.knows', params: {}})).toBeNull();
        expect(botCommentMessage('Old text')).toBeNull();
        expect(botCommentMessage(null)).toBeNull();
        expect(botCommentMessage({key: 5})).toBeNull();
    });

    it('parameters — only simple values', () => {
        expect(botCommentMessage({key: 'book.paulsen', params: {games: 3, junk: {deep: 1}}}))
            .toEqual({key: 'botComments.book.paulsen', params: {games: 3}});
    });
});
