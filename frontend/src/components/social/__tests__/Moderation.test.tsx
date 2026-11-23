// Moderation (task 17.4): a report from a profile, a report on a chat message, the moderator queue, an appeal.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {ModerationPage, ReportButton} from '../ModerationPage';
import {GameChatPanel} from '../../chessboard/GameChatPanel';

function stub(handler: (url: string, init?: RequestInit) => unknown) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => ({ok: true, status: 200, json: async () => handler(String(url), init)} as Response));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const posts = (fetchMock: ReturnType<typeof stub>) =>
    (fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([, init]) => init?.method === 'POST');

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
});

const SUMMARY = {
    days: 30, opened: 7, resolved: 4, open_now: 3, oldest_open_hours: 52, cheaters: 2,
    by_kind: {player: 5, cheat_review: 2}, by_action: {warn: 3, dismiss: 1}, top_targets: [{username: 'troll', reports: 4}],
};

describe('moderation', () => {
    it('a report on a player from the profile', async () => {
        const fetchMock = stub(() => ({id: 1}));
        render(<ReportButton username="troll"/>);
        fireEvent.click(screen.getByTestId('report-open'));
        fireEvent.change(screen.getByTestId('report-reason'), {target: {value: 'cheating'}});
        await act(async () => fireEvent.submit(screen.getByTestId('report-form')));
        expect(JSON.parse(String(posts(fetchMock)[0][1].body))).toMatchObject({target: 'troll', kind: 'player', reason: 'cheating'});
        expect(screen.getByTestId('report-sent')).toBeInTheDocument();
    });

    it('a report on an opponent\'s message in the game chat — with a copy of the text; there is no button for one\'s own messages', async () => {
        const fetchMock = stub(() => ({id: 2}));
        render(<GameChatPanel messages={[{sender: 'troll', text: 'you are weak', timestamp: 1}, {sender: 'me', text: 'calm down', timestamp: 2}]} chatInput=""
                              onChatInputChange={vi.fn()} onSendMessage={vi.fn()} onSendPreset={vi.fn()} isSpectator={false}
                              onLeaveSpectate={vi.fn()} myName="me" gameId={77}/>);
        expect(screen.queryByTestId('report-message-1')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('report-message-0')));
        expect(JSON.parse(String(posts(fetchMock)[0][1].body))).toEqual({
            target: 'troll', kind: 'message', reason: 'abuse', message_text: 'you are weak', game_id: 77,
        });
        expect(screen.getByText('Report sent')).toBeInTheDocument();
    });

    it('the moderator queue and the decision', async () => {
        const item = {id: 5, kind: 'message', reason: 'abuse', comment: null, message_text: 'you are weak', game_id: 77, created_at: null,
            reporter: 'me', target: 'troll', target_is_cheater: false, target_trust: 100, reports_on_target: 3};
        const fetchMock = stub((url) => (url.endsWith('/me') ? {is_moderator: true, is_cheater: false, open_appeal: false, chat_banned_until: null}
            : url.endsWith('/queue') ? {reports: [item]} : url.endsWith('/summary') ? SUMMARY : {id: 5, action: 'chat_ban'}));
        render(<MemoryRouter><ModerationPage/></MemoryRouter>);
        expect(await screen.findByTestId('mod-item-5')).toHaveTextContent('you are weak');
        expect(screen.getByTestId('mod-item-5')).toHaveTextContent('reports on the player: 3');
        expect(screen.queryByTestId('act-5-mark_cheater')).toBeNull();   // for a message — no cheating flag
        await act(async () => fireEvent.click(screen.getByTestId('act-5-chat_ban')));
        expect(posts(fetchMock)[0][0]).toContain('/reports/5/resolve');
    });

    it('violations summary: totals, breakdown by kind and decision, the most frequent reports', async () => {
        stub((url) => (url.endsWith('/me') ? {is_moderator: true, is_cheater: false, open_appeal: false, chat_banned_until: null}
            : url.endsWith('/queue') ? {reports: []} : SUMMARY));
        render(<MemoryRouter><ModerationPage/></MemoryRouter>);
        expect(await screen.findByTestId('summary-totals')).toHaveTextContent('Reports received: 7, resolved: 4, open now: 3');
        expect(screen.getByTestId('violations-summary')).toHaveTextContent('Oldest open report: 52 h');
        expect(screen.getByTestId('summary-kinds')).toHaveTextContent('Player report: 5');
        expect(screen.getByTestId('summary-actions')).toHaveTextContent('Warn: 3');
        expect(screen.getByTestId('summary-top')).toHaveTextContent('troll (4)');
    });

    it('an appeal for a flagged player', async () => {
        const fetchMock = stub((url) => (url.endsWith('/me') ? {is_moderator: false, is_cheater: true, open_appeal: false, chat_banned_until: null} : {id: 9}));
        render(<MemoryRouter><ModerationPage/></MemoryRouter>);
        fireEvent.change(await screen.findByTestId('appeal-text'), {target: {value: 'played myself'}});
        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'File an appeal'})));
        expect(JSON.parse(String(posts(fetchMock)[0][1].body))).toEqual({comment: 'played myself'});
    });
});
