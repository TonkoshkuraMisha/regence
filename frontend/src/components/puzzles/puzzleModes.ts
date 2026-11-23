// --- FILE: frontend/src/components/puzzles/puzzleModes.ts ---
// Puzzle page modes and their groups (puzzle page design, owner's plan 18.11). The eight modes used to stand
// as identical buttons in one grid; now they are laid out by meaning:
//   solve  - "Solve": database puzzles by rating, the daily puzzle, a timed run;
//   train  - "Train": a path through techniques, generator exercises, defence, "Save the game";
//   review - "Your games": "My mistakes", positions from the player's own games.
// A new mode is a row in MODE_GROUPS and an icon in MODE_ICONS; labels come from puzzles.modes.*, explanations from
// puzzles.modeInfo.*, group names from puzzles.modeGroups.* (all language catalogs).
// Pure data without network or state; used by PuzzlesPage.tsx and PuzzleModePicker.tsx.

import type {LucideIcon} from 'lucide-react';
import {BookOpen, CalendarDays, Dumbbell, Handshake, History, Shield, Target, Timer} from 'lucide-react';

/** Puzzle page modes; the value goes into the puzzles.modes.* keys and into the buttons' data-testid. */
export type Mode = 'rated' | 'themes' | 'defense' | 'save' | 'drills' | 'personal' | 'daily' | 'timed';
/** Group of mode tabs (puzzles.modeGroups.* key). */
export type ModeGroupId = 'solve' | 'train' | 'review';

/** Mode groups in display order: the row order sets the order of tabs and cards. */
export const MODE_GROUPS: { id: ModeGroupId; modes: Mode[] }[] = [
    {id: 'solve', modes: ['rated', 'daily', 'timed']},
    {id: 'train', modes: ['themes', 'drills', 'defense', 'save']},
    {id: 'review', modes: ['personal']},
];

/** All modes in group order: checking a jump to the page with a ready mode (the daily warm-up). */
export const MODES: Mode[] = MODE_GROUPS.flatMap((group) => group.modes);

/** Icon of each mode (lucide-react) for tabs and cards; an entry is required for every Mode. */
export const MODE_ICONS: Record<Mode, LucideIcon> = {
    rated: Target,
    daily: CalendarDays,
    timed: Timer,
    themes: BookOpen,
    drills: Dumbbell,
    defense: Shield,
    save: Handshake,
    personal: History,
};
