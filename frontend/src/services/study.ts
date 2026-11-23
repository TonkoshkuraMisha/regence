// --- FILE: frontend/src/services/study.ts ---
// Joint review and coaching session (task 17.3): the room (/api/v1/study) and club materials.
// Routes — src/api/study.py, sign-in only. The room lives in Redis (src/services/study_room.py) and has no broadcasts over
// WebSocket: participants poll its state (poll) once a second. Club materials — the table
// study_materials.
import {apiRequest} from './http';


export type ArrowColor = 'green' | 'red' | 'blue' | 'yellow';

/** Room board: set entirely by the host (setBoard), the others only see it. */
export interface StudyBoard {
    fen: string;
    last_move: string | null;
    arrows: { from: string; to: string; color: ArrowColor }[];
    highlights: { square: string; tone: 'light' | 'dark' }[];
    /** "Ghost" piece on a square — the host's annotation over the board; it does not change the position (fen). */
    ghost: { square: string; piece: string } | null;
}

/** Host's question: a move on the board (move) or a choice among options (choice), with a timer. */
export interface StudyQuestion {
    id: string;
    kind: 'move' | 'choice';
    prompt: string;
    options?: string[];
    /**
     * Correct answer: an option number or a list of correct moves. The server gives it to a participant only after reveal
     * (revealed); the host always sees it.
     */
    correct?: number | string[];
    /** Answer deadline — server time in Unix seconds. */
    deadline: number;
    revealed: boolean;
}

/** Room state for the asker (study_room.view on the server). */
export interface StudyRoom {
    code: string;
    host: string;
    is_host: boolean;
    /** Grows on every room change: the poll uses it to tell that nothing is new. */
    version: number;
    board: StudyBoard;
    chat: { from: string; text: string; at: number }[];
    question: StudyQuestion | null;
    /** Names of those who recently polled the room. */
    participants: string[];
    /** Host only: participants' answers to the current question (key — player id as a string). */
    answers?: Record<string, { name: string; answer: string | number; correct: boolean }>;
    /** Participant only: their own answer to the current question. */
    my_answer?: string | number;
}

/** Request to /api/v1/study through the shared http.ts wrapper. null — a 204 response: on a poll it means "the room version has not changed". */
const call = async <T>(path: string, init: RequestInit = {}): Promise<T | null> =>
    (await apiRequest<T | undefined>(`/study${path}`, init)) ?? null;

const json = (method: string, body: unknown): RequestInit => ({method, body: JSON.stringify(body)});

/**
 * Room endpoints. The server accepts setBoard, ask and reveal only from the host (refusal code study_host_only),
 * chat and answer — from any participant. Each of them returns the new room state.
 */
export const studyApi = {
    /** Create a room: the creator becomes the host, code — the room code for the invite link. */
    create: () => call<StudyRoom>('', {method: 'POST'}) as Promise<StudyRoom>,
    /** Poll: since — the version the client already has; null — nothing has changed since. */
    poll: (code: string, since: number) => call<StudyRoom>(`/${encodeURIComponent(code)}?since=${since}`),
    setBoard: (code: string, board: StudyBoard) => call<StudyRoom>(`/${code}/board`, json('PUT', board)) as Promise<StudyRoom>,
    chat: (code: string, text: string) => call<StudyRoom>(`/${code}/chat`, json('POST', {text})) as Promise<StudyRoom>,
    ask: (code: string, question: { kind: 'move' | 'choice'; prompt: string; options?: string[]; correct: number | string[]; seconds: number }) =>
        call<StudyRoom>(`/${code}/question`, json('POST', question)) as Promise<StudyRoom>,
    answer: (code: string, answer: string | number) => call<StudyRoom>(`/${code}/answer`, json('POST', {answer})) as Promise<StudyRoom>,
    /** Reveal the correct answer to the current question to all participants. */
    reveal: (code: string) => call<StudyRoom>(`/${code}/reveal`, {method: 'POST'}) as Promise<StudyRoom>,
    /** The player's club materials: sessions saved as lessons in the school format (content/lessons/format.ts). */
    materials: () => call<{ materials: { id: number; title: string; created_at: string }[] }>('/materials'),
    saveMaterial: (title: string, lesson: unknown) =>
        call<{ id: number; title: string }>('/materials', json('POST', {title, lesson})) as Promise<{ id: number; title: string }>,
};
