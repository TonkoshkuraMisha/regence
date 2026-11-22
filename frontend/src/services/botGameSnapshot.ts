// --- FILE: frontend/src/services/botGameSnapshot.ts ---
// Снимок идущей партии с ботом в localStorage: партия с ботом живёт только в браузере, и без снимка перезагрузка
// страницы (или переход на другую страницу и возврат) теряла позицию, а в турнире повторный старт засчитывал поражение
// (сервер: start_player_game, таск A.2). Снимок хранит всё, чтобы продолжить: PGN (с позицией «со своей расстановки» и
// форой), цвет игрока, соперника, часы, добавку, признаки лестницы и турнира. Пишет Chessboard.tsx при каждом ходе и
// при закрытии страницы, читает и применяет он же при открытии; стирается с концом партии и выходом из неё.
// Правила: снимок один (партия с ботом на доске одна), принадлежит игроку (чужой аккаунт его не видит), живёт
// SNAPSHOT_TTL_MS; часы того, чей ход, при продолжении уменьшаются на время, прошедшее с записи (перезагрузка не
// останавливает часы). Единственное хранилище — localStorage с ключом regence_bot_game.

import type {CustomOpponent} from '../config/archetypes';

// Ключ localStorage со снимком.
const STORAGE_KEY = 'regence_bot_game';
// Версия формата: снимок другой версии игнорируется (не пытаемся читать чужую структуру).
const SNAPSHOT_VERSION = 1;
// Сколько снимок считается живым (мс): сутки — партия с ботом дольше не идёт, дальше это забытая партия.
export const SNAPSHOT_TTL_MS = 24 * 60 * 60 * 1000;

/** Фора партии: вид и кто её даёт (как в chessboard/odds.ts); строки — чтобы не зависеть от модуля доски. */
export interface SnapshotOdds {
    kind: string;
    giver: string;
}

export interface BotGameSnapshot {
    version: number;
    /** Когда записан (мс с эпохи) — от него отсчитывается время, ушедшее на перезагрузку. */
    savedAt: number;
    /** Имя игрока: чужой аккаунт снимок не получает. */
    username: string;
    /** id исторического бота или «custom» (тогда соперник — в custom). */
    botId: string;
    custom: CustomOpponent | null;
    color: 'white' | 'black';
    /** Партия целиком в PGN: с заголовками FEN и SetUp, если начата не с обычной расстановки. */
    pgn: string;
    whiteTimeMs: number;
    blackTimeMs: number;
    /** Базовое время (минуты) и добавка (секунды) партии — для часов после продолжения. */
    baseMinutes: number;
    incrementSeconds: number;
    odds: SnapshotOdds | null;
    ladder: boolean;
    /** Партия турнира: номер партии расписания и турнира — иначе null. */
    tournamentGameId: number | null;
    tournamentId: number | null;
    /** Партия стояла на паузе: часы при продолжении не уменьшаются на время перезагрузки (снимки без поля — не на паузе). */
    paused?: boolean;
}

/** Сохраняет снимок; хранилище недоступно — молча (продолжение партии — удобство, не гарантия). */
export function saveBotGameSnapshot(snapshot: Omit<BotGameSnapshot, 'version' | 'savedAt'>, now: number = Date.now()): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({...snapshot, version: SNAPSHOT_VERSION, savedAt: now}));
    } catch {
        // Переполнено или запрещено — без снимка партия просто не переживёт перезагрузку.
    }
}

/** Стирает снимок (партия окончена, оставлена или результат уже записан). */
export function clearBotGameSnapshot(): void {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // Нечего делать.
    }
}

/** Годится ли разобранное значение как снимок текущей версии: поля нужных типов, часы и PGN на месте. */
function isSnapshot(value: unknown): value is BotGameSnapshot {
    if (!value || typeof value !== 'object') return false;
    const s = value as Record<string, unknown>;
    return s.version === SNAPSHOT_VERSION
        && typeof s.savedAt === 'number' && typeof s.username === 'string' && typeof s.botId === 'string'
        && (s.color === 'white' || s.color === 'black') && typeof s.pgn === 'string'
        && typeof s.whiteTimeMs === 'number' && typeof s.blackTimeMs === 'number'
        && typeof s.baseMinutes === 'number' && typeof s.incrementSeconds === 'number'
        && typeof s.ladder === 'boolean'
        && (s.tournamentGameId === null || typeof s.tournamentGameId === 'number')
        && (s.tournamentId === null || typeof s.tournamentId === 'number');
}

/**
 * Снимок для этого игрока, если он есть, свежий и целый; иначе null (и испорченный или просроченный стирается).
 * username — текущий игрок: снимок другого аккаунта не отдаётся и не стирается (он ещё нужен владельцу).
 */
export function loadBotGameSnapshot(username: string, now: number = Date.now()): BotGameSnapshot | null {
    let raw: string | null;
    try {
        raw = localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
    if (raw === null) return null;
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        parsed = null;
    }
    if (!isSnapshot(parsed) || now - parsed.savedAt > SNAPSHOT_TTL_MS || parsed.savedAt > now + SNAPSHOT_TTL_MS) {
        clearBotGameSnapshot();
        return null;
    }
    return parsed.username === username ? parsed : null;
}

/**
 * Часы после продолжения: у стороны, чей ход, вычитается время, прошедшее с записи снимка (перезагрузка часы не
 * останавливает, но партия на паузе их не уменьшает); не меньше нуля — упавший флаг обработает обычная проверка времени.
 */
export function clocksAfterGap(
    snapshot: Pick<BotGameSnapshot, 'whiteTimeMs' | 'blackTimeMs' | 'savedAt'> & { paused?: boolean }, whiteToMove: boolean, now: number = Date.now(),
): { white: number; black: number } {
    const gap = snapshot.paused ? 0 : Math.max(0, now - snapshot.savedAt);
    return {
        white: whiteToMove ? Math.max(0, snapshot.whiteTimeMs - gap) : snapshot.whiteTimeMs,
        black: whiteToMove ? snapshot.blackTimeMs : Math.max(0, snapshot.blackTimeMs - gap),
    };
}
