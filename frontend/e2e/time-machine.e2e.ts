// The "Time machine" and the catalogue of past masters in a real browser against the full stack (tasks 28.3 and 28.5).
// A player's game with a past master is saved under his name from the PGN ("Keres, Paul"): until 17.11 the server rejected such a name
// (400 username_invalid_chars), the result was not recorded, and a historical tournament could not be finished.
// Unit tests set results through the service directly and did not see this — here the browser goes the whole way.

import {expect, test} from '@playwright/test';
import type {APIRequestContext, Page} from '@playwright/test';
import {API, loginNewPlayer} from './helpers.ts';

interface PlayerRow { seat: number; kind: string; bot_key: string | null; personality_name: string | null }
interface GameRow { id: number; round: number; white_seat: number; black_seat: number; result: string | null; game_id: number | null }
interface TournamentState {
    id: number; status: string; event_key: string | null; my_seat: number; current_round: number;
    players: PlayerRow[]; games: GameRow[];
}

/** The player is shared by the run: resign the tournaments left from the previous attempt to enter a new one. */
async function withdrawActiveTournaments(request: APIRequestContext, token: string) {
    const headers = {Authorization: `Bearer ${token}`};
    const list = await (await request.get(`${API}/api/v1/tournaments`, {headers})).json() as { id: number; status: string }[];
    for (const t of list.filter((item) => item.status === 'active')) {
        await request.post(`${API}/api/v1/tournaments/${t.id}/withdraw`, {headers});
    }
}

async function resign(page: Page) {
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', {name: /Resign/}).click();
}

test('time machine: a game with a past master is recorded in the historical tournament', async ({page, request}) => {
    test.setTimeout(240_000);
    const token = await loginNewPlayer(page, request, 'tm');
    const headers = {Authorization: `Bearer ${token}`};
    await withdrawActiveTournaments(request, token);

    await page.goto('/time-machine');
    await page.getByTestId('start-avro_1938').click();
    await expect(page.getByTestId('tournament-view')).toBeVisible();
    const tournamentId = Number(new URL(page.url()).pathname.split('/').pop());
    expect(tournamentId).toBeGreaterThan(0);

    const state = async () =>
        await (await request.get(`${API}/api/v1/tournaments/${tournamentId}`, {headers})).json() as TournamentState;
    const before = await state();
    expect(before.event_key).toBe('avro_1938');
    const mine = before.games.find((g) => g.round === before.current_round && g.result === null
        && [g.white_seat, g.black_seat].includes(before.my_seat));
    expect(mine, 'the player has a game in the first round').toBeTruthy();
    const opponentSeat = mine!.white_seat === before.my_seat ? mine!.black_seat : mine!.white_seat;
    const opponent = before.players.find((p) => p.seat === opponentSeat)!;
    // The newcomer's first opponent is from the upper part of the seeding: in the seeding that is a past master, not a historical bot.
    expect(opponent.kind).toBe('personality');
    expect(opponent.bot_key).toMatch(/^guest:/);
    expect(opponent.personality_name).toContain(', ');

    await page.getByRole('button', {name: 'Play my game'}).click();
    await expect(page.getByTestId('tournament-bar')).toBeVisible();
    // On the board — the master's name in the player's language, not the Latin name from the PGN.
    await expect(page.getByText(/Keres|Fine|Reshevsky|Euwe|Flohr/).first()).toBeVisible();
    await resign(page);
    await expect(page.getByText(/The result is recorded in the tournament/)).toBeVisible();
    // After the game: the way back to the tournament and the card of the opponent — the past master.
    await expect(page.getByTestId('back-to-tournament')).toBeVisible();
    await expect(page.getByTestId('tournament-bar-opponent-card')).toHaveAttribute('href', /\/masters\?master=/);

    // The server accepted the game: it has a result and an archive record.
    await expect.poll(async () => (await state()).games.find((g) => g.id === mine!.id)?.result ?? null, {timeout: 20_000})
        .not.toBeNull();
    const recorded = (await state()).games.find((g) => g.id === mine!.id)!;
    expect(recorded.game_id).not.toBeNull();
    const pgn = await request.get(`${API}/api/v1/profile/games/${recorded.game_id}/pgn`, {headers});
    expect(pgn.ok()).toBe(true);
    expect(await pgn.text()).toContain(opponent.personality_name!);

    await request.post(`${API}/api/v1/tournaments/${tournamentId}/withdraw`, {headers});
});

test('master catalogue: a separate game with a past master goes to the archive under his name', async ({page, request}) => {
    test.setTimeout(180_000);
    const token = await loginNewPlayer(page, request, 'masters');
    const headers = {Authorization: `Bearer ${token}`};
    const me = await (await request.get(`${API}/api/v1/profile/me`, {headers})).json() as { username: string };

    await page.goto('/masters');
    await expect(page.getByTestId('master-keres')).toBeVisible();
    await page.getByTestId('masters-search').fill('Kieseritzky');
    await expect(page.locator('li[data-testid^="master-"]')).toHaveCount(1);
    await page.getByTestId('play-kieseritzky-white').click();

    // The board: the opponent is Kieseritzky, the player is White. The move e2–e4, the master replies (the engine on the server).
    await expect(page.getByText(/Kieseritzky/).first()).toBeVisible();
    const square = (name: string) => page.locator(`[data-square="${name}"]`).first();
    await square('e2').click();
    await square('e4').click();
    await expect.poll(async () => page.locator('[data-square="e4"] img').count(), {timeout: 10_000}).toBe(1);
    // Black's reply: there are fewer than eight pawns on the seventh rank, or a piece has left the eighth.
    await expect.poll(async () => await page.evaluate(`Array.from(document.querySelectorAll('[data-square]'))
        .filter((cell) => /[78]$/.test(cell.getAttribute('data-square') ?? '') && cell.querySelector('img')).length`),
        {timeout: 30_000}).toBeLessThan(16);
    await resign(page);

    // In the player's archive the last game is with the master — under the name from the PGN.
    await expect.poll(async () => {
        const games = await (await request.get(`${API}/api/v1/profile/${encodeURIComponent(me.username)}/games`, {headers})).json();
        const list = (Array.isArray(games) ? games : games.items ?? []) as { white_username: string; black_username: string }[];
        return list.length > 0 ? list[0].black_username : null;
    }, {timeout: 20_000}).toBe('Kieseritzky, Lionel');
});
