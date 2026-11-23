// Settings -> "App" (task 24.2): install the site to the home screen. A button where the browser allows installation
// (Chrome, Edge, Android); on iPhone and iPad, a hint on how to add it manually; if already installed, we say so.
// State and the system dialog are services/pwa.ts (useInstallState, promptInstall); the section is connected by Settings.tsx.

import {Smartphone} from 'lucide-react';
import {useI18n} from '../../i18n';
import {promptInstall, useInstallState} from '../../services/pwa';

/** Settings section; the section and heading classes are passed by Settings.tsx so that the styling matches the neighbouring sections. */
export function InstallAppSection({sectionClass, headingClass}: { sectionClass: string; headingClass: string }) {
    const {t} = useI18n();
    const state = useInstallState();
    return (
        <section className={sectionClass} data-testid="settings-app">
            <h2 className={headingClass}><Smartphone size={18} className="text-amber-400"/> {t('settings.app.title')}</h2>
            <p className="text-sm mb-3">{t('settings.app.intro')}</p>
            {state === 'available' && (
                <button type="button" onClick={() => void promptInstall()} data-testid="settings-app-install"
                        className="px-4 py-2 rounded bg-amber-700 hover:bg-amber-600 text-white font-bold cursor-pointer">
                    {t('settings.app.install')}
                </button>
            )}
            <p className="text-sm text-boxwood/85" data-testid="settings-app-state">
                {state === 'installed' && t('settings.app.installed')}
                {state === 'ios' && t('settings.app.ios')}
                {state === 'unsupported' && t('settings.app.browserMenu')}
            </p>
        </section>
    );
}
