// --- FILE: frontend/src/components/InviteFriend.tsx ---
// "Invite a friend" (task 26.2): the player's personal link of the form <site address>/?invite=CODE and a counter of how many people have
// registered through it. The code is issued by the server (GET /beta/my-invite, src/services/beta.py): on the first request it is
// created and does not change afterwards. The link is opened by the registration form with the code already filled in (App.tsx reads ?invite).

import {useEffect, useState} from 'react';
import {Copy, Check} from 'lucide-react';
import {useI18n} from '../i18n';
import {betaApi} from '../services/beta';

export function InviteFriend() {
    const {t} = useI18n();
    const [invite, setInvite] = useState<{ code: string; uses: number } | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        let cancelled = false;
        betaApi.myInvite().then((r) => { if (!cancelled) setInvite(r); }).catch(() => undefined);
        return () => { cancelled = true; };
    }, []);

    if (!invite) return null;
    const link = `${window.location.origin}/?invite=${invite.code}`;
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
        } catch {
            // The clipboard is unavailable: the link stays in the field and can be copied manually.
        }
    };

    return (
        <div className="bg-acacia-dark border border-amber-900/40 p-5 rounded shadow-heavy flex flex-col gap-2" data-testid="invite-friend">
            <h2 className="text-sm uppercase tracking-widest text-amber-500/80 font-bold">{t('profile.invite.title')}</h2>
            <p className="text-sm text-boxwood/80">{t('profile.invite.hint')}</p>
            <div className="flex gap-2">
                <input readOnly value={link} aria-label={t('profile.invite.title')} data-testid="invite-link"
                       onFocus={(e) => e.currentTarget.select()}
                       className="flex-1 min-w-0 bg-black/40 border border-amber-900/50 rounded px-2 py-1 text-sm font-mono"/>
                <button type="button" onClick={() => void copy()} data-testid="invite-copy"
                        className="px-3 py-1 rounded bg-amber-800 hover:bg-amber-700 text-white text-sm flex items-center gap-1.5">
                    {copied ? <Check size={14}/> : <Copy size={14}/>}
                    {t(copied ? 'profile.invite.copied' : 'profile.invite.copy')}
                </button>
            </div>
            <span className="text-xs text-boxwood/70" data-testid="invite-uses">{t('profile.invite.uses', {count: invite.uses})}</span>
        </div>
    );
}
