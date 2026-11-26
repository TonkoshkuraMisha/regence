// --- FILE: frontend/src/components/tournaments/Diploma.tsx ---
// Tournament prize-winner diploma (task 15.3): custom SVG design on the client (drawn by code, no third-party images),
// saving to PNG and printing. Decoration (parchment gradient, triple frame, corner scrolls, dividers, symmetric laurel
// branches, beaded medal) is plain SVG paths defined once in <defs> and reused, so it is the same in the PNG and in the
// print window. The whole colour scheme (paper, frames, ornaments, laurel, medal, ink) follows the place: gold, silver or
// bronze (PALETTES). Used in TournamentsPage.tsx (TournamentView) for places 1-3 of a finished
// tournament. Data - only component props; texts - catalogue tournaments.diploma.*; no network needed.

import {useRef} from 'react';
import {useI18n} from '../../i18n';

/** Diploma props: player name, place (1-3), format or historic tournament name, size and date. */
export interface DiplomaProps {
    name: string;
    place: number;
    format: string;
    size: number;
    date: string;
}

/** Colour scheme of a diploma: every colour used by the drawing, so one place = one palette (gold, silver, bronze). */
interface Palette {
    paper: [string, string, string]; // parchment gradient: centre, middle, edge
    frame: string; // outer thick frame and thin inner line
    accent: string; // ornaments, thin frame, dividers
    accentLight: string; // light thin frame line, divider diamond
    leaf: string; // laurel leaf fill
    leafEdge: string; // laurel leaf outline and stem
    vein: string; // laurel leaf vein (highlight)
    medal: string; // medal disc
    inkStrong: string; // winner name, place number
    ink: string; // title and place text
    inkMid: string; // "awarded to"
    inkSoft: string; // subtitle and event line
}

// Palettes by place (index is place minus one): gold, silver, bronze.
const PALETTES: Palette[] = [
    {
        paper: ['#fbf4e2', '#f3e6c8', '#e6d0a4'], frame: '#5b3a1e', accent: '#a9773f', accentLight: '#c99a45',
        leaf: '#b8862f', leafEdge: '#6b4513', vein: '#f0d98a', medal: '#d4a017',
        inkStrong: '#2a1a0c', ink: '#3b2412', inkMid: '#5b3a1e', inkSoft: '#7a5230',
    },
    {
        paper: ['#f9fafc', '#eaedf2', '#d2d8e1'], frame: '#3f4652', accent: '#7d8696', accentLight: '#a9b1bf',
        leaf: '#9aa3b2', leafEdge: '#4d5562', vein: '#eef1f5', medal: '#b9bec7',
        inkStrong: '#161a21', ink: '#262c36', inkMid: '#3f4652', inkSoft: '#566070',
    },
    {
        paper: ['#fbf0e4', '#f1dcc4', '#dfc0a0'], frame: '#5a2e16', accent: '#9c5a32', accentLight: '#c07a4a',
        leaf: '#b0703c', leafEdge: '#5e3014', vein: '#ebb98c', medal: '#b0703c',
        inkStrong: '#2a1408', ink: '#3d2010', inkMid: '#5a2e16', inkSoft: '#7a4a2c',
    },
];

// Laurel branch beside the medal, drawn once for the left side and mirrored for the right one, so both are exactly symmetric.
// The stem is an arc around the medal from the bottom (angle 98, SVG degrees, 90 = straight down) up to the upper left (244);
// leaves grow in pairs along it in the growth direction and get smaller towards the tip.
const MEDAL_CENTER = {x: 707, y: 668};
const STEM_RADIUS = 114;
const STEM_START_DEG = 98;
const STEM_END_DEG = 244;
const LEAF_PAIRS = 7;
const LEAF_SPREAD_DEG = 40; // angle between a leaf and the stem
const LEAF_LENGTH_BASE = 50;
const LEAF_LENGTH_TAPER = 17;
const TIP_LEAF_LENGTH = 36;

/** Point of the stem circle at the given angle. */
function stemPoint(deg: number): { x: number; y: number } {
    const rad = (deg * Math.PI) / 180;
    return {x: MEDAL_CENTER.x + STEM_RADIUS * Math.cos(rad), y: MEDAL_CENTER.y + STEM_RADIUS * Math.sin(rad)};
}

/** Pointed leaf of the given length lying along +x from the origin. */
function leafPath(length: number): string {
    const w = length * 0.3;
    return `M0 0 C${length * 0.3} ${-w} ${length * 0.75} ${-w * 0.8} ${length} 0 C${length * 0.75} ${w * 0.8} ${length * 0.3} ${w} 0 0Z`;
}

const STEM_START = stemPoint(STEM_START_DEG);
const STEM_END = stemPoint(STEM_END_DEG);
const STEM_PATH = `M${STEM_START.x} ${STEM_START.y} A${STEM_RADIUS} ${STEM_RADIUS} 0 0 1 ${STEM_END.x} ${STEM_END.y}`;

/** Leaves of the branch: base point, direction (degrees) and length. */
const BRANCH_LEAVES = [
    ...Array.from({length: LEAF_PAIRS}, (_, i) => {
        const t = i / (LEAF_PAIRS - 1);
        const deg = STEM_START_DEG + (STEM_END_DEG - STEM_START_DEG) * t;
        const {x, y} = stemPoint(deg);
        const length = LEAF_LENGTH_BASE - LEAF_LENGTH_TAPER * t;
        const growth = deg + 90; // the tangent of the circle, pointing the way the branch grows
        return [
            {x, y, rotate: growth - LEAF_SPREAD_DEG, length},
            {x, y, rotate: growth + LEAF_SPREAD_DEG, length},
        ];
    }).flat(),
    {...STEM_END, rotate: STEM_END_DEG + 90, length: TIP_LEAF_LENGTH},
];

/** Diploma SVG markup as a string - for saving to PNG and printing. */
function svgMarkup(svg: SVGSVGElement): string {
    return new XMLSerializer().serializeToString(svg);
}

/** Diploma in SVG with "Save PNG" (via canvas) and "Print" (a separate window with the same SVG) buttons. */
export function Diploma({name, place, format, size, date}: DiplomaProps) {
    const {t} = useI18n();
    const svgRef = useRef<SVGSVGElement>(null);
    const c = PALETTES[Math.min(Math.max(place, 1), 3) - 1];

    const savePng = () => {
        const svg = svgRef.current;
        if (!svg) return;
        const blob = new Blob([svgMarkup(svg)], {type: 'image/svg+xml;charset=utf-8'});
        const url = URL.createObjectURL(blob);
        const image = new Image();
        // PNG size 1600x1131 - the proportions of an A4 sheet in landscape (like the 1414x1000 viewBox).
        image.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = 1600;
            canvas.height = 1131;
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);
            const link = document.createElement('a');
            link.download = `regence-diploma-${place}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
        };
        image.src = url;
    };

    const print = () => {
        const svg = svgRef.current;
        const win = window.open('', '_blank');
        if (!svg || !win) return;
        win.document.write(`<html><head><title>${t('tournaments.diploma.title')}</title>`
            + '<style>@page{size:landscape;margin:0}body{margin:0}svg{width:100vw;height:100vh}</style></head>'
            + `<body>${svgMarkup(svg)}</body></html>`);
        win.document.close();
        win.focus();
        win.print();
    };

    return (
        <div className="flex flex-col gap-2" data-testid="diploma">
            <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" xmlnsXlink="http://www.w3.org/1999/xlink"
                 viewBox="0 0 1414 1000" className="w-full rounded-md shadow-heavy"
                 role="img" aria-label={t('tournaments.diploma.title')}>
                <defs>
                    <radialGradient id="dp-paper" cx="50%" cy="45%" r="75%">
                        <stop offset="0" stopColor={c.paper[0]}/>
                        <stop offset="0.7" stopColor={c.paper[1]}/>
                        <stop offset="1" stopColor={c.paper[2]}/>
                    </radialGradient>
                    {/* Corner scroll, drawn for the top-left corner of the inner frame and mirrored into the other three. */}
                    <g id="dp-corner" fill="none" stroke={c.accent} strokeWidth="3" strokeLinecap="round">
                        <path d="M0 96 Q0 0 96 0"/>
                        <path d="M0 64 Q0 0 64 0" strokeWidth="1.5"/>
                        <path d="M22 22 c14 -6 26 4 21 16 c-4 9 -17 9 -19 0 c-1 -6 5 -9 9 -6"/>
                        <path d="M10 118 c3 -10 12 -14 18 -8 M118 10 c-10 3 -14 12 -8 18" strokeWidth="2"/>
                        <circle cx="8" cy="8" r="5" fill={c.accent} stroke="none"/>
                        <path d="M0 132 L5 124 L10 132 L5 140Z M132 0 L124 5 L132 10 L140 5Z" fill={c.accent} stroke="none"/>
                    </g>
                    {/* Right half of a divider: a wave with a curl and a bud; the left half is its mirror image. */}
                    <g id="dp-divider-half" fill="none" stroke={c.accent} strokeWidth="2.5" strokeLinecap="round">
                        <path d="M28 0 C58 -16 88 16 128 0 S176 -9 300 0"/>
                        <path d="M128 0 c12 -24 42 -16 36 4 c-4 11 -20 9 -17 -3"/>
                        <path d="M60 -7 c4 -12 14 -14 20 -8 c-8 -1 -12 3 -14 9Z" fill={c.accent}/>
                        <circle cx="30" cy="0" r="3.5" fill={c.accent} stroke="none"/>
                    </g>
                    <g id="dp-divider">
                        <use href="#dp-divider-half"/>
                        <use href="#dp-divider-half" transform="scale(-1,1)"/>
                        <path d="M0 -14 L14 0 L0 14 L-14 0Z" fill={c.accentLight} stroke={c.frame} strokeWidth="1.5"/>
                        <circle r="4" fill={c.paper[0]}/>
                    </g>
                    {/* Left laurel branch; the right one is the same group mirrored about the medal centre. */}
                    <g id="dp-branch">
                        <path d={STEM_PATH} fill="none" stroke={c.leafEdge} strokeWidth="3.5" strokeLinecap="round"/>
                        {BRANCH_LEAVES.map((leaf) => (
                            <g key={`${leaf.rotate}-${leaf.length}`} transform={`translate(${leaf.x},${leaf.y}) rotate(${leaf.rotate})`}>
                                <path d={leafPath(leaf.length)} fill={c.leaf} stroke={c.leafEdge} strokeWidth="1.2" strokeLinejoin="round"/>
                                <path d={`M3 0 L${leaf.length * 0.85} 0`} stroke={c.vein} strokeWidth="1.3" strokeLinecap="round"/>
                            </g>
                        ))}
                    </g>
                </defs>
                <rect width="1414" height="1000" fill="url(#dp-paper)"/>
                <rect x="30" y="30" width="1354" height="940" fill="none" stroke={c.frame} strokeWidth="10"/>
                <rect x="46" y="46" width="1322" height="908" fill="none" stroke={c.accentLight} strokeWidth="2"/>
                <rect x="55" y="55" width="1304" height="890" fill="none" stroke={c.accent} strokeWidth="3"/>
                <rect x="63" y="63" width="1288" height="874" fill="none" stroke={c.frame} strokeWidth="1"/>
                <use href="#dp-corner" transform="translate(78,78)"/>
                <use href="#dp-corner" transform="translate(1336,78) scale(-1,1)"/>
                <use href="#dp-corner" transform="translate(78,922) scale(1,-1)"/>
                <use href="#dp-corner" transform="translate(1336,922) scale(-1,-1)"/>
                <text x="707" y="190" textAnchor="middle" fontFamily="Georgia, serif" fontSize="92" letterSpacing="8" fill={c.ink}>
                    {t('tournaments.diploma.title')}
                </text>
                <text x="707" y="265" textAnchor="middle" fontFamily="Georgia, serif" fontSize="38" letterSpacing="2" fill={c.inkSoft}>
                    {t('tournaments.diploma.heading')}
                </text>
                <use href="#dp-divider" transform="translate(707,305)"/>
                <text x="707" y="390" textAnchor="middle" fontFamily="Georgia, serif" fontSize="34" fill={c.inkMid} fontStyle="italic">
                    {t('tournaments.diploma.awarded')}
                </text>
                <text x="707" y="490" textAnchor="middle" fontFamily="Georgia, serif" fontSize="80" fontWeight="bold" fill={c.inkStrong}>
                    {name}
                </text>
                <use href="#dp-divider" transform="translate(707,530) scale(0.6)"/>
                <use href="#dp-branch"/>
                <use href="#dp-branch" transform={`translate(${2 * MEDAL_CENTER.x},0) scale(-1,1)`}/>
                <circle cx={MEDAL_CENTER.x} cy={MEDAL_CENTER.y} r="94" fill="none" stroke={c.accent} strokeWidth="5" strokeDasharray="1 11" strokeLinecap="round"/>
                <circle data-testid="diploma-medal" cx={MEDAL_CENTER.x} cy={MEDAL_CENTER.y} r="80" fill={c.medal} stroke={c.frame} strokeWidth="4"/>
                <circle cx={MEDAL_CENTER.x} cy={MEDAL_CENTER.y} r="68" fill="none" stroke={c.frame} strokeWidth="1.5" opacity="0.6"/>
                <text x="707" y={MEDAL_CENTER.y + 30} textAnchor="middle" fontFamily="Georgia, serif" fontSize="90" fontWeight="bold" fill={c.inkStrong}>
                    {place}
                </text>
                <text x="707" y="848" textAnchor="middle" fontFamily="Georgia, serif" fontSize="40" fill={c.ink}>
                    {t('tournaments.diploma.place', {place})}
                </text>
                <text x="707" y="896" textAnchor="middle" fontFamily="Georgia, serif" fontSize="28" fill={c.inkSoft}>
                    {t('tournaments.diploma.event', {format, size, date})}
                </text>
                <use href="#dp-divider" transform="translate(707,924) scale(0.45)"/>
                <text x="235" y="290" textAnchor="middle" fontSize="100" fill={c.accent}>♞</text>
                <text x="1179" y="290" textAnchor="middle" fontSize="100" fill={c.accent}>♛</text>
            </svg>
            <div className="flex gap-2">
                <button type="button" onClick={savePng}
                        className="px-3 py-1.5 rounded-md bg-amber-700 text-white font-bold hover:bg-amber-600 cursor-pointer">
                    {t('tournaments.diploma.save')}
                </button>
                <button type="button" onClick={print}
                        className="px-3 py-1.5 rounded-md bg-black/40 border border-amber-700/50 hover:bg-black/60 cursor-pointer">
                    {t('tournaments.diploma.print')}
                </button>
            </div>
        </div>
    );
}
