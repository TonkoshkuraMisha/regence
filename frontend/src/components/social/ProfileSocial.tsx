// --- FILE: frontend/src/components/social/ProfileSocial.tsx ---
// Another player's profile (task 17.1): whether they are online, follow (mutual - "friends"), direct challenge and direct message (30.1).
// The challenge is created on the main board (the socket is open there and the time control is chosen): the page passes the name via
// location.state.challenge. Data: socialApi.relation, follow and unfollow (services/social.ts, /api/v1/social); the block is
// hidden for a guest and on one's own profile. Rendered in Profile.tsx. Any player can be challenged - no strength thresholds.
// "Message" is hidden when either side is in kid mode (task 23.1): the server refuses such messages anyway.

import {useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {MessageSquare, Swords, UserCheck, UserPlus} from 'lucide-react';
import {useI18n} from '../../i18n';
import {getToken} from '../../services/authToken';
import {socialApi} from '../../services/social';
import type {Relation} from '../../services/social';
import {ReportButton} from './ModerationPage';
import {useKidMode} from '../../services/kidMode';

/** Action panel over another player's profile: "online" status, follow, challenge, message and report. */
export function ProfileSocial({username, kidMode: theirKidMode = false}: { username: string; kidMode?: boolean }) {
    const {t} = useI18n();
    const myKidMode = useKidMode();
    const navigate = useNavigate();
    const [relation, setRelation] = useState<Relation | null>(null);

    useEffect(() => {
        if (!getToken()) return;
        socialApi.relation(username).then(setRelation).catch(() => setRelation(null));
    }, [username]);

    if (!relation || relation.self) return null;

    const toggle = () => (relation.following ? socialApi.unfollow(username) : socialApi.follow(username))
        .then(setRelation).catch(() => undefined);

    return (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-3 z-10 text-sm" data-testid="profile-social">
            <span className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-full ${relation.online ? 'bg-emerald-400' : 'bg-stone-600'}`}/>
                {t(relation.online ? 'social.online' : 'social.offline')}
            </span>
            {relation.friends && <span className="text-emerald-300" data-testid="profile-friends">{t('social.friends')}</span>}
            <button type="button" onClick={() => void toggle()} data-testid="profile-follow"
                    className="px-2.5 py-1 rounded bg-black/40 border border-amber-800/60 flex items-center gap-1 hover:border-amber-500">
                {relation.following ? <UserCheck size={14}/> : <UserPlus size={14}/>}
                {t(relation.following ? 'social.unfollow' : 'social.follow')}
            </button>
            <button type="button" onClick={() => navigate('/', {state: {challenge: username}})} data-testid="profile-challenge"
                    className="px-2.5 py-1 rounded bg-amber-700 text-white font-bold flex items-center gap-1">
                <Swords size={14}/> {t('social.challenge')}
            </button>
            {!myKidMode && !theirKidMode && (
                <button type="button" onClick={() => navigate(`/messages/${encodeURIComponent(username)}`)} data-testid="profile-message"
                        className="px-2.5 py-1 rounded bg-black/40 border border-amber-800/60 flex items-center gap-1 hover:border-amber-500">
                    <MessageSquare size={14}/> {t('dm.write')}
                </button>
            )}
            <ReportButton username={username}/>
        </div>
    );
}
