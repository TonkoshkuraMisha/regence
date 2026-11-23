// --- FILE: frontend/src/components/gameViewer/ViewerAppearancePanel.tsx ---
// Choice of pieces and board right in the game viewer (extracted from GameViewer.tsx, task 17.6). Sets and themes are the registries of
// config/boardAppearance.ts; rewards not yet unlocked (config/unlocks.ts) are unavailable and show the unlock condition.
// The choice is saved by the parent (GameViewer.tsx), here is only the view.

import {X} from 'lucide-react';
import {BOARD_THEMES, PIECE_SETS} from '../../config/boardAppearance';
import {useI18n} from '../../i18n';
import {unlockText, useUnlocks} from '../../config/unlocks';

// Look of a choice button: the active one is highlighted.
const option = (active: boolean) => `py-1 px-1 rounded border text-xs font-bold transition cursor-pointer truncate ${
    active ? 'bg-amber-900/50 border-amber-400 text-amber-200' : 'bg-black/35 border-amber-900/40 text-boxwood/75 hover:text-amber-200'
}`;

/** Panel of two rows of buttons: piece set and board theme; locked rewards are disabled, except an already selected one. */
export function ViewerAppearancePanel({pieceSetKey, themeKey, onPieceSetChange, onThemeChange, onClose}: {
    pieceSetKey: string; themeKey: string; onPieceSetChange: (id: string) => void; onThemeChange: (id: string) => void; onClose: () => void;
}) {
    const {t} = useI18n();
    const lockOf = useUnlocks();
    const activePieceSet = PIECE_SETS[pieceSetKey] || PIECE_SETS.merida;
    return (
        <div className="bg-acacia-dark p-3 rounded-md border border-amber-700/50 flex flex-col gap-2 shadow-lg shrink-0" data-testid="viewer-appearance">
            <div className="flex justify-between items-center text-xs text-boxwood/90">
                <span className="font-bold">{t('viewer.piecesLabel')} <span className="text-amber-400">{activePieceSet.name}</span></span>
                <button type="button" onClick={onClose} className="text-boxwood/60 hover:text-white cursor-pointer" aria-label={t('common.close')}>
                    <X size={14}/>
                </button>
            </div>
            <div className="grid grid-cols-5 gap-1">
                {Object.values(PIECE_SETS).map((pset) => (
                    <button key={pset.id} type="button" onClick={() => onPieceSetChange(pset.id)} className={`${option(pset.id === activePieceSet.id)} disabled:opacity-50`}
                            disabled={Boolean(lockOf('pieces', pset.id)) && pset.id !== activePieceSet.id}
                            title={lockOf('pieces', pset.id) ? unlockText(lockOf('pieces', pset.id)!) : undefined}>
                        {pset.shortName}
                    </button>
                ))}
            </div>
            <div className="grid grid-cols-5 gap-1 pt-1 border-t border-amber-900/30">
                {Object.values(BOARD_THEMES).map((theme) => (
                    <button key={theme.id} type="button" onClick={() => onThemeChange(theme.id)} className={`${option(theme.id === themeKey)} disabled:opacity-50`}
                            disabled={Boolean(lockOf('board', theme.id)) && theme.id !== themeKey}
                            title={lockOf('board', theme.id) ? unlockText(lockOf('board', theme.id)!) : undefined}>
                        {theme.name}
                    </button>
                ))}
            </div>
        </div>
    );
}
