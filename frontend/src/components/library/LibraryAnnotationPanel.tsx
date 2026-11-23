// Library game annotation (task 27.4): the coach's comment on the current move and navigation between comments.
// The auto status is a draft assembled automatically (the label says so directly); approved means checked by the owner.
// The texts are coach.* codes from annotation.comments (services/library.ts, GET /library/games/{id}), assembled by coachText.
// Used in GameViewer.tsx in library mode; with no comments at all there is no panel.

import {ChevronLeft, ChevronRight, MessageSquareText} from 'lucide-react';
import {useI18n} from '../../i18n';
import {coachText} from '../../services/coach';
import type {LibraryAnnotation} from '../../services/library';

// annotation is the game annotation; viewIndex is the current viewing position (ply); onSelect jumps to a ply.
interface Props {
    annotation: LibraryAnnotation;
    viewIndex: number;
    onSelect: (index: number) => void;
}

/** Comment on the move viewIndex and buttons to the previous/next commented move. */
export function LibraryAnnotationPanel({annotation, viewIndex, onSelect}: Props) {
    const {t} = useI18n();
    const plies = Object.keys(annotation.comments).map(Number).filter((n) => coachText(annotation.comments[String(n)], t))
        .sort((a, b) => a - b);
    const current = annotation.comments[String(viewIndex)];
    const text = coachText(current, t);
    const previous = [...plies].reverse().find((n) => n < viewIndex);
    const next = plies.find((n) => n > viewIndex);
    if (plies.length === 0) return null;
    return (
        <div className="flex flex-col gap-1.5 text-xs" data-testid="library-annotation">
            <div className="flex items-center gap-1.5 font-bold text-amber-200">
                <MessageSquareText size={14} className="text-amber-400"/> {t('library.annotation.title')}
                <span className="font-normal text-boxwood/60">
                    {t(annotation.status === 'approved' ? 'library.annotation.approved' : 'library.annotation.auto', {n: plies.length})}
                </span>
            </div>
            <p className="bg-black/30 rounded p-2 min-h-[2.5rem]" data-testid="library-annotation-text">
                {text || <span className="text-boxwood/60">{t('library.annotation.none')}</span>}
            </p>
            <div className="flex gap-2">
                <button type="button" disabled={previous === undefined} onClick={() => previous !== undefined && onSelect(previous)}
                        data-testid="library-annotation-prev"
                        className="px-2 py-1 rounded bg-black/40 disabled:opacity-40 flex items-center gap-1">
                    <ChevronLeft size={13}/> {t('library.annotation.prev')}
                </button>
                <button type="button" disabled={next === undefined} onClick={() => next !== undefined && onSelect(next)}
                        data-testid="library-annotation-next"
                        className="px-2 py-1 rounded bg-black/40 disabled:opacity-40 flex items-center gap-1">
                    {t('library.annotation.next')} <ChevronRight size={13}/>
                </button>
            </div>
        </div>
    );
}
