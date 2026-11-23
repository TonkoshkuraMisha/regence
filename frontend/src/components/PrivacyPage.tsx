// --- FILE: frontend/src/components/PrivacyPage.tsx ---
// "Privacy" (task 23.1): what is stored about the player, for how long and how to manage it. The text is the `privacy.*` keys
// of the i18n catalogs; the figures (move retention of 90 days in src/services/telemetry_retention.py, export and deletion in
// src/services/account.py) must match the server. The page is open without sign-in; it is linked from the consent checkbox in the
// registration window (AuthModal.tsx). Route is App.tsx.

import {Lock} from 'lucide-react';
import {useI18n} from '../i18n';

const SECTIONS = ['s1', 's2', 's3', 's4', 's5'] as const;

export function PrivacyPage() {
    const {t} = useI18n();
    return (
        <article className="max-w-2xl mx-auto w-full px-4 py-6 flex flex-col gap-4" data-testid="privacy-page">
            <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><Lock size={22}/> {t('privacy.title')}</h1>
            <p className="text-boxwood/85">{t('privacy.intro')}</p>
            {SECTIONS.map((section) => (
                <section key={section} className="flex flex-col gap-1">
                    <h2 className="text-lg font-bold text-amber-200">{t(`privacy.${section}Title`)}</h2>
                    <p className="text-boxwood/85">{t(`privacy.${section}Body`)}</p>
                </section>
            ))}
        </article>
    );
}
