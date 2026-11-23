// --- FILE: frontend/src/components/xray/useXraySettings.ts ---
// "X-ray" settings (task 12.1): which modes are enabled and which side to look from. Modes are remembered in
// localStorage (key regence_xray_modes), "for the opponent" is not: it resets on a fresh page load.
// The hook is used by Chessboard.tsx, GameViewer.tsx and chessboard/AuxBoard.tsx; rendered by XrayPanel and XrayOverlay.

import {useCallback, useState} from 'react';

/** An "x-ray" mode; key xray.modes.<mode>.name/legend in the three catalogs and a field of the xrayFor report. */
export type XrayMode =
    | 'control' | 'hanging' | 'lines' | 'captures' | 'defenses' | 'checks' | 'moves' | 'pawns' | 'safety';

/** All modes in panel display order; localStorage values not listed here are discarded. */
export const XRAY_MODES: readonly XrayMode[] = [
    'control', 'hanging', 'lines', 'captures', 'defenses', 'checks', 'moves', 'pawns', 'safety',
];

/** localStorage key holding the list of enabled modes (JSON array). */
const STORAGE_KEY = 'regence_xray_modes';

/** Read the remembered modes; a corrupted value or unavailable storage gives an empty set. */
function readModes(): Set<XrayMode> {
    try {
        const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
        return new Set((Array.isArray(raw) ? raw : []).filter((m): m is XrayMode => XRAY_MODES.includes(m)));
    } catch {
        return new Set();
    }
}

/** State and actions of the "x-ray" settings. */
export interface XraySettings {
    /** Enabled modes. */
    modes: Set<XrayMode>;
    /** Enable or disable a mode and persist the choice. */
    toggle: (mode: XrayMode) => void;
    /** Show the same hints for the opponent: "what will they answer?". */
    forOpponent: boolean;
    setForOpponent: (value: boolean) => void;
}

/** "X-ray" settings hook: modes are read from localStorage once on creation. */
export function useXraySettings(): XraySettings {
    const [modes, setModes] = useState<Set<XrayMode>>(readModes);
    const [forOpponent, setForOpponent] = useState(false);
    const toggle = useCallback((mode: XrayMode) => {
        setModes((current) => {
            const next = new Set(current);
            if (next.has(mode)) next.delete(mode);
            else next.add(mode);
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
            } catch {
                // private mode - the setting will not be remembered
            }
            return next;
        });
    }, []);
    return {modes, toggle, forOpponent, setForOpponent};
}
