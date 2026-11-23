// --- FILE: frontend/src/components/puzzles/PuzzleModePicker.tsx ---
// Mode choice on the puzzle page (owner's plan 18.11): three groups of tabs with a group label ("Solve",
// "Train", "Your games") and a one-line explanation of the selected mode. The composition of the groups and icons are in
// puzzleModes.ts; the texts are puzzles.modeGroups.*, puzzles.modes.*, puzzles.modeInfo.* in all language catalogs.
// Mode buttons have data-testid "puzzle-mode-<mode>"; the mode cards before the start (PuzzlesPage) have the same id: only one of the two
// is always on screen, and tests follow the player's path without knowing what is currently shown.
// It holds no state: the selected mode and the handler come from PuzzlesPage.

import {useI18n} from '../../i18n';
import {SegmentedControl} from '../ui';
import {MODE_GROUPS, MODE_ICONS} from './puzzleModes';
import type {Mode} from './puzzleModes';

interface Props {
    mode: Mode;
    onChange: (mode: Mode) => void;
}

/** Mode tabs by group plus an explanation line for the current mode (data-testid "puzzle-mode-info"). */
export function PuzzleModePicker({mode, onChange}: Props) {
    const {t} = useI18n();
    return (
        <div className="flex flex-col gap-2" data-testid="puzzle-modes">
            <div className="flex flex-wrap gap-x-4 gap-y-2">
                {MODE_GROUPS.map((group) => (
                    <div key={group.id} className="flex flex-col gap-1 min-w-0">
                        <span className="text-[11px] uppercase tracking-wider font-bold text-boxwood/70">
                            {t(`puzzles.modeGroups.${group.id}`)}
                        </span>
                        <SegmentedControl<Mode>
                            label={t(`puzzles.modeGroups.${group.id}`)}
                            value={mode}
                            onChange={onChange}
                            testIdPrefix="puzzle-mode"
                            options={group.modes.map((id) => {
                                const Icon = MODE_ICONS[id];
                                return {id, label: t(`puzzles.modes.${id}`), icon: <Icon size={14} aria-hidden/>};
                            })}
                        />
                    </div>
                ))}
            </div>
            <p className="text-sm text-boxwood/85 leading-snug" data-testid="puzzle-mode-info">
                {t(`puzzles.modeInfo.${mode}`)}
            </p>
        </div>
    );
}
