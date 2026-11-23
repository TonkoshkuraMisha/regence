// --- FILE: frontend/src/components/chessboard/LastMoveArrow.tsx ---
// Last-move arrow (task 18.4, the "show opponent's move" setting in config/boardPrefs.ts: square highlight,
// arrow or both). Semi-transparent; lies under the coach arrows and the player's marks (z-index 25
// versus 30), does not intercept clicks.

import {squareCenter} from './CoachArrowsOverlay';

/** Arrow from square from to square to; for the history move being shown, not only the opponent's move. */
export function LastMoveArrow({from, to, flipped}: { from: string; to: string; flipped: boolean }) {
    const a = squareCenter(from, flipped);
    const b = squareCenter(to, flipped);
    if (!a || !b) return null;
    // The arrowhead does not reach the centre of the square: the piece stays visible.
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const end = {x: b.x - ((b.x - a.x) / len) * 3, y: b.y - ((b.y - a.y) / len) * 3};
    return (
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full z-[25] pointer-events-none" data-testid="last-move-arrow">
            <defs>
                <marker id="last-move-head" markerWidth="3.5" markerHeight="3.5" refX="2.3" refY="1.75" orient="auto">
                    <polygon points="0 0, 3.5 1.75, 0 3.5" fill="rgba(245, 158, 11, 0.85)"/>
                </marker>
            </defs>
            <line x1={a.x} y1={a.y} x2={end.x} y2={end.y} stroke="rgba(245, 158, 11, 0.75)" strokeWidth="2.2" strokeLinecap="round"
                  markerEnd="url(#last-move-head)"/>
        </svg>
    );
}
