// --- FILE: frontend/src/components/LanguageSwitcher.tsx ---
// Interface language switcher. An ordinary <select>: available from the keyboard and to screen readers, on a phone
// it opens the system list. Languages are labelled with their own names, so one recognises one's own language whatever the current one is.
// The language and the language list are from i18n (useI18n, LANGUAGES); the choice is remembered by the i18n context itself. Used in the app
// header (App.tsx, compact) and on the settings page (Settings.tsx).

import {Languages} from 'lucide-react';
import {LANGUAGES, LANGUAGE_NATIVE_NAMES, LANGUAGE_SHORT_LABELS, isLanguage, useI18n} from '../i18n';

export interface LanguageSwitcherProps {
    /** compact is for the header: only an icon and a language code; otherwise full names (the settings page). */
    compact?: boolean;
    className?: string;
}

/** Language dropdown; compact is the header variant. */
export default function LanguageSwitcher({compact = false, className = ''}: LanguageSwitcherProps) {
    const {t, language, setLanguage} = useI18n();
    return (
        <label
            className={`relative flex items-center gap-1.5 text-boxwood/85 hover:text-amber-300 transition ${className}`}
            title={t('language.choose')}
        >
            <Languages size={compact ? 19 : 17} aria-hidden="true"/>
            <select
                value={language}
                onChange={(e) => {
                    if (isLanguage(e.target.value)) setLanguage(e.target.value);
                }}
                aria-label={t('language.label')}
                className={`bg-black/40 border border-amber-900/50 rounded-md text-amber-200 font-semibold outline-none cursor-pointer focus:border-amber-500 ${
                    compact ? 'px-1 py-1 text-xs uppercase' : 'px-2.5 py-1.5 text-sm'
                }`}
            >
                {LANGUAGES.map((code) => (
                    <option key={code} value={code} lang={code}>
                        {compact ? LANGUAGE_SHORT_LABELS[code] : LANGUAGE_NATIVE_NAMES[code]}
                    </option>
                ))}
            </select>
        </label>
    );
}
