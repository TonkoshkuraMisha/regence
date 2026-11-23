// --- FILE: frontend/src/components/PlayerAvatar.tsx ---
// Player avatar from the own set (task 18.4): the "Lewis" piece (CC0) on a coloured background. The player chooses an avatar in the
// settings; until chosen, the avatar is computed from the name. An external avatar service is no longer needed: the player's name does not
// go to a foreign server. The avatar code is "<piece>-<background number>" (for example wN-3), stored in the profile on the server
// (the avatar field, saved via services/profileSettings.ts); piece images are public/assets/pieces/lewis/.
// Used in the leaderboard, profile, settings (AvatarPicker) and the header.

/** Pieces available as an avatar: the colour and kind code of the piece (the SVG file name without the extension). */
export const AVATAR_PIECES = ['wK', 'wQ', 'wR', 'wB', 'wN', 'wP', 'bK', 'bQ', 'bR', 'bB', 'bN', 'bP'] as const;
/** Avatar background colours; the avatar code stores an index into this list. */
export const AVATAR_BACKGROUNDS = ['#D0A972', '#7FA37A', '#7A9CC6', '#C98A7A', '#A58BC4', '#D6C26E', '#6FB0AA', '#B9B2A6'] as const;
// Avatar code format: a piece and a background index (0-7, by the number of AVATAR_BACKGROUNDS).
const AVATAR_RE = /^([wb][KQRBNP])-([0-7])$/;

/** FNV-1a over the name characters: a stable number from which the default piece and background are chosen. */
function hash(text: string): number {
    let h = 2166136261;
    for (const ch of text) h = Math.imul(h ^ ch.codePointAt(0)!, 16777619);
    return h >>> 0;
}

/** Avatar code: the chosen one if it is valid, otherwise by the player's name. */
export function avatarCode(username: string, chosen?: string | null): string {
    if (chosen && AVATAR_RE.test(chosen)) return chosen;
    const h = hash(username.toLowerCase());
    return `${AVATAR_PIECES[h % AVATAR_PIECES.length]}-${(h >>> 8) % AVATAR_BACKGROUNDS.length}`;
}

/** Player avatar: the chosen one or computed from the name; alt is empty if a name is already next to it. */
export function PlayerAvatar({username, avatar, className = 'w-8 h-8', alt = ''}: {
    username: string; avatar?: string | null; className?: string; alt?: string;
}) {
    const [, piece, background] = AVATAR_RE.exec(avatarCode(username, avatar))!;
    return (
        <span className={`inline-flex items-center justify-center overflow-hidden shrink-0 ${className}`}
              style={{backgroundColor: AVATAR_BACKGROUNDS[Number(background)]}} data-testid="player-avatar" data-avatar={`${piece}-${background}`}>
            <img src={`/assets/pieces/lewis/${piece}.svg`} alt={alt} className="w-[86%] h-[86%] object-contain" draggable={false}/>
        </span>
    );
}

/** Avatar choice in the settings: a piece and a background colour. */
export function AvatarPicker({username, value, onChange}: { username: string; value: string | null; onChange: (code: string) => void }) {
    const current = avatarCode(username, value);
    const [, piece, background] = AVATAR_RE.exec(current)!;
    return (
        <div className="flex flex-col gap-2" data-testid="avatar-picker">
            <div className="grid grid-cols-6 gap-1.5 max-w-sm">
                {AVATAR_PIECES.map((code) => (
                    <button key={code} type="button" aria-pressed={code === piece} data-testid={`avatar-piece-${code}`}
                            onClick={() => onChange(`${code}-${background}`)}
                            className={`rounded-md p-0.5 border-2 cursor-pointer ${code === piece ? 'border-amber-400' : 'border-transparent'}`}>
                        <PlayerAvatar username={username} avatar={`${code}-${background}`} className="w-10 h-10 rounded"/>
                    </button>
                ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
                {AVATAR_BACKGROUNDS.map((color, index) => (
                    <button key={color} type="button" aria-pressed={String(index) === background} data-testid={`avatar-bg-${index}`}
                            aria-label={color} onClick={() => onChange(`${piece}-${index}`)}
                            className={`w-7 h-7 rounded-full border-2 cursor-pointer ${String(index) === background ? 'border-amber-300' : 'border-black/40'}`}
                            style={{backgroundColor: color}}/>
                ))}
            </div>
        </div>
    );
}
