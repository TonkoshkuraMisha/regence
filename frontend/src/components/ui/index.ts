// --- FILE: frontend/src/components/ui/index.ts ---
// Shared Regence design components (owner plan of 18.11): page frame, cards, buttons, badges, progress,
// tabs, empty state, modal window. Usage rules are in docs/design-system.md; showcase - the /design page.
// A single import point: pages take components with one import from this folder.

export {Page, PageHeader, Section} from './Page';
export type {PageWidth} from './Page';
export {Card, CardGrid} from './Card';
export type {CardVariant} from './Card';
export {Button, ButtonLink, buttonClasses} from './Button';
export type {ButtonSize, ButtonVariant} from './Button';
export {Badge, EmptyState, ProgressBar} from './Indicators';
export type {BadgeTone} from './Indicators';
export {SegmentedControl} from './SegmentedControl';
export type {SegmentOption} from './SegmentedControl';
export {Modal} from './Modal';
