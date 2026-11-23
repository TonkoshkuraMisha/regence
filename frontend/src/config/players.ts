// --- FILE: frontend/src/config/players.ts ---
// Player names sent by the server - in the player's language. For bots the server stores neutral names
// (src/api/bots.py): a historical bot - its id ("morphy"), the shared workshop opponent - "workshop_opponent",
// an archetype in the game archive - "archetype:<id>". Ordinary player names are shown as is.

import {hasMessage, t as translateNow, uiMessage} from '../i18n';
import type {I18n, MessageParam} from '../i18n';
import {ARCHETYPE_PREFIX} from './archetypes';
import {HISTORICAL_BOTS} from './champions';
import type {HistoricalBotId} from './champions';

export const WORKSHOP_OPPONENT_USERNAME = 'workshop_opponent';

function historicalBotId(username: string): HistoricalBotId | null {
    const id = username.toLowerCase().replace(/_bot$/, '');
    return id in HISTORICAL_BOTS ? (id as HistoricalBotId) : null;
}

/** Player name as a message: a bot or archetype label from the catalog, otherwise the name as is. */
export function playerNameMessage(username: string | null | undefined): MessageParam {
    if (!username) return '';
    const botId = historicalBotId(username);
    if (botId) return uiMessage(`bots.profiles.${botId}.playerLabel`);
    if (username === WORKSHOP_OPPONENT_USERNAME) return uiMessage('bots.workshopTitle');
    if (username.startsWith(ARCHETYPE_PREFIX)) {
        const key = `archetypes.${username.slice(ARCHETYPE_PREFIX.length)}.name`;
        if (hasMessage(key)) return uiMessage(key);
    }
    return username;
}

/** Player name for display in the current language of the component (t from useI18n) or of the application. */
export function displayPlayerName(username: string | null | undefined, t: I18n['t'] = translateNow): string {
    const message = playerNameMessage(username);
    if (typeof message !== 'object') return String(message);
    return 'text' in message ? message.text : t(message.key);
}

/** Ladder step opponent: a historical bot - by id, an archetype - by archetype id. */
export function ladderOpponentName(kind: 'historical' | 'archetype', id: string, t: I18n['t'] = translateNow): string {
    if (kind === 'historical') {
        const key = `bots.profiles.${id}.shortName`;
        return hasMessage(key) ? t(key) : id;
    }
    const key = `archetypes.${id}.name`;
    return hasMessage(key) ? t(key) : id;
}
