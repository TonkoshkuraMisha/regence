// --- FILE: frontend/src/components/settings/KidModeSection.tsx ---
// Kid mode in the settings (task 23.1; rules — src/services/kid_mode.py): what it turns off, and turning it on (the account
// password and an optional guardian code) or off (the guardian code when one is set, otherwise the password). The request is
// POST /account/kid-mode (services/account.ts); the shared flag (services/kidMode.ts) is updated at once so menus and
// chats follow. Rendered in Settings.tsx for a signed-in player.

import {useState} from 'react';
import {Baby} from 'lucide-react';
import {accountApi} from '../../services/account';
import {errorMessage} from '../../services/apiErrors';
import {setKidModeOn} from '../../services/kidMode';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';

/** Shortest guardian code the server accepts (kid_mode.GUARDIAN_CODE_MIN_LENGTH). */
const GUARDIAN_CODE_MIN = 4;
const GUARDIAN_CODE_MAX = 32;

interface KidModeSectionProps {
    sectionClass: string;
    headingClass: string;
    inputClass: string;
    /** State from the profile (GET /profile/me). */
    enabled: boolean;
    guardianCodeSet: boolean;
    onChange: (enabled: boolean, guardianCodeSet: boolean) => void;
}

/** The "Kid mode" section: a note, the current state and one form to turn it on or off. */
export function KidModeSection({sectionClass, headingClass, inputClass, enabled, guardianCodeSet, onChange}: KidModeSectionProps) {
    const {t} = useI18n();
    const [password, setPassword] = useState('');
    const [guardianCode, setGuardianCode] = useState('');
    const [error, setError] = useState<UiMessage | null>(null);
    const [busy, setBusy] = useState(false);
    // Turning off with a guardian code needs only the code; everything else needs the account password.
    const needsCodeOnly = enabled && guardianCodeSet;
    const ready = needsCodeOnly ? guardianCode.length >= GUARDIAN_CODE_MIN : Boolean(password)
        && (guardianCode === '' || guardianCode.length >= GUARDIAN_CODE_MIN);

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setBusy(true);
        try {
            const secret = needsCodeOnly ? {guardian_code: guardianCode}
                : {password, ...(!enabled && guardianCode ? {guardian_code: guardianCode} : {})};
            const state = await accountApi.setKidMode(!enabled, secret);
            setKidModeOn(state.kid_mode);
            onChange(state.kid_mode, state.kid_guardian_code);
            setPassword('');
            setGuardianCode('');
        } catch (err) {
            setError(errorMessage(err, 'settings.kidModeFailed'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className={sectionClass} data-testid="settings-kid-mode">
            <h2 className={headingClass}><Baby size={18} className="text-amber-400"/> {t('settings.kidMode')}</h2>
            <p className="text-sm text-boxwood/80 mb-2 max-w-xl">{t('settings.kidModeNote')}</p>
            <p className="text-sm mb-3 font-bold" data-testid="settings-kid-mode-state">
                {t(enabled ? 'settings.kidModeOn' : 'settings.kidModeOff')}
            </p>
            <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-2 max-w-sm">
                {!needsCodeOnly && (
                    <input type="password" autoComplete="current-password" value={password}
                           onChange={(e) => setPassword(e.target.value)} className={inputClass}
                           placeholder={t('settings.currentPassword')} data-testid="settings-kid-password"/>
                )}
                {(needsCodeOnly || !enabled) && (
                    <input type="password" autoComplete="off" value={guardianCode} maxLength={GUARDIAN_CODE_MAX}
                           onChange={(e) => setGuardianCode(e.target.value)} className={inputClass}
                           placeholder={t(needsCodeOnly ? 'settings.kidGuardianCodeNeeded' : 'settings.kidGuardianCodeOptional')}
                           data-testid="settings-kid-code"/>
                )}
                <button type="submit" disabled={!ready || busy} data-testid="settings-kid-toggle"
                        className="self-start px-4 py-2 rounded-md bg-amber-800 hover:bg-amber-700 text-white text-sm font-bold transition cursor-pointer disabled:opacity-40">
                    {t(enabled ? 'settings.kidModeDisable' : 'settings.kidModeEnable')}
                </button>
            </form>
            {error && <p className="text-sm text-red-300 mt-2" role="alert">{renderUiMessage(error, t)}</p>}
        </section>
    );
}
