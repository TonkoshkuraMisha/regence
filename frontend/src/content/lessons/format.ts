// --- FILE: frontend/src/content/lessons/format.ts ---
// School lesson format (task 14.1). A lesson is a JSON file in this folder: texts in several languages, positions and moves.
// Content check is validateLesson (run by the CI test: all moves are legal, every question has a correct
// answer, texts in all languages); answers to chess questions are verified by the engine in an offline script
// scripts/verify_lessons.py.
//
// Lesson steps:
//  * text      - position and explanation; arrows, square highlights, a "ghost" piece;
//  * demo      - showcase: a sequence of board actions (sliding move, arrow, highlight, piece appearance,
//                "ghost", pause), synchronised with the text;
//  * find_move - "find the move": correct answers, a dedicated reply to each expected wrong move, the computer's reply and
//                "play the continuation" (a line of several player moves);
//  * choice    - a multiple-choice question with a reply for each option.
// After the steps comes an exam: 1-5 control questions (find_move or choice); a first-attempt correct answer counts.

import type {Language} from '../../i18n';

export type LocalizedText = Record<Language, string>;

export type ArrowColor = 'green' | 'red' | 'blue' | 'yellow';

export interface Arrow {
    from: string;
    to: string;
    color?: ArrowColor;
}

/** Piece in colour + type format: "wN", "bq"... (type case does not matter). */
export type PieceCode = string;

export interface Ghost {
    square: string;
    piece: PieceCode;
}

export type DemoAction =
    | { do: 'move'; uci: string }
    | { do: 'arrow'; from: string; to: string; color?: ArrowColor }
    | { do: 'highlight'; squares: string[] }
    | { do: 'ghost'; square: string; piece: PieceCode }
    | { do: 'place'; square: string; piece: PieceCode }
    | { do: 'clear' }
    | { do: 'pause'; ms: number };

interface BoardDecor {
    arrows?: Arrow[];
    highlights?: string[];
    ghost?: Ghost;
    orientation?: 'white' | 'black';
}

export interface TextStep extends BoardDecor {
    type: 'text';
    fen: string;
    text: LocalizedText;
}

export interface DemoStep extends BoardDecor {
    type: 'demo';
    fen: string;
    text: LocalizedText;
    actions: DemoAction[];
}

/** One player move in a question line: correct answers, replies to wrong ones, the computer's reply. */
export interface MoveTask {
    answers: string[];
    /** Computer move after a correct answer (uci). */
    reply?: string;
    /** Dedicated reply to an expected wrong move (uci -> text). */
    wrong?: Record<string, LocalizedText>;
    /** Reply to a correct move. */
    correct?: LocalizedText;
}

export interface FindMoveStep extends BoardDecor {
    type: 'find_move';
    fen: string;
    text: LocalizedText;
    hint?: LocalizedText;
    line: MoveTask[];
}

export interface ChoiceOption {
    text: LocalizedText;
    correct?: boolean;
    feedback?: LocalizedText;
}

export interface ChoiceStep extends BoardDecor {
    type: 'choice';
    fen?: string;
    text: LocalizedText;
    options: ChoiceOption[];
}

export type QuestionStep = FindMoveStep | ChoiceStep;
export type Step = TextStep | DemoStep | QuestionStep;

export interface Lesson {
    id: string;
    course: string;
    /** Lesson order within the course. */
    order: number;
    title: LocalizedText;
    summary: LocalizedText;
    steps: Step[];
    exam: QuestionStep[];
}

export interface CourseInfo {
    id: string;
    order: number;
    title: LocalizedText;
    summary: LocalizedText;
}

export const MAX_EXAM_QUESTIONS = 5;
