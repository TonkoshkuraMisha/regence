// --- FILE: frontend/src/components/InviteFriend.tsx ---
// «Пригласить друга» (таск 26.2): личная ссылка игрока вида <адрес сайта>/?invite=КОД и счётчик, сколько человек уже
// зарегистрировалось по ней. Код выдаёт сервер (GET /beta/my-invite, src/services/beta.py): при первом обращении он
// создаётся и дальше не меняется. Ссылку открывает форма регистрации с уже подставленным кодом (App.tsx читает ?invite).

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
            // Буфер недоступен — ссылка остаётся в поле, её можно скопировать вручную.
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
