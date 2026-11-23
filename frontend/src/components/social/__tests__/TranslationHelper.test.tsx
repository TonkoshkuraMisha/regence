// "Translation helper" mode (task 17.7): press the button, then an interface text → a suggestion with the key goes to moderation.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {setTranslationHelper} from '../../../services/profileSettings';
import {TranslationHelper} from '../TranslationHelper';

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    act(() => setTranslationHelper(false));
    vi.unstubAllGlobals();
});

function page(text: string) {
    return render(
        <MemoryRouter initialEntries={['/puzzles']}>
            <p data-testid="text">{text}</p>
            <TranslationHelper/>
        </MemoryRouter>,
    );
}

describe('translation helper', () => {
    it('off — there is no button', () => {
        page('Report sent');
        expect(screen.queryByTestId('translation-pick')).toBeNull();
    });

    it('pressing a text finds the key and sends a suggestion with the language and the page', async () => {
        const fetchMock = vi.fn(async () => ({ok: true, status: 201, json: async () => ({id: 1})} as Response));
        vi.stubGlobal('fetch', fetchMock);
        act(() => setTranslationHelper(true));
        page('Report sent');
        fireEvent.click(screen.getByTestId('translation-pick'));
        fireEvent.click(screen.getByTestId('text'));
        expect(screen.getByTestId('translation-key')).toHaveValue('moderation.reportSent');
        fireEvent.change(screen.getByTestId('translation-suggestion'), {target: {value: 'Report received'}});
        await act(async () => fireEvent.submit(screen.getByTestId('translation-form')));
        const [url, init] = (fetchMock.mock.calls as unknown as [string, RequestInit][])[0];
        expect(url).toContain('/moderation/translations');
        expect(JSON.parse(String(init.body))).toEqual({
            language: 'en', key: 'moderation.reportSent', current: 'Report sent', suggestion: 'Report received', context: '/puzzles',
        });
        expect(screen.getByTestId('translation-sent')).toBeInTheDocument();
    });

    it('a text not from the catalog — honestly says so', () => {
        act(() => setTranslationHelper(true));
        page('magnus_1990');
        fireEvent.click(screen.getByTestId('translation-pick'));
        fireEvent.click(screen.getByTestId('text'));
        expect(screen.getByTestId('translation-not-found')).toBeInTheDocument();
    });
});
