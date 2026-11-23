// --- FILE: frontend/src/services/moveNumbers.ts ---
// Move notation with numbers: "1. e4", "e5", "2. Nf3"... If the line starts from its own position (FEN), the number is taken from
// the sixth FEN field, and Black's first move is written "12... Kg7". A pure function, no network.
// Used by the repertoire editor and trainer (repertoire/), Fischer chess (chess960/) and board analysis (tools/).

/** SAN moves with numbers; startFen — the position the line starts from (by default — White's first move). */
export function numberedMoves(sans: string[], startFen?: string): string[] {
    const fields = startFen?.split(' ') ?? [];
    const firstBlack = fields[1] === 'b';
    const firstNumber = Number(fields[5] ?? 1) || 1;
    return sans.map((san, i) => {
        const ply = i + (firstBlack ? 1 : 0);
        const number = firstNumber + Math.floor(ply / 2);
        if (ply % 2 === 0) return `${number}. ${san}`;
        return i === 0 ? `${number}… ${san}` : san;
    });
}
