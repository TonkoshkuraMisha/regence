// --- FILE: frontend/src/components/ui/Button.tsx ---
// Platform buttons (shared design components, owner plan of 18.11; rules in docs/design-system.md). Hierarchy:
// primary - the single main action on a screen (amber fill), secondary - ordinary actions (dark with border),
// ghost - secondary (text only), danger - irreversible (resign, delete). Sizes: sm - in dense panels,
// md - default, lg - the main call to action of a page. ButtonLink - the same look for a router link. Classes
// are assembled by buttonClasses - a single source. Showcase - the /design page (DesignGallery).

import type {ButtonHTMLAttributes, ReactNode} from 'react';
import {Link} from 'react-router-dom';
import type {LinkProps} from 'react-router-dom';

// Button variant and size (see the file header).
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

// Common class part: layout, smooth colour change, disabled look and a visible keyboard focus ring.
const BASE = 'inline-flex items-center justify-center gap-1.5 rounded-md font-bold transition-colors cursor-pointer '
    + 'disabled:opacity-45 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 '
    + 'focus-visible:outline-amber-300';

// Colours per button variant.
const VARIANTS: Record<ButtonVariant, string> = {
    primary: 'bg-amber-700 hover:bg-amber-600 text-white shadow-sm',
    secondary: 'bg-black/30 hover:bg-black/45 border border-amber-800/60 hover:border-amber-500 text-boxwood-light',
    ghost: 'text-amber-300 hover:text-amber-200 hover:bg-white/5',
    danger: 'bg-rose-900/70 hover:bg-rose-800 border border-rose-600/60 text-rose-50',
};

// Padding and font size per size.
const SIZES: Record<ButtonSize, string> = {
    sm: 'px-2.5 py-1 text-xs',
    md: 'px-3.5 py-1.5 text-sm',
    lg: 'px-5 py-2.5 text-base',
};

/** Button classes - for places that need another element with the same look (for example, a label). */
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', extra = ''): string {
    return [BASE, VARIANTS[variant], SIZES[size], extra].filter(Boolean).join(' ');
}

// Properties shared by Button and ButtonLink.
interface CommonProps {
    variant?: ButtonVariant;
    size?: ButtonSize;
    /** Icon before the text (lucide-react, size chosen by the caller). */
    icon?: ReactNode;
    children?: ReactNode;
}

/** Button (type="button" by default so forms are not submitted by accident); other properties are as on button. */
export function Button({variant = 'secondary', size = 'md', icon, children, className = '', type = 'button', ...rest}:
                           CommonProps & ButtonHTMLAttributes<HTMLButtonElement>) {
    return (
        <button type={type} className={buttonClasses(variant, size, className)} {...rest}>
            {icon}{children}
        </button>
    );
}

/** Router link styled as a button. */
export function ButtonLink({variant = 'secondary', size = 'md', icon, children, className = '', ...rest}: CommonProps & LinkProps) {
    return (
        <Link className={buttonClasses(variant, size, className)} {...rest}>
            {icon}{children}
        </Link>
    );
}
