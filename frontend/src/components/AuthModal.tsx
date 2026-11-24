// --- FILE: frontend/src/components/AuthModal.tsx ---
// Sign-in and registration window. Registration: a name and password (name rules are checked by the server, src/schemas/user.py), two
// optional questions about experience and strength, by which the server sets the starting rating, and an invitation code if registration is
// closed (the beta programme). The age is asked explicitly (task 23.1, the site is for 16+): a player under 16 is registered
// by a parent or guardian, who agrees on their behalf and sets a guardian code - the account starts in kid mode. An account
// waiting for deletion does not log in: the window offers to restore it (POST /auth/restore). Server refusals arrive as
// codes and are shown as text from the serverErrors catalog. After sign-in the access token is kept only in page memory
// (services/authToken.ts).

import {useEffect, useState} from 'react';
import {LogIn, UserPlus, X} from 'lucide-react';
import {accountApi, isDeletionPending} from '../services/account';
import {errorMessage, serverErrorMessage} from '../services/apiErrors';
import {offerGuestPersonalityTransfer} from '../services/personalities';
import {EXPERIENCES, PROVISIONAL_GAMES, STRENGTH_BANDS} from '../services/onboarding';
import type {Experience, StrengthBand} from '../services/onboarding';
import {useI18n} from '../i18n';
import {renderUiMessage, uiMessage} from '../i18n';
import type {UiMessage} from '../i18n';
import {setToken} from '../services/authToken';
import {betaApi} from '../services/beta';

/** Message under the heading: an error (a server response by code or its own) or registration success. */
type Feedback = { tone: 'error' | 'success'; message: UiMessage };

interface AuthModalProps {
    onSuccess: (token: string) => void;
    /** Closing without signing in: the cross, a click on the backdrop or Esc. */
    onClose?: () => void;
    /** "Play the first game" after registration (task 17.8): the player's starting rating. */
    onFirstGame?: (rating: number) => void;
    /** For a beginner ("just starting"): a jump to the ABC (14.5). */
    onBasics?: () => void;
    /** Closed registration (task 24.4): an account cannot be created without an invitation code. */
    inviteOnly?: boolean;
    /** Code from an invitation link: the window opens straight on registration with the code already filled in. */
    inviteCode?: string;
}

/**
 * Sign-in and registration window. Sign-in is POST /auth/login (an OAuth2 form), registration is POST /auth/register, password
 * reset is POST /account/password-reset; after registration a welcome is shown, and sign-in is done at once.
 */
export default function AuthModal({onSuccess, onClose: onCloseProp, onFirstGame, onBasics, inviteOnly = false, inviteCode}: AuthModalProps) {
    const {t, tp, language} = useI18n();
    const [isLogin, setIsLogin] = useState(!inviteCode);
    const [invite, setInvite] = useState(inviteCode ?? '');
    // Consent to the rules and privacy policy (task 23.1): without the mark, registration is not submitted.
    const [acceptTerms, setAcceptTerms] = useState(false);
    // Age (task 23.1): not chosen yet, 16 or older, or under 16 with a guardian's consent and code.
    const [age, setAge] = useState<'' | 'adult' | 'under16'>('');
    const [guardianConsent, setGuardianConsent] = useState(false);
    const [guardianCode, setGuardianCode] = useState('');
    // The login answered "waiting for deletion": the window offers to restore the account with the same password.
    const [canRestore, setCanRestore] = useState(false);
    // The code from the link is checked at once: it is better to learn about an invalid invitation before filling in the form.
    const [inviteValid, setInviteValid] = useState<boolean | null>(null);
    useEffect(() => {
        if (!inviteCode) return;
        let cancelled = false;
        betaApi.checkInvite(inviteCode).then((valid) => {
            if (!cancelled) setInviteValid(valid);
        }).catch(() => undefined);
        return () => {
            cancelled = true;
        };
    }, [inviteCode]);
    const showInvite = inviteOnly || Boolean(inviteCode);
    const [experience, setExperience] = useState<Experience | ''>('');
    const [strength, setStrength] = useState<StrengthBand | ''>('');
    // After registration the player is already signed in: a welcome window, closing the window is also sign-in.
    const [welcome, setWelcome] = useState<{ token: string; rating: number } | null>(null);
    const onClose = welcome ? () => onSuccess(welcome.token) : onCloseProp;
    // "Forgot password?" (task 17.5): an email with a link to the linked e-mail.
    const [forgot, setForgot] = useState(false);
    const [email, setEmail] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [feedback, setFeedback] = useState<Feedback | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!onClose) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    const requestReset = async (e: React.FormEvent) => {
        e.preventDefault();
        setFeedback(null);
        setLoading(true);
        try {
            await accountApi.requestPasswordReset(email, language);
            setFeedback({tone: 'success', message: uiMessage('auth.resetSent')});
        } catch (err) {
            setFeedback({tone: 'error', message: errorMessage(err, 'common.noConnection')});
        } finally {
            setLoading(false);
        }
    };

    /** Sign-in by name and password from the form: the token is saved, guest opponents are offered for transfer. */
    const signIn = async (restore = false): Promise<string> => {
        // An OAuth2 form and the refresh cookie of a long sign-in (task 17.5); 429 says how long to wait, not "wrong password".
        const accessToken = await (restore ? accountApi.restore : accountApi.login)(username, password);
        setToken(accessToken);
        // Opponents built by a guest in this browser: offer to transfer them to the profile.
        offerGuestPersonalityTransfer(accessToken)
            .then((result) => {
                if (result?.skipped.length) {
                    const list = result.skipped
                        .map((s) => t('auth.importSkippedItem', {
                            name: s.name,
                            reason: renderUiMessage(
                                serverErrorMessage(s.reason, s.params) ?? {text: s.reason}, t,
                            ),
                        }))
                        .join('; ');
                    window.alert(t('auth.importSkipped', {list}));
                }
            })
            .catch((err) => window.alert(renderUiMessage(errorMessage(err, 'workshop.importFailed'), t)));
        return accessToken;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFeedback(null);
        setCanRestore(false);
        setLoading(true);

        try {
            if (isLogin) {
                onSuccess(await signIn());
            } else {
                // Registration; strength answers are optional (task 17.8): the server sets the starting rating from them.
                const created = await accountApi.register({
                    username, password, accept_terms: acceptTerms,
                    ...(age === 'under16' ? {under_16: true, guardian_consent: guardianConsent, guardian_code: guardianCode} : {}),
                    ...(experience ? {experience} : {}),
                    ...(strength && experience !== 'new' ? {strength} : {}),
                    ...(showInvite && invite.trim() ? {invite_code: invite.trim()} : {}),
                });
                // Sign-in and a welcome with an offer of the first game at once.
                try {
                    setWelcome({token: await signIn(), rating: created.blitz_rating});
                } catch {
                    setIsLogin(true);
                    setFeedback({tone: 'success', message: uiMessage('auth.registered')});
                }
            }
        } catch (err) {
            const message = errorMessage(err, 'common.noConnection');
            setCanRestore(isLogin && isDeletionPending(message));
            setFeedback({tone: 'error', message});
        } finally {
            setLoading(false);
        }
    };

    /** Restore an account waiting for deletion (task 23.1) with the name and password already typed, then sign in. */
    const restoreAccount = async () => {
        setLoading(true);
        try {
            onSuccess(await signIn(true));
        } catch (err) {
            setFeedback({tone: 'error', message: errorMessage(err, 'common.noConnection')});
        } finally {
            setLoading(false);
        }
    };

    return (
        <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onMouseDown={(e) => {
                // Only a click on the backdrop itself: a text selection in a field that ended
                // outside the window must not close it.
                if (e.target === e.currentTarget) onClose?.();
            }}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="auth-modal-title"
                className="relative bg-[#261C14] border-2 border-amber-900/80 rounded-lg p-6 w-full max-w-md shadow-heavy text-boxwood-light font-serif">

                {onClose && (
                    <button
                        type="button"
                        onClick={onClose}
                        title={t('common.closeEsc')}
                        aria-label={t('common.close')}
                        className="absolute top-3 right-3 p-1 rounded text-boxwood/70 hover:text-amber-200 hover:bg-black/30 transition cursor-pointer"
                    >
                        <X size={18}/>
                    </button>
                )}

                <div className="flex justify-center mb-4">
                    <div
                        className="w-12 h-12 rounded bg-boxwood flex items-center justify-center text-acacia-dark font-bold text-2xl shadow-inner border border-amber-600/40">
                        ♞
                    </div>
                </div>

                <h2 id="auth-modal-title" className="text-2xl font-bold text-center text-amber-200 mb-1">
                    {welcome ? t('auth.welcomeTitle', {name: username})
                        : t(forgot ? 'auth.forgotTitle' : isLogin ? 'auth.loginTitle' : 'auth.registerTitle')}
                </h2>
                {!welcome && (
                    <p className="text-xs text-center text-boxwood/70 mb-6">
                        {t(forgot ? 'auth.forgotNote' : isLogin ? 'auth.loginSubtitle' : 'auth.registerSubtitle')}
                    </p>
                )}

                {feedback && (
                    <div
                        role={feedback.tone === 'error' ? 'alert' : 'status'}
                        className={`p-3 mb-4 rounded text-xs text-center border ${feedback.tone === 'success' ? 'bg-emerald-950/60 border-emerald-600/50 text-emerald-200' : 'bg-red-950/80 border-red-800/50 text-red-200'}`}>
                        {renderUiMessage(feedback.message, t)}
                        {canRestore && (
                            <button type="button" onClick={() => void restoreAccount()} disabled={loading} data-testid="auth-restore"
                                    className="block mx-auto mt-2 px-3 py-1 rounded bg-amber-700 text-white font-bold hover:bg-amber-600 disabled:opacity-50">
                                {t('auth.restoreAccount')}
                            </button>
                        )}
                    </div>
                )}

                {welcome ? (
                    <div className="flex flex-col gap-4 mt-4" data-testid="auth-welcome">
                        <p className="text-sm text-center text-boxwood-light">
                            {tp('auth.welcomeRating', PROVISIONAL_GAMES, {rating: welcome.rating})}
                        </p>
                        {experience === 'new' && onBasics && (
                            // Only learned the rules (17.8): ABC 14.5 first, a game optionally after it.
                            <>
                                <p className="text-sm text-center text-boxwood/85">{t('auth.basicsHint')}</p>
                                <button type="button" data-testid="auth-start-basics"
                                        onClick={() => {
                                            onSuccess(welcome.token);
                                            onBasics();
                                        }}
                                        className="py-2.5 bg-amber-700 text-white font-bold rounded hover:bg-amber-600 transition shadow">
                                    {t('auth.startBasics')}
                                </button>
                            </>
                        )}
                        <button type="button" data-testid="auth-first-game"
                                onClick={() => {
                                    onSuccess(welcome.token);
                                    onFirstGame?.(welcome.rating);
                                }}
                                className="py-2.5 bg-boxwood text-acacia-dark font-bold rounded hover:bg-boxwood-light transition shadow border border-amber-600/40">
                            {t('auth.playFirstGame')}
                        </button>
                        <button type="button" onClick={() => onSuccess(welcome.token)}
                                className="text-xs text-amber-400 hover:underline">
                            {t('auth.later')}
                        </button>
                    </div>
                ) : forgot ? (
                    <form onSubmit={(e) => void requestReset(e)} className="flex flex-col gap-4" data-testid="forgot-form">
                        <div>
                            <label htmlFor="auth-email" className="block text-xs text-boxwood/80 mb-1">{t('auth.email')}</label>
                            <input id="auth-email" type="email" autoComplete="email" required value={email}
                                   onChange={(e) => setEmail(e.target.value)}
                                   className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600"/>
                        </div>
                        <button type="submit" disabled={loading}
                                className="mt-2 py-2.5 bg-boxwood text-acacia-dark font-bold rounded hover:bg-boxwood-light transition shadow border border-amber-600/40 disabled:opacity-50">
                            {loading ? t('auth.loading') : t('auth.sendResetLink')}
                        </button>
                    </form>
                ) : (
                <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                    <div>
                        <label htmlFor="auth-username" className="block text-xs text-boxwood/80 mb-1">{t('auth.username')}</label>
                        <input
                            id="auth-username"
                            autoComplete="username"
                            type="text"
                            required
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600"
                            placeholder={t('auth.usernamePlaceholder')}
                        />
                    </div>

                    <div>
                        <label htmlFor="auth-password" className="block text-xs text-boxwood/80 mb-1">{t('auth.password')}</label>
                        <input
                            id="auth-password"
                            autoComplete={isLogin ? 'current-password' : 'new-password'}
                            type="password"
                            required
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600"
                            placeholder="••••••••"
                        />
                    </div>

                    {!isLogin && showInvite && (
                        <div>
                            <label htmlFor="auth-invite" className="block text-xs text-boxwood/80 mb-1">{t('auth.inviteCode')}</label>
                            <input id="auth-invite" type="text" autoComplete="off" autoCapitalize="characters" spellCheck={false}
                                   required={inviteOnly} maxLength={32} value={invite} data-testid="auth-invite"
                                   onChange={(e) => {
                                       setInvite(e.target.value);
                                       setInviteValid(null);
                                   }}
                                   className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm font-mono uppercase focus:outline-none focus:border-amber-600"/>
                            {inviteValid !== null && (
                                <p className={`text-xs mt-1 ${inviteValid ? 'text-emerald-300' : 'text-rose-300'}`} data-testid="auth-invite-status">
                                    {t(inviteValid ? 'auth.inviteValid' : 'auth.inviteNotValid')}
                                </p>
                            )}
                            {inviteOnly && <p className="text-xs text-boxwood/65 mt-1" data-testid="auth-invite-only">{t('auth.inviteOnlyNote')}</p>}
                        </div>
                    )}

                    {!isLogin && (
                        <>
                            <div>
                                <label htmlFor="auth-experience" className="block text-xs text-boxwood/80 mb-1">{t('auth.experienceLabel')}</label>
                                <select id="auth-experience" value={experience}
                                        onChange={(e) => setExperience(e.target.value as Experience | '')}
                                        className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600">
                                    <option value="">{t('auth.notAnswered')}</option>
                                    {EXPERIENCES.map((value) => <option key={value} value={value}>{t(`auth.experience.${value}`)}</option>)}
                                </select>
                            </div>
                            {experience !== 'new' && (
                                <div>
                                    <label htmlFor="auth-strength" className="block text-xs text-boxwood/80 mb-1">{t('auth.strengthLabel')}</label>
                                    <select id="auth-strength" value={strength}
                                            onChange={(e) => setStrength(e.target.value as StrengthBand | '')}
                                            className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600">
                                        <option value="">{t('auth.notAnswered')}</option>
                                        {STRENGTH_BANDS.map((value) => <option key={value} value={value}>{t(`auth.strength.${value}`)}</option>)}
                                    </select>
                                </div>
                            )}
                            <fieldset className="flex flex-col gap-1 text-xs text-boxwood/85" data-testid="auth-age">
                                <legend className="text-boxwood/80 mb-1">{t('auth.ageLabel')}</legend>
                                {(['adult', 'under16'] as const).map((value) => (
                                    <label key={value} className="flex items-start gap-2">
                                        <input type="radio" name="auth-age" value={value} required checked={age === value}
                                               onChange={() => setAge(value)} data-testid={'auth-age-' + value} className="mt-0.5"/>
                                        {t(value === 'adult' ? 'auth.age16Plus' : 'auth.ageUnder16')}
                                    </label>
                                ))}
                            </fieldset>
                            {age === 'under16' && (
                                <div className="flex flex-col gap-2 p-2 rounded border border-amber-800/50 bg-black/20" data-testid="auth-guardian">
                                    <label className="flex items-start gap-2 text-xs text-boxwood/85">
                                        <input type="checkbox" required checked={guardianConsent} data-testid="auth-guardian-consent"
                                               onChange={(e) => setGuardianConsent(e.target.checked)} className="mt-0.5"/>
                                        <span>{t('auth.guardianConsent')}</span>
                                    </label>
                                    <div>
                                        <label htmlFor="auth-guardian-code" className="block text-xs text-boxwood/80 mb-1">{t('auth.guardianCode')}</label>
                                        <input id="auth-guardian-code" type="password" autoComplete="off" required minLength={4} maxLength={32}
                                               value={guardianCode} onChange={(e) => setGuardianCode(e.target.value)} data-testid="auth-guardian-code"
                                               className="w-full px-3 py-2 bg-black/40 border border-amber-900/60 rounded text-amber-100 text-sm focus:outline-none focus:border-amber-600"/>
                                        <p className="text-xs text-boxwood/65 mt-1">{t('auth.guardianCodeNote')}</p>
                                    </div>
                                </div>
                            )}
                            <label className="flex items-start gap-2 text-xs text-boxwood/85" htmlFor="auth-terms">
                                <input id="auth-terms" type="checkbox" required checked={acceptTerms} data-testid="auth-terms"
                                       onChange={(e) => setAcceptTerms(e.target.checked)} className="mt-0.5"/>
                                <span>
                                    {t('auth.acceptTermsLead')}{' '}
                                    <a href="/terms" target="_blank" rel="noreferrer" className="underline">{t('auth.termsTermsLink')}</a>,{' '}
                                    <a href="/rules" target="_blank" rel="noreferrer" className="underline">{t('auth.termsRulesLink')}</a>{' '}
                                    {t('auth.termsAnd')}{' '}
                                    <a href="/privacy" target="_blank" rel="noreferrer" className="underline">{t('auth.termsPrivacyLink')}</a>
                                </span>
                            </label>
                        </>
                    )}

                    <button
                        type="submit"
                        disabled={loading}
                        className="mt-2 flex items-center justify-center gap-2 py-2.5 bg-boxwood text-acacia-dark font-bold rounded hover:bg-boxwood-light transition shadow border border-amber-600/40 disabled:opacity-50"
                    >
                        {isLogin ? <LogIn size={18}/> : <UserPlus size={18}/>}
                        {loading ? t('auth.loading') : t(isLogin ? 'auth.submitLogin' : 'auth.submitRegister')}
                    </button>
                </form>
                )}

                {!welcome && <div className="mt-4 text-center text-xs flex flex-col gap-2">
                    {isLogin && (
                        <button type="button" data-testid="auth-forgot"
                                onClick={() => {
                                    setForgot(!forgot);
                                    setFeedback(null);
                                }}
                                className="text-amber-400 hover:underline">
                            {t(forgot ? 'auth.backToLogin' : 'auth.forgotPassword')}
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => {
                            setIsLogin(!isLogin);
                            setForgot(false);
                            setFeedback(null);
                            setCanRestore(false);
                        }}
                        className="text-amber-400 hover:underline"
                    >
                        {t(isLogin ? 'auth.toRegister' : 'auth.toLogin')}
                    </button>
                </div>}

            </div>
        </div>
    );
}