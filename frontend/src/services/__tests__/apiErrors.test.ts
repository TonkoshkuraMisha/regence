// --- FILE: frontend/src/services/__tests__/apiErrors.test.ts ---
// Server errors in the player's language: code → the serverErrors catalog, field validation errors (422) → the
// validation catalog with the field name, an unknown code → the server's English text, service exceptions → UiError.

import {describe, expect, it} from 'vitest';
import {makeI18n, renderUiMessage, type Language} from '../../i18n';
import {
    UiError,
    apiErrorMessage,
    errorMessage,
    readApiError,
    readApiErrorOr,
    serverErrorMessage,
} from '../apiErrors';

const render = (detail: unknown, language: Language = 'en') => {
    const message = apiErrorMessage(detail);
    return message ? renderUiMessage(message, makeI18n(language).t) : null;
};

const jsonResponse = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});

describe('a server error with a code', () => {
    const detail = {
        code: 'rating_out_of_range',
        params: {rating: 1500, min: 1600, max: 1800},
        message: 'Your rating 1500 is outside the challenge range (1600–1800)',
    };

    it('the text is taken from the catalog in the player\'s language, with parameters', () => {
        expect(render(detail, 'uk')).toBe('Ваш рейтинг 1500 поза діапазоном виклику (1600–1800)');
        expect(render(detail, 'en')).toBe('Your rating 1500 is outside the challenge range (1600–1800)');
    });

    it('an unknown code — the server\'s English text', () => {
        expect(render({code: 'brand_new_code', params: {}, message: 'Something new'})).toBe('Something new');
    });

    it('without a code and text — nothing (the fallback message will show)', () => {
        expect(apiErrorMessage({code: 'brand_new_code'})).toBeNull();
        expect(apiErrorMessage(undefined)).toBeNull();
        expect(apiErrorMessage([])).toBeNull();
    });

    it('a standard FastAPI error without a code is shown as is', () => {
        expect(render('Not Found')).toBe('Not Found');
    });

    it('parameters — only simple values', () => {
        const message = serverErrorMessage('user_not_found', {username: 'alice', extra: {nested: 1}});
        expect(message).toEqual({key: 'serverErrors.user_not_found', params: {username: 'alice'}});
    });
});

describe('field validation errors (422)', () => {
    it('the server\'s own validation — by code and with the field name', () => {
        const detail = [{type: 'username_mixed_scripts', loc: ['body', 'username'], msg: '…', params: {}}];
        expect(render(detail, 'en')).toBe('Username: A name cannot mix Latin and Cyrillic letters');
    });

    it('standard validation — by type from the validation catalog', () => {
        const detail = [{type: 'string_too_short', loc: ['body', 'password'], msg: 'String should…', params: {min_length: 8}}];
        expect(render(detail, 'en')).toBe('Password: at least 8 characters');
        expect(render(detail, 'uk')).toBe('Пароль: щонайменше 8 символів');
    });

    it('an unknown field — by name, an unknown validation — "invalid value"', () => {
        const detail = [{type: 'some_pydantic_type', loc: ['body', 'weird_field'], msg: 'Weird', params: {}}];
        expect(render(detail, 'en')).toBe('weird_field: invalid value');
    });

    it('whole-model validation — without a field name', () => {
        const detail = [{type: 'config_or_personality', loc: ['body'], msg: '…', params: {}}];
        expect(render(detail, 'en')).toBe('Specify either the opponent’s settings or a saved opponent, not both');
    });
});

describe('reading a response', () => {
    it('readApiError parses the response body', async () => {
        const message = await readApiError(jsonResponse(404, {detail: {code: 'game_not_found', params: {game_id: 7}, message: '…'}}));
        expect(message).toEqual({key: 'serverErrors.game_not_found', params: {game_id: 7}});
    });

    it('the body is not JSON — the fallback message', async () => {
        expect(await readApiError(new Response('<html>502</html>', {status: 502}))).toBeNull();
        expect(await readApiErrorOr(new Response('', {status: 500}), 'viewer.analysisFailed'))
            .toEqual({key: 'viewer.analysisFailed'});
    });
});

describe('exceptions', () => {
    it('UiError carries a message, the rest — the fallback', () => {
        const ui = {key: 'serverErrors.personality_duplicate' as const};
        expect(errorMessage(new UiError(ui), 'workshop.saveFailed')).toBe(ui);
        expect(errorMessage(new TypeError('Failed to fetch'), 'workshop.saveFailed')).toEqual({key: 'workshop.saveFailed'});
    });
});
