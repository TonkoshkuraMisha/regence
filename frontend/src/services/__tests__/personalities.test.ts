// The opponent workshop: guest personalities in localStorage and moving them to the profile after login.

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
    DEFAULT_CONFIG,
    GUEST_STORAGE_KEY,
    MAX_PERSONALITIES,
    createPersonality,
    deleteGuestPersonality,
    importGuestPersonalities,
    offerGuestPersonalityTransfer,
    readGuestPersonalities,
    saveGuestPersonality,
} from '../personalities';
import {UiError} from '../apiErrors';

const draft = (name: string, aggression = 0) => ({name, config: {...DEFAULT_CONFIG, aggression}});

function mockFetch(status: number, body: unknown) {
    const fetchMock = vi.fn(async () => ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
    }) as Response);
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

/** The message from a UiError thrown by a function (guest errors are the same codes as the server's). */
function thrownUi(fn: () => unknown) {
    try {
        fn();
    } catch (err) {
        if (err instanceof UiError) return err.ui;
        throw err;
    }
    throw new Error('nothing was thrown');
}

describe('guest personalities', () => {
    it('are saved, updated and deleted in localStorage', () => {
        const created = saveGuestPersonality(draft('Gambiteer', 80));
        expect(readGuestPersonalities()).toHaveLength(1);

        saveGuestPersonality(draft('Gambiteer', -40), created.id as string);
        expect(readGuestPersonalities()[0].config.aggression).toBe(-40);

        deleteGuestPersonality(created.id as string);
        expect(readGuestPersonalities()).toEqual([]);
        expect(localStorage.getItem(GUEST_STORAGE_KEY)).toBeNull();
    });

    it('the name is unique case-insensitively, and the limit applies', () => {
        saveGuestPersonality(draft('Tactician'));
        expect(thrownUi(() => saveGuestPersonality(draft('TACTICIAN'))))
            .toEqual({key: 'serverErrors.personality_duplicate'});

        for (let i = 1; i < MAX_PERSONALITIES; i++) saveGuestPersonality(draft(`Bot_${i}`));
        expect(thrownUi(() => saveGuestPersonality(draft('Overflow'))))
            .toEqual({key: 'serverErrors.personality_limit', params: {max: 20}});
    });

    it('corrupted storage does not crash the page', () => {
        localStorage.setItem(GUEST_STORAGE_KEY, '{not json');
        expect(readGuestPersonalities()).toEqual([]);
    });
});

describe('moving to the profile', () => {
    it('the moved ones are removed from the browser, the skipped ones stay', async () => {
        saveGuestPersonality(draft('Fresh'));
        saveGuestPersonality(draft('Existing'));
        const fetchMock = mockFetch(200, {
            created: [{id: 7, name: 'Fresh', config: DEFAULT_CONFIG, created_at: '', updated_at: ''}],
            skipped: [{name: 'Existing', reason: 'personality_duplicate', params: {}}],
        });

        const result = await importGuestPersonalities('jwt');

        expect(result.skipped[0].name).toBe('Existing');
        expect(readGuestPersonalities().map((p) => p.name)).toEqual(['Existing']);
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toMatch(/\/api\/v1\/bots\/personalities\/import$/);
        expect((init.headers as Record<string, string>).Authorization).toBe('Bearer jwt');
        expect(JSON.parse(init.body as string).items).toHaveLength(2);
    });

    it('without guest personalities it asks nothing and sends nothing', async () => {
        const fetchMock = mockFetch(200, {});
        const confirm = vi.fn(() => true);
        expect(await offerGuestPersonalityTransfer('jwt', confirm)).toBeNull();
        expect(confirm).not.toHaveBeenCalled();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('the player\'s refusal leaves the personalities in the browser', async () => {
        saveGuestPersonality(draft('Keep'));
        const fetchMock = mockFetch(200, {});
        expect(await offerGuestPersonalityTransfer('jwt', () => false)).toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
        expect(readGuestPersonalities()).toHaveLength(1);
    });

    it('a server error shows its text and loses nothing', async () => {
        saveGuestPersonality(draft('Keep'));
        mockFetch(409, {detail: 'No more than 20 opponents in the workshop — delete the extras'});
        await expect(importGuestPersonalities('jwt')).rejects.toThrow(/No more than 20/);
        expect(readGuestPersonalities()).toHaveLength(1);
    });
});

describe('server', () => {
    it('creating sends the name and the config with a token', async () => {
        const fetchMock = mockFetch(201, {id: 1, ...draft('Gambiteer'), created_at: '', updated_at: ''});
        const saved = await createPersonality('jwt', draft('Gambiteer', 60));
        expect(saved.id).toBe(1);
        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(init.method).toBe('POST');
        expect(JSON.parse(init.body as string).config.aggression).toBe(60);
    });
});
