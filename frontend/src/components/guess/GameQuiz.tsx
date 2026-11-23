// --- FILE: frontend/src/components/guess/GameQuiz.tsx ---
// Questions after a "whole" game in "Guess the master's move" (task 14.3): who won, where the key moment was, whether the
// game ended in mate. The questions and the check are provided by the server (GET/POST /guess/game/{id}/quiz, src/services/guess_quiz.py) as option
// codes; the component only shows the options and the result. A network error does not affect the game: the block simply does not appear.

import {useEffect, useState} from 'react';
import {useI18n} from '../../i18n';
import type {MessageKey} from '../../i18n';
import {guessApi} from '../../services/guess';
import type {QuizQuestion, QuizResult} from '../../services/guess';

/** Move code like "12w" means "Move 12, White"; the other option codes come from the guess.quiz.option.<code> catalog. */
const MOVE_CODE = /^\d+[wb]$/;

export function GameQuiz({gameId}: { gameId: number }) {
    const {t} = useI18n();
    const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
    const [picked, setPicked] = useState<Record<string, string>>({});
    const [result, setResult] = useState<QuizResult | null>(null);

    useEffect(() => {
        guessApi.quiz(gameId).then((r) => setQuestions(r.questions)).catch(() => setQuestions(null));
    }, [gameId]);

    if (!questions || questions.length === 0) return null;

    const label = (code: string): string => {
        if (!MOVE_CODE.test(code)) return t(`guess.quiz.option.${code}` as MessageKey);
        const side = t(code.endsWith('w') ? 'guess.quiz.option.white' : 'guess.quiz.option.black');
        return t('guess.quiz.option.move', {number: parseInt(code, 10), side});
    };
    const complete = questions.every((q) => picked[q.id]);

    return (
        <div className="bg-black/30 rounded p-3 text-sm flex flex-col gap-3" data-testid="guess-quiz">
            <span className="font-bold text-amber-200">{t('guess.quiz.title')}</span>
            {questions.map((q) => (
                <div key={q.id} className="flex flex-col gap-1.5">
                    <span>{t(`guess.quiz.q.${q.id}` as MessageKey)}</span>
                    <div className="flex flex-wrap gap-2">
                        {q.options.map((code) => {
                            const right = result?.correct[q.id] === code;
                            const wrong = result !== null && picked[q.id] === code && !right;
                            const tone = right ? 'border-emerald-400 bg-emerald-900/40' : wrong ? 'border-rose-400 bg-rose-900/40'
                                : picked[q.id] === code ? 'border-amber-400 bg-amber-900/40' : 'border-amber-900/60 hover:border-amber-500';
                            return (
                                <button key={code} type="button" disabled={result !== null} data-testid={`quiz-${q.id}-${code}`}
                                        aria-pressed={picked[q.id] === code}
                                        onClick={() => setPicked((p) => ({...p, [q.id]: code}))}
                                        className={`px-3 py-1 rounded border ${tone}`}>
                                    {label(code)}
                                </button>
                            );
                        })}
                    </div>
                </div>
            ))}
            {result ? (
                <span className="text-amber-300" data-testid="guess-quiz-score">{t('guess.quiz.score', {score: result.score, total: result.total})}</span>
            ) : (
                <button type="button" disabled={!complete} data-testid="guess-quiz-check"
                        onClick={() => void guessApi.checkQuiz(gameId, picked).then(setResult).catch(() => undefined)}
                        className="self-start px-3 py-1.5 rounded bg-amber-700 text-white font-bold disabled:opacity-40">
                    {t('guess.quiz.check')}
                </button>
            )}
        </div>
    );
}
