// --- FILE: frontend/src/components/ui/SegmentedControl.tsx ---
// Tab switcher (shared design components, owner plan of 18.11; docs/design-system.md): modes and filters on
// one line instead of a scatter of identical buttons. Accessibility - role="tablist"/"tab", aria-selected, left/
// right arrows move the selection (cyclically). Options are caller data: id, label (already in the player's language), icon and
// an optional hint.

import {useRef} from 'react';
import type {KeyboardEvent, ReactNode} from 'react';

/** Tab: id - the selection value, label - the label in the player's language. */
export interface SegmentOption<T extends string> {
    id: T;
    label: ReactNode;
    icon?: ReactNode;
    title?: string;
}

interface Props<T extends string> {
    options: SegmentOption<T>[];
    value: T;
    onChange: (id: T) => void;
    /** Group label for screen readers. */
    label: string;
    /** Full width: tabs share the line equally. */
    stretch?: boolean;
    testIdPrefix?: string;
}

/** Row of tabs; a value outside the option list is allowed (then the group is entered from the first tab). */
export function SegmentedControl<T extends string>({options, value, onChange, label, stretch = false, testIdPrefix}: Props<T>) {
    const refs = useRef<(HTMLButtonElement | null)[]>([]);
    const onKey = (event: KeyboardEvent, index: number) => {
        if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
        event.preventDefault();
        const next = (index + (event.key === 'ArrowRight' ? 1 : options.length - 1)) % options.length;
        onChange(options[next].id);
        refs.current[next]?.focus();
    };
    return (
        <div role="tablist" aria-label={label}
             className={`inline-flex flex-wrap gap-1 rounded-lg bg-black/30 border border-amber-900/50 p-1 ${stretch ? 'w-full' : 'self-start max-w-full'}`}>
            {options.map((option, index) => {
                const selected = option.id === value;
                // The value may come from a neighbouring group (the puzzles page): then the group is entered from the first tab.
                const focusable = selected || (index === 0 && !options.some((o) => o.id === value));
                return (
                    <button key={option.id} type="button" role="tab" aria-selected={selected} tabIndex={focusable ? 0 : -1}
                            ref={(el) => {
                                refs.current[index] = el;
                            }}
                            title={option.title} onClick={() => onChange(option.id)} onKeyDown={(e) => onKey(e, index)}
                            data-testid={testIdPrefix ? `${testIdPrefix}-${option.id}` : undefined}
                            className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-bold transition-colors cursor-pointer ${
                                stretch ? 'flex-1' : ''} ${selected ? 'bg-amber-700 text-white shadow-sm' : 'text-boxwood/80 hover:text-amber-200 hover:bg-white/5'}`}>
                        {option.icon}{option.label}
                    </button>
                );
            })}
        </div>
    );
}
