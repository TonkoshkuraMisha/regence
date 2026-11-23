// --- FILE: frontend/src/services/exam.ts ---
// Diagnostic exam (task 22.0): requests to /api/v1/exam (src/api/exam.py) — a summary of the latest results,
// section questions, move checking and answer submission. Used by ExamPage.tsx; the response types are described there as well.
// Request and errors — apiRequest (http.ts).

import {apiRequest} from './http';

/** Request to /api/v1/exam{path}: without body — GET, with body — POST; a refusal becomes a UiError with a code. */
export const examCall = <T>(path: string, body?: object) =>
    apiRequest<T>(`/exam${path}`, body ? {method: 'POST', body: JSON.stringify(body)} : {});
