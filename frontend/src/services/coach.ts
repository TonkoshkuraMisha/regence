// --- FILE: frontend/src/services/coach.ts ---
// Mentor commentary (src/services/coach.py): the server sends sentences as coach catalog keys and
// parameters (pieces in figurine notation, «♘f7»), arrows and square highlights. The text is in the player's language.

import {hasMessage, renderUiMessage, uiMessage} from '../i18n';
import type {I18n, UiMessage} from '../i18n';

/** Arrow kind: best move, opponent's threat, idea (plan). The kind determines the arrow color on the board. */
export type CoachArrowKind = 'best' | 'threat' | 'idea';

/** Arrow on the board: «from» and «to» squares written like «e2», «e4». */
export interface CoachArrow {
    from: string;
    to: string;
    kind: CoachArrowKind;
}

/** Highlighted square. The client does not distinguish the kind (the server sends target and piece): coachHighlights takes only the squares. */
export interface CoachHighlight {
    square: string;
    kind: string;
}

/** Mentor commentary in the server response: the coach field of a game-analysis move and of the move-check response. */
export interface CoachComment {
    /** Sentences in order: a coach.* catalog key and template parameters. */
    comment: { key: string; params?: Record<string, string | number> }[];
    arrows?: CoachArrow[];
    highlights?: CoachHighlight[];
}

const SQUARE = /^[a-h][1-8]$/;
const ARROW_KINDS: ReadonlySet<string> = new Set(['best', 'threat', 'idea']);

/** Commentary sentences; unfamiliar keys (the server is newer than the client) are skipped. */
export function coachSentences(coach: CoachComment | null | undefined): UiMessage[] {
    if (!coach || !Array.isArray(coach.comment)) return [];
    const sentences: UiMessage[] = [];
    for (const sentence of coach.comment) {
        if (!sentence || typeof sentence.key !== 'string' || !hasMessage(sentence.key)) continue;
        const params: Record<string, string | number> = {};
        for (const [name, value] of Object.entries(sentence.params ?? {})) {
            if (typeof value === 'string' || typeof value === 'number') params[name] = value;
        }
        sentences.push(uiMessage(sentence.key, params));
    }
    return sentences;
}

/** The whole commentary text: sentences separated by a space. */
export function coachText(coach: CoachComment | null | undefined, t: I18n['t']): string {
    return coachSentences(coach).map((sentence) => renderUiMessage(sentence, t)).join(' ');
}

/** Commentary arrows, only valid ones (board squares and a known kind). */
export function coachArrows(coach: CoachComment | null | undefined): CoachArrow[] {
    return (coach?.arrows ?? []).filter(
        (arrow) => SQUARE.test(arrow.from) && SQUARE.test(arrow.to) && ARROW_KINDS.has(arrow.kind),
    );
}

/** Squares the commentary asks to highlight (only valid board squares). */
export function coachHighlights(coach: CoachComment | null | undefined): Set<string> {
    return new Set((coach?.highlights ?? []).map((h) => h.square).filter((square) => SQUARE.test(square)));
}
