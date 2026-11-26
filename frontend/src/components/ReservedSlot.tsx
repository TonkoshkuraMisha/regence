// --- FILE: frontend/src/components/ReservedSlot.tsx ---
// A fixed-height line for a message that sits above a chessboard (an error, a notice, a status, a prompt). The slot always
// takes `lines` lines of space whether or not the message is shown or how long it is, so the board below it never shifts when
// the message appears, disappears or changes - a jump of the board is a hard "no" for the product (it strains the eyes).
// Used by every board screen that has a variable text above the board; text that fits nowhere in a slot goes beside or below
// the board instead.

import type {ReactNode} from 'react';

/** Height of one reserved line, in rem: a text-sm line with leading, as the messages above boards use. */
const LINE_REM = 1.5;

/** Reserves `lines` lines (default one) of vertical space for `children`; the content may be empty. */
export function ReservedSlot({lines = 1, className = '', children}: { lines?: number; className?: string; children?: ReactNode }) {
    return <div className={className} style={{minHeight: `${lines * LINE_REM}rem`}}>{children}</div>;
}
