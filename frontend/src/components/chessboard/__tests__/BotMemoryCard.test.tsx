// Bot memory on the card (tasks 32.1–32.2): strength against players and "remembers you" with a score.

import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it, vi} from 'vitest';
import {HISTORICAL_BOTS} from '../../../config/champions';
import {scorePoints} from '../../../services/botCatalog';
import {HistoricalBotsPanel} from '../HistoricalBotsPanel';

function panel(extra: Partial<Parameters<typeof HistoricalBotsPanel>[0]> = {}) {
    return render(
        <MemoryRouter>
            <HistoricalBotsPanel selectedBotId="morphy" onSelectBot={vi.fn()} selectedBotProfile={HISTORICAL_BOTS.morphy}
                                 activeBot={null} activeBotProfile={null} gameId={null} gameOverResult={null}
                                 isBotThinking={false} botComment={null} onStartBotGame={vi.fn()}
                                 canStartFromPosition={false} startFromPosition={false} onStartFromPositionChange={vi.fn()}
                                 {...extra}/>
        </MemoryRouter>,
    );
}

describe('bot memory on the card', () => {
    it('a score with halves', () => {
        expect([scorePoints(0), scorePoints(0.5), scorePoints(2.5), scorePoints(3)]).toEqual(['0', '½', '2½', '3']);
    });

    it('a regular opponent: the bot remembers and avoids lost lines', () => {
        panel({
            live: {morphy: {rating: 1980, games: 64}},
            rivals: {morphy: {bot_id: 'morphy', games: 3, bot_points: 0.5, remembers: true}},
        });
        expect(screen.getByTestId('bot-live-strength')).toHaveTextContent('Against players: 1980 (games: 64)');
        const rivalry = screen.getByTestId('bot-rivalry');
        expect(rivalry).toHaveTextContent('remembers you: games 3, score 2½ : ½');
        expect(rivalry).toHaveTextContent('avoids the lines');
    });

    it('one game — just an acquaintance; no games — no line', () => {
        const {unmount} = panel({rivals: {morphy: {bot_id: 'morphy', games: 1, bot_points: 1, remembers: false}}});
        expect(screen.getByTestId('bot-rivalry')).toHaveTextContent('You have played');
        unmount();
        panel();
        expect(screen.queryByTestId('bot-rivalry')).toBeNull();
        expect(screen.queryByTestId('bot-live-strength')).toBeNull();
    });
});
