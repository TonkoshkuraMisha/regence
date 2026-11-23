// --- FILE: frontend/src/components/ui/Page.tsx ---
// Page frame (shared design components, owner plan of 18.11; docs/design-system.md): identical width, margins and
// heading across all sections. Widths: narrow - reading and lists (school, rules), default - pages with panels
// (puzzles, tournaments), wide - board with panels (game hall, analysis). Heading: icon, title, a single line
// of explanation and a place for actions on the right (below the title on a phone).

import type {ReactNode} from 'react';

// Page width variant (see the file header).
export type PageWidth = 'narrow' | 'default' | 'wide';

// Maximum content width per variant: 4xl, 6xl and 1600 px.
const WIDTHS: Record<PageWidth, string> = {
    narrow: 'max-w-4xl',
    default: 'max-w-6xl',
    wide: 'max-w-[1600px]',
};

interface PageProps {
    width?: PageWidth;
    children: ReactNode;
    className?: string;
    testId?: string;
}

/** Page container: width by variant, 12/16 px margins, 16 px vertical rhythm. */
export function Page({width = 'default', children, className = '', testId}: PageProps) {
    return (
        <div data-testid={testId}
             className={`w-full ${WIDTHS[width]} mx-auto px-3 sm:px-4 py-4 flex flex-col gap-4 text-boxwood-light ${className}`}>
            {children}
        </div>
    );
}

interface PageHeaderProps {
    title: ReactNode;
    /** Section icon (lucide-react). */
    icon?: ReactNode;
    /** One or two lines: what people do here. */
    description?: ReactNode;
    /** Actions on the right: usually one main button. */
    actions?: ReactNode;
}

/** Page heading: icon, title, explanation and actions on the right. */
export function PageHeader({title, icon, description, actions}: PageHeaderProps) {
    return (
        <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
            <div className="flex flex-col gap-1 min-w-0">
                <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2">
                    {icon && <span className="text-amber-400 shrink-0" aria-hidden>{icon}</span>}
                    <span className="min-w-0 break-words">{title}</span>
                </h1>
                {description && <p className="text-boxwood/80 max-w-3xl">{description}</p>}
            </div>
            {actions && <div className="flex flex-wrap gap-2 shrink-0">{actions}</div>}
        </header>
    );
}

interface SectionProps {
    title: ReactNode;
    /** To the right of the section heading: an "All" link, a counter, etc. */
    aside?: ReactNode;
    children: ReactNode;
    testId?: string;
}

/** Page section: a second-level heading and content indented by 8 px. */
export function Section({title, aside, children, testId}: SectionProps) {
    return (
        <section className="flex flex-col gap-2" data-testid={testId}>
            <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-lg font-bold text-amber-200">{title}</h2>
                {aside && <div className="text-sm text-boxwood/75">{aside}</div>}
            </div>
            {children}
        </section>
    );
}
