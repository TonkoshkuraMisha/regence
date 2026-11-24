// --- FILE: frontend/src/components/TermsPage.tsx ---
// "Terms of use" (tasks 17.5 / 23.1): the rules of using the service in plain words. The text is the `terms.*` keys of the i18n
// catalogs; the facts in it (minimum age 16, the fair-play rule, account deletion, the beta status) must match the code
// (src/schemas/user.py, src/api/fair_play.py, src/services/account.py). It is a working draft written from the code, not a legal
// text: the owner's lawyer reviews it before launch (ToDo 23.1). Open without sign-in; linked from the consent checkbox in the
// registration window (AuthModal.tsx). Changing its meaning means bumping TERMS_VERSION (src/services/legal.py). Route is App.tsx.

import {ScrollText} from 'lucide-react';
import {useI18n} from '../i18n';

const SECTIONS = ['s1', 's2', 's3', 's4', 's5', 's6', 's7'] as const;

export function TermsPage() {
    const {t} = useI18n();
    return (
        <article className="max-w-2xl mx-auto w-full px-4 py-6 flex flex-col gap-4" data-testid="terms-page">
            <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><ScrollText size={22}/> {t('terms.title')}</h1>
            <p className="text-boxwood/85">{t('terms.intro')}</p>
            {SECTIONS.map((section) => (
                <section key={section} className="flex flex-col gap-1">
                    <h2 className="text-lg font-bold text-amber-200">{t(`terms.${section}Title`)}</h2>
                    <p className="text-boxwood/85">{t(`terms.${section}Body`)}</p>
                </section>
            ))}
        </article>
    );
}
