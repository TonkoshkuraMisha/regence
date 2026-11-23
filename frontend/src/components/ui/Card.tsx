// --- FILE: frontend/src/components/ui/Card.tsx ---
// Card (shared design components, owner plan of 18.11; docs/design-system.md) - one shape for school sections,
// tournaments and puzzle modes: icon, title, short description, status badge, progress and an action at the bottom. Variants:
// default - regular, muted - secondary (closed tournament, "coming soon"), hero - the main one on a page (for example,
// "Grand Course"). With to the whole card is a link; with onClick - a button; otherwise just a block (then actions go
// into footer). CardGrid - a card grid: one column on a phone, two on a tablet, three on a wide screen (or two - cols=2).

import type {ReactNode} from 'react';
import {Link} from 'react-router-dom';

// Card variant (see the file header).
export type CardVariant = 'default' | 'muted' | 'hero';

// Background and border per card variant.
const VARIANTS: Record<CardVariant, string> = {
    default: 'bg-acacia/80 border-acacia-light/60',
    muted: 'bg-black/25 border-amber-900/40 opacity-80',
    hero: 'bg-gradient-to-br from-amber-900/60 to-acacia border-amber-500/80',
};
// Addition for clickable cards: border highlight, slight lift and a keyboard focus ring.
const INTERACTIVE = 'hover:border-amber-400 hover:-translate-y-px transition focus-visible:outline-2 focus-visible:outline-amber-300';

// Card properties; badge, footer and children are optional.
interface CardProps {
    title: ReactNode;
    description?: ReactNode;
    icon?: ReactNode;
    /** Badge in the top right corner (Badge): "completed", "new", "closed". */
    badge?: ReactNode;
    /** Bottom part: progress, buttons. */
    footer?: ReactNode;
    variant?: CardVariant;
    to?: string;
    onClick?: () => void;
    testId?: string;
    children?: ReactNode;
}

/** Card: the root element is chosen by to / onClick (link, button or block). */
export function Card({title, description, icon, badge, footer, variant = 'default', to, onClick, testId, children}: CardProps) {
    const body = (
        <>
            <div className="flex items-start gap-3">
                {icon && (
                    <span className={`shrink-0 rounded-md p-2 ${variant === 'hero' ? 'bg-amber-500/20 text-amber-200' : 'bg-black/25 text-amber-300'}`}
                          aria-hidden>{icon}</span>
                )}
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                        <h3 className={`font-bold leading-snug min-w-0 break-words ${variant === 'hero' ? 'text-lg text-amber-100' : 'text-amber-200'}`}>
                            {title}
                        </h3>
                        {badge && <span className="shrink-0">{badge}</span>}
                    </div>
                    {description && <p className="text-sm text-boxwood/80 leading-snug">{description}</p>}
                </div>
            </div>
            {children}
            {footer && <div className="mt-auto pt-1 flex flex-wrap items-center gap-2">{footer}</div>}
        </>
    );
    const classes = `rounded-lg border p-4 flex flex-col gap-3 text-left text-boxwood-light ${VARIANTS[variant]}`;
    if (to) {
        return <Link to={to} data-testid={testId} className={`${classes} ${INTERACTIVE}`}>{body}</Link>;
    }
    if (onClick) {
        return <button type="button" onClick={onClick} data-testid={testId} className={`${classes} ${INTERACTIVE} cursor-pointer`}>{body}</button>;
    }
    return <div data-testid={testId} className={classes}>{body}</div>;
}

/** Card grid: 1 / 2 / 3 columns by screen width (cols=2 - at most two). */
export function CardGrid({children, cols = 3}: { children: ReactNode; cols?: 2 | 3 }) {
    return <div className={`grid gap-3 sm:grid-cols-2 ${cols === 3 ? 'lg:grid-cols-3' : ''}`}>{children}</div>;
}
