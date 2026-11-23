// --- FILE: frontend/src/App.tsx ---
// Application shell: the header (sections, language, player search, notifications, messages, profile menu), the sign-in window and all
// site routes (<Routes> at the end of the file). On load it restores sign-in by the refresh cookie
// (services/authToken.ts) and waits for that no longer than SESSION_RESTORE_WAIT_MS; the profile (/profile/me) sets the interface
// language, the theme set and the avatar. Section pages are in components/<section>/; a new page is added here
// as a route and, if it has no parameters, to the ROUTES list of the layout check (e2e/layout.e2e.ts).

import {useState, useRef, useEffect} from 'react';
import {Routes, Route, useNavigate, Link, useLocation} from 'react-router-dom';
import Chessboard from './components/Chessboard';
import AuthModal from './components/AuthModal';
import Profile from './components/Profile';
import GameViewer from './components/GameViewer';
import ChampionGames from './components/ChampionGames';
import Leaderboard from './components/Leaderboard';
import About from './components/About';
import Settings from './components/Settings';
import {ResetPasswordPage, VerifyEmailPage} from './components/EmailLinkPages';
import PuzzlesPage from './components/puzzles/PuzzlesPage';
import {LearnPage, LessonPage} from './components/learn/LearnPage';
import {GuessPage} from './components/guess/GuessPage';
import {BasicsPage, BasicsSectionPage} from './components/learn/BasicsPage';
import {MateConstructionPage, MateCoursePage, MateExamPage} from './components/learn/MateCourse';
import {ClassicGamePage, ClassicsPage} from './components/learn/ClassicsPage';
import {EndgamesPage, EndgameTrainerPage} from './components/learn/EndgameTrainer';
import {ToolsPage} from './components/tools/ToolsPage';
import {WatchPage} from './components/watch/WatchPage';
import {ImportPage} from './components/gameImport/ImportPage';
import {TransparencyPage} from './components/TransparencyPage';
import {PrivacyPage} from './components/PrivacyPage';
import {ArenaPage, ArenasPage} from './components/arena/ArenaPages';
import {ConferencesPage} from './components/arena/ConferencesPage';
import {TeamsPage} from './components/social/TeamsPage';
import {StudyLobby, StudyRoomPage} from './components/study/StudyPages';
import {ModerationPage} from './components/social/ModerationPage';
import {MessagesPage} from './components/social/MessagesPage';
import {FeedPage, PostPage} from './components/social/FeedPage';
import {CommunityRulesPage} from './components/social/Civility';
import {DesignGallery} from './components/DesignGallery';
import {MiniGamePage, MiniGamesPage} from './components/trainers/MiniGames';
import {MiniGameRoomPage} from './components/trainers/MiniGameRoom';
import {Chess960Page} from './components/chess960/Chess960Page';
import {Chess960LiveGame} from './components/chess960/Chess960LiveGame';
import {WorkoutPage} from './components/WorkoutPage';
import {ExamPage} from './components/ExamPage';
import {ProgramPage, ProgramsPage} from './components/ProgramsPage';
import {SupercoursePage} from './components/learn/SupercoursePage';
import {PageErrorBoundary} from './components/PageErrorBoundary';
import {RepertoireEditorPage, RepertoireListPage} from './components/repertoire/RepertoirePages';
import {LibraryPage} from './components/library/LibraryPage';
import {RepertoireDrillPage} from './components/repertoire/RepertoireDrill';
import {moderationApi} from './services/moderation';
import {ReportProblem} from './components/beta/ReportProblem';
import {useSiteConfig} from './services/beta';
import {TrainerPage, TrainersPage} from './components/trainers/TrainersPage';
import {NotificationBell, PlayerSearch} from './components/social/SocialHeader';
import {TournamentView, TournamentsPage} from './components/tournaments/TournamentsPage';
import {TimeMachinePage} from './components/tournaments/TimeMachine';
import {MastersPage} from './components/tournaments/MastersPage';
import {CHAMPIONS_LIST} from './config/champions';
import {API_BASE_URL} from './config/api';
import {gameSocket} from './services/gameSocket';
import * as auth from './services/authToken';
import {isLearningPath, setCheckSounds} from './services/soundEngine';

import {
    Swords,
    Bug,
    LogOut,
    User,
    Settings as SettingsIcon,
    LogIn,
    Crown,
    Medal,
    ChevronDown,
    Trophy,
    Scale,
    Puzzle,
    CloudDownload,
    GraduationCap,
    Eye,
    Wrench,
    Dumbbell,
    Shield,
    Presentation,
    Gavel,
    Newspaper,
    MessageSquare
} from 'lucide-react';
import {isLanguage, useI18n} from './i18n';
import {saveProfileSettings, setTranslationHelper} from './services/profileSettings';
import {applyPreset, findPreset, getSavedPresetId} from './config/themePresets';
import {TranslationHelper} from './components/social/TranslationHelper';
import {PlayerAvatar} from './components/PlayerAvatar';
import {loadUnlocks} from './config/unlocks';
import LanguageSwitcher from './components/LanguageSwitcher';

interface UserProfile {
    id: number;
    username: string;
    bullet_rating: number;
    blitz_rating: number;
    rapid_rating: number;
    classical_rating: number;
    is_cheater: boolean;
    /** Categories with a provisional rating (task 17.8): fewer than 30 games. */
    provisional?: string[];
    /** Languages (task 17.7): the language from the profile and the "translation helper" mode. */
    language?: string | null;
    translation_helper?: boolean;
    /** Theme set (task 18.3). */
    theme_preset?: string | null;
    /** Avatar from the own set (task 18.4). */
    avatar?: string | null;
}

/** How long to wait for sign-in restoration before showing the page without it. */
export const SESSION_RESTORE_WAIT_MS = 3000;

export default function App() {
    const {t, language, setLanguage} = useI18n();
    // The token is in memory (services/authToken): on load sign-in is restored by the httpOnly cookie (task 17.5).
    const [token, setToken] = useState<string | null>(() => auth.getToken());
    // Pages are rendered after the first attempt to restore sign-in (cookie -> token). Otherwise, on a direct visit and on
    // a page refresh, they requested data before the token appeared and got 401: "Time Machine"
    // showed "Failed to load tournaments", the tournament page showed an error, the tournament list stayed empty.
    const [sessionChecked, setSessionChecked] = useState<boolean>(() => auth.getToken() !== null);
    const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
    const [profileRetry, setProfileRetry] = useState(0);

    const [isProfileOpen, setIsProfileOpen] = useState(false);
    // The language is stored in the profile (task 17.7): on sign-in the profile language is applied (so it moves between devices),
    // if the profile has none yet, the current one is written there; after that every language change is saved on the server.
    const languageSyncedFor = useRef<number | null>(null);
    useEffect(() => {
        if (!token || !userProfile) {
            languageSyncedFor.current = null;
            setTranslationHelper(false);
            return;
        }
        setTranslationHelper(!!userProfile.translation_helper);
        if (languageSyncedFor.current !== userProfile.id) {
            languageSyncedFor.current = userProfile.id;
            if (isLanguage(userProfile.language) && userProfile.language !== language) {
                setLanguage(userProfile.language);
                return;
            }
        }
        if (userProfile.language !== language) {
            setUserProfile((p) => (p ? {...p, language} : p));
            saveProfileSettings({language}).catch(() => undefined);
        }
    }, [token, userProfile, language, setLanguage]);
    // The theme set from the profile (task 18.3) is applied on sign-in if another one is chosen in the browser.
    const presetSyncedFor = useRef<number | null>(null);
    useEffect(() => {
        if (!userProfile || presetSyncedFor.current === userProfile.id) return;
        presetSyncedFor.current = userProfile.id;
        const preset = findPreset(userProfile.theme_preset);
        if (preset && preset.id !== getSavedPresetId()) applyPreset(preset);
    }, [userProfile]);
    // Unlockable appearance (task 18.4): the player's earned achievements; a guest has none.
    useEffect(() => {
        void loadUnlocks(token && userProfile ? userProfile.username : null);
    }, [token, userProfile?.username]); // eslint-disable-line react-hooks/exhaustive-deps
    // The "Moderation" item (17.4) is only for a moderator and a player with the unfair play flag (there, an appeal).
    const [showModeration, setShowModeration] = useState(false);
    useEffect(() => {
        if (!token || !userProfile) {
            setShowModeration(false);
            return;
        }
        moderationApi.me().then((m) => setShowModeration(m.is_moderator || m.is_cheater)).catch(() => setShowModeration(false));
    }, [token, userProfile]);
    const [isChampionsMenuOpen, setIsChampionsMenuOpen] = useState(false);

    const [showAuthModal, setShowAuthModal] = useState(false);
    // Beta programme (task 24.4): "Report a problem" from any page; whether registration is closed comes from the server.
    const [showReport, setShowReport] = useState(false);
    const siteConfig = useSiteConfig();
    const [serverPing, setServerPing] = useState<number | null>(null);

    const dropdownRef = useRef<HTMLDivElement>(null);
    const championsMenuRef = useRef<HTMLDivElement>(null);
    const navigate = useNavigate();
    const location = useLocation();
    // Invitation link (/?invite=CODE): the code is remembered, removed from the address, and a guest gets registration opened at once.
    const [inviteCode] = useState(() => new URLSearchParams(location.search).get('invite')?.trim() || undefined);

    // The check sound is only in learning sections; in games it distracts (owner's decision, 17.11).
    useEffect(() => {
        setCheckSounds(isLearningPath(location.pathname));
    }, [location.pathname]);

    const isSingleScreenRoute =
        location.pathname === '/' ||
        location.pathname.startsWith('/challenge/') ||
        // The game viewer is the same screen with a board for the library and for games from other sites: otherwise the move
        // panel stretches over the whole game, and the page moves along with the current move.
        /^\/(game|library\/game|import\/game)\//.test(location.pathname);

    useEffect(() => {
        const unsubscribe = auth.onTokenChange((current) => {
            setToken(current);
            if (!current) {
                setUserProfile(null);
                gameSocket.disconnect();
            }
        });
        // Safety net: if the server does not answer the sign-in restoration, pages do not wait for it longer than three seconds:
        // a guest must see at least what does not need the server.
        const giveUp = setTimeout(() => setSessionChecked(true), SESSION_RESTORE_WAIT_MS);
        void Promise.resolve(auth.restoreSession()).then((restored) => {
            clearTimeout(giveUp);
            setSessionChecked(true);
            if (inviteCode && !restored) setShowAuthModal(true);
        });
        return () => {
            clearTimeout(giveUp);
            unsubscribe();
        };
    }, [inviteCode]);

    useEffect(() => {
        if (inviteCode && new URLSearchParams(location.search).has('invite')) {
            navigate(location.pathname, {replace: true});
        }
    }, [inviteCode, location.pathname, location.search, navigate]);

    useEffect(() => {
        if (!token) {
            setUserProfile(null);
            gameSocket.disconnect();
            return;
        }

        let cancelled = false;
        let retryTimer: ReturnType<typeof setTimeout> | null = null;

        fetch(`${API_BASE_URL}/api/v1/profile/me`, {
            headers: {
                'Authorization': `Bearer ${token}`,
                'accept': 'application/json'
            }
        })
            .then(res => {
                if (res.status === 401) {
                    // Only an authorization refusal means the token is invalid (for example, it expired while the
                    // computer slept). A network error or 5xx is no reason to sign out. First refresh the token by
                    // the cookie; if that fails, sign out (the subscription above).
                    void auth.refreshSession();
                    return null;
                }
                if (!res.ok) throw new Error(`profile/me: HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!cancelled && data) setUserProfile(data);
            })
            .catch(() => {
                // The profile did not load: we try again, the session is not touched.
                if (!cancelled) retryTimer = setTimeout(() => setProfileRetry(n => n + 1), 3000);
            });

        return () => {
            cancelled = true;
            if (retryTimer) clearTimeout(retryTimer);
        };
    }, [token, profileRetry]);

    useEffect(() => {
        if (!isProfileOpen) return;
        const measurePing = async () => {
            const start = Date.now();
            try {
                await fetch(`${API_BASE_URL}/health`);
                setServerPing(Date.now() - start);
            } catch {
                setServerPing(-1);
            }
        };
        measurePing();
        const interval = setInterval(measurePing, 3000);
        return () => clearInterval(interval);
    }, [isProfileOpen]);

    const handleLogout = () => {
        void auth.logout();
        setIsProfileOpen(false);
        navigate('/');
    };

    const handleLogoutEverywhere = async () => {
        // The server revokes all tokens and closes the WebSocket in all tabs and on all devices.
        if (token) {
            try {
                await fetch(`${API_BASE_URL}/api/v1/auth/logout-all`, {
                    method: 'POST',
                    headers: {Authorization: `Bearer ${token}`},
                });
            } catch {
                // The network is unavailable: we perform the local sign-out anyway.
            }
        }
        handleLogout();
    };

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsProfileOpen(false);
            }
            if (championsMenuRef.current && !championsMenuRef.current.contains(event.target as Node)) {
                setIsChampionsMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const username = userProfile?.username || t('nav.guest');
    // Blitz is the headline rating in the compact navigation (as on chess.com/lichess.org);
    // the full breakdown by bullet/blitz/rapid/classical is on the profile page.
    const userRating = userProfile?.blitz_rating || 1200;
    // A provisional rating (task 17.8) gets a "?" mark while few blitz games have been played.
    const ratingProvisional = Boolean(userProfile?.provisional?.includes('blitz'));
    const ratingLabel = ratingProvisional ? `${userRating}?` : String(userRating);

    // Menu item labels are visible from the width at which the whole header fits; narrower, icons with tooltips remain.
    // The interface font is the system one, and text width depends on the player's system: on Linux (and where Inter is installed)
    // it is 9-10% wider than Segoe UI on Windows. The thresholds are taken for the wide font (the 17.11 measurement with Verdana, which
    // is still 15-25 px wider than the font in the CI build): a guest with labels needs up to 1335 px, a signed-in player without the
    // longest label ("Chess Legends") up to 1340 px, with all labels up to 1465 px.
    const navLabel = 'hidden min-[1360px]:inline';
    const legendsLabel = token && userProfile ? 'hidden min-[1500px]:inline' : navLabel;

    return (
        <div
            className={`w-full flex flex-col text-paper font-sans select-none ${
                isSingleScreenRoute ? 'min-h-dvh xl:h-dvh xl:overflow-hidden' : 'min-h-dvh'
            }`}
        >
            <header
                className="h-14 shrink-0 bg-acacia-dark border-b-2 border-amber-900/60 px-3 sm:px-5 flex items-center justify-between shadow-heavy relative z-30">
                <div className="flex items-center gap-4 2xl:gap-7">
                    {/* The name for a signed-in player appears from 720 px: at 640 px it appeared together with the player's name, and a header
                        with a long name ran out of room (on Windows 8 px, with a wide font more). */}
                    <Link to="/" className="flex items-center gap-2.5 cursor-pointer group outline-none">
                        <div
                            className="w-9 h-9 rounded-md bg-boxwood flex items-center justify-center shadow-inner border border-amber-600/40 text-acacia-dark font-bold text-xl">
                            ♞
                        </div>
                        <span
                            className={`hidden ${token && userProfile ? "min-[720px]:inline md:hidden lg:inline" : "min-[440px]:inline"} text-2xl font-extrabold tracking-wide text-boxwood-light group-hover:text-white transition`}>
                            regence
                        </span>
                    </Link>

                    <nav className="hidden md:flex items-center gap-3 2xl:gap-4 whitespace-nowrap text-[15px] font-semibold text-boxwood/90">
                        <Link
                            to="/"
                            title={t('nav.play')}
                            aria-label={t('nav.play')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname === '/' ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <Swords size={17}/> <span className={navLabel}>{t('nav.play')}</span>
                        </Link>

                        <Link
                            to="/puzzles"
                            title={t('nav.puzzles')}
                            aria-label={t('nav.puzzles')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname === '/puzzles' ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <Puzzle size={17}/> <span className={navLabel}>{t('nav.puzzles')}</span>
                        </Link>

                        {/* School (14.2): three courses are ready, so the item is back in the header (23.6). */}
                        <Link
                            to="/learn"
                            title={t('learn.title')}
                            aria-label={t('learn.title')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname.startsWith('/learn') ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <GraduationCap size={17}/> <span className={navLabel}>{t('learn.title')}</span>
                        </Link>

                        <Link
                            to="/tournaments"
                            title={t('nav.tournaments')}
                            aria-label={t('nav.tournaments')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname.startsWith('/tournaments') ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <Trophy size={17}/> <span className={navLabel}>{t('nav.tournaments')}</span>
                        </Link>

                        {/* Trainers (19.1). */}
                        <Link
                            to="/train"
                            title={t('trainers.title')}
                            aria-label={t('trainers.title')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname.startsWith('/train') ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <Dumbbell size={17}/> <span className={navLabel}>{t('trainers.title')}</span>
                        </Link>

                        <Link
                            to="/leaderboard"
                            title={t('nav.leaderboard')}
                            aria-label={t('nav.leaderboard')}
                            className={`flex items-center gap-1.5 transition ${
                                location.pathname === '/leaderboard' ? 'text-amber-300' : 'hover:text-amber-300'
                            }`}
                        >
                            <Medal size={17}/> <span className={navLabel}>{t('nav.leaderboard')}</span>
                        </Link>

                        <div className="relative" ref={championsMenuRef}>
                            <button
                                onClick={() => setIsChampionsMenuOpen(!isChampionsMenuOpen)}
                                title={t('nav.legends')}
                                aria-label={t('nav.legends')}
                                className={`flex items-center gap-1.5 transition outline-none cursor-pointer ${
                                    isChampionsMenuOpen || location.pathname.startsWith('/champions')
                                        ? 'text-amber-300'
                                        : 'hover:text-amber-300'
                                }`}
                            >
                                <Crown size={17}/> <span className={legendsLabel}>{t('nav.legends')}</span>
                                <ChevronDown
                                    size={15}
                                    className={`transition-transform ${isChampionsMenuOpen ? 'rotate-180' : ''}`}
                                />
                            </button>

                            {isChampionsMenuOpen && (
                                <div
                                    className="absolute top-full left-0 mt-3 w-80 bg-[#261C14] border-2 border-amber-900/80 rounded-lg shadow-2xl z-50 max-h-[75vh] overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-amber-900/50">
                                    {CHAMPIONS_LIST.map(champ => (
                                        <Link
                                            key={champ.id}
                                            to={`/champions/${encodeURIComponent(champ.id)}`}
                                            onClick={() => setIsChampionsMenuOpen(false)}
                                            className="flex items-center gap-3.5 px-4 py-2.5 hover:bg-black/40 transition border-b border-amber-900/30 last:border-b-0 group outline-none"
                                        >
                                            <img
                                                src={champ.img}
                                                alt={champ.name}
                                                referrerPolicy="no-referrer"
                                                className="w-11 h-11 object-cover rounded-md shadow border border-amber-900/50 group-hover:border-amber-500/60 transition shrink-0"
                                            />
                                            <div className="flex flex-col min-w-0">
                                                <span
                                                    className="font-bold text-amber-200 text-[15px] group-hover:text-white transition truncate">
                                                    {champ.name}
                                                </span>
                                                <span
                                                    className="text-xs text-boxwood/70 font-mono group-hover:text-amber-400 transition">
                                                    {t(champ.worldChampion ? 'nav.worldChampionYears' : 'nav.careerYears', {years: champ.years})}
                                                </span>
                                            </div>
                                        </Link>
                                    ))}
                                    {/* Catalogue of masters of the past (task 28.5): participants of historical tournaments. */}
                                    <Link to="/masters" onClick={() => setIsChampionsMenuOpen(false)} data-testid="nav-masters"
                                          className="flex flex-col gap-0.5 px-4 py-2.5 hover:bg-black/40 transition outline-none">
                                        <span className="font-bold text-amber-200 text-[15px]">{t('masters.title')}</span>
                                        <span className="text-xs text-boxwood/70">{t('masters.teaser')}</span>
                                    </Link>
                                </div>
                            )}
                        </div>

                    </nav>
                </div>

                <div className="flex items-center gap-1 sm:gap-3 text-boxwood-light relative" ref={dropdownRef}>
                    <LanguageSwitcher compact/>
                    {token && userProfile && <PlayerSearch/>}
                    {token && userProfile && <NotificationBell/>}
                    <Link
                        to="/leaderboard"
                        className="md:hidden p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300"
                        title={t('nav.leaderboardFull')}
                        aria-label={t('nav.leaderboardFull')}
                    >
                        <Trophy size={19}/>
                    </Link>
                    <Link
                        to="/about"
                        className="p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300"
                        title={t('nav.about')}
                        aria-label={t('nav.about')}
                    >
                        <Scale size={19}/>
                    </Link>
                    {/* For a signed-in player on a narrow screen the item is in the profile menu: there is not enough room in the header. */}
                    <button
                        type="button"
                        onClick={() => setShowReport(true)}
                        data-testid="report-problem-open"
                        className={`${token && userProfile ? 'hidden sm:block' : ''} p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300 cursor-pointer`}
                        title={t('nav.reportProblem')}
                        aria-label={t('nav.reportProblem')}
                    >
                        <Bug size={19}/>
                    </button>
                    {!(token && userProfile) && (
                        <Link
                            to="/settings"
                            className="p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300"
                            title={t('nav.settings')}
                            aria-label={t('nav.settings')}
                        >
                            <SettingsIcon size={19}/>
                        </Link>
                    )}

                    {token && userProfile ? (
                        <>
                            <div
                                onClick={() => setIsProfileOpen(!isProfileOpen)}
                                className="flex items-center gap-1.5 sm:gap-2.5 border-l border-amber-900/50 cursor-pointer hover:opacity-90 transition select-none py-1 pl-1.5 pr-1 sm:pl-3 sm:pr-2.5 rounded-md hover:bg-black/25"
                            >
                                <PlayerAvatar username={username} avatar={userProfile.avatar}
                                              className="w-8 h-8 rounded border border-amber-900/50 shadow"/>
                                <div className="flex-col items-start hidden sm:flex md:hidden lg:flex">
                                    <span className="font-bold text-sm text-amber-200 leading-tight max-w-[7rem] truncate"
                                          title={username}>{username}</span>
                                    <span
                                        className="text-xs text-amber-400 font-mono font-semibold"
                                        title={ratingProvisional ? t('nav.provisional') : undefined}>({ratingLabel})</span>
                                </div>
                                <span className="text-xs text-amber-400 ml-0.5">▼</span>
                            </div>

                            {isProfileOpen && (
                                <div
                                    className="absolute right-0 top-12 w-64 bg-[#261C14] border-2 border-amber-900/80 rounded-lg shadow-2xl py-2 z-50 text-boxwood-light">
                                    <div className="px-4 py-2.5 border-b border-amber-900/40 flex items-center gap-3">
                                        <PlayerAvatar username={username} avatar={userProfile.avatar}
                                                      className="w-10 h-10 rounded border border-amber-900/50 shadow"/>
                                        <div>
                                            <div className="font-bold text-base text-amber-200">{username}</div>
                                            <div
                                                className="text-xs text-amber-400 font-mono">{t('nav.rating', {rating: ratingLabel})}</div>
                                            <div className="text-xs text-emerald-400 flex items-center gap-1.5 mt-0.5">
                                                <span
                                                    className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
                                                {t('nav.online')}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="py-1 border-b border-amber-900/40 text-sm font-medium">
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate(`/profile/${encodeURIComponent(username)}`);
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <User size={16} className="text-amber-500"/> {t('nav.profile')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/puzzles');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Puzzle size={16} className="text-amber-500"/> {t('nav.puzzles')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/import');
                                            }}
                                            data-testid="nav-import"
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <CloudDownload size={16} className="text-amber-500"/> {t('nav.importGames')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/learn');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <GraduationCap size={16} className="text-amber-500"/> {t('learn.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/watch');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Eye size={16} className="text-amber-500"/> {t('watch.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/tools');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Wrench size={16} className="text-amber-500"/> {t('tools.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/teams');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Shield size={16} className="text-amber-500"/> {t('teams.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/feed');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Newspaper size={16} className="text-amber-500"/> {t('feed.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/messages');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <MessageSquare size={16} className="text-amber-500"/> {t('dm.title')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/study');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Presentation size={16} className="text-amber-500"/> {t('study.title')}
                                        </button>
                                        {showModeration && (
                                            <button
                                                onClick={() => {
                                                    setIsProfileOpen(false);
                                                    navigate('/moderation');
                                                }}
                                                className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                            >
                                                <Gavel size={16} className="text-amber-500"/> {t('moderation.title')}
                                            </button>
                                        )}
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/tournaments');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Trophy size={16} className="text-amber-500"/> {t('nav.tournaments')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/leaderboard');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Trophy size={16} className="text-amber-500"/> {t('nav.leaderboardFull')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                navigate('/settings');
                                            }}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <SettingsIcon size={16} className="text-amber-500"/> {t('nav.settings')}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsProfileOpen(false);
                                                setShowReport(true);
                                            }}
                                            data-testid="report-problem-menu"
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-black/30 transition text-boxwood/90 hover:text-amber-300 cursor-pointer"
                                        >
                                            <Bug size={16} className="text-amber-500"/> {t('nav.reportProblem')}
                                        </button>
                                        <button
                                            onClick={handleLogout}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-red-950/40 transition text-red-300 hover:text-red-200 cursor-pointer"
                                        >
                                            <LogOut size={16} className="text-red-400"/> {t('nav.logout')}
                                        </button>
                                        <button
                                            onClick={handleLogoutEverywhere}
                                            title={t('nav.logoutEverywhereHint')}
                                            className="w-full px-4 py-2 text-left flex items-center gap-3 hover:bg-red-950/40 transition text-red-300/80 hover:text-red-200 cursor-pointer text-sm"
                                        >
                                            <LogOut size={16} className="text-red-500"/> {t('nav.logoutEverywhere')}
                                        </button>
                                    </div>

                                    <div
                                        className="px-4 py-2 text-xs font-mono text-boxwood/70 flex justify-between items-center bg-black/20">
                                        <span>{t('nav.ping', {
                                            value: serverPing === null ? '…'
                                                : serverPing === -1 ? t('nav.pingError') : t('nav.pingMs', {ms: serverPing}),
                                        })}</span>
                                        <span className="text-emerald-400 font-bold">{t('nav.server')}</span>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <button
                            onClick={() => setShowAuthModal(true)}
                            aria-label={t('nav.login')}
                            className="flex items-center gap-2 px-2.5 sm:px-4 py-1.5 bg-boxwood text-acacia-dark font-bold text-sm rounded-md hover:bg-boxwood-light transition shadow border border-amber-600/40 cursor-pointer"
                        >
                            {/* On a narrow screen only the icon: otherwise the header is wider than the screen. */}
                            <LogIn size={16}/> <span className="hidden sm:inline">{t('nav.login')}</span>
                        </button>
                    )}
                </div>
            </header>

            <main
                className={`flex-1 flex justify-center w-full ${
                    isSingleScreenRoute
                        ? 'items-stretch p-2 sm:p-3 xl:overflow-hidden'
                        : 'items-start p-4 sm:p-6 overflow-y-auto'
                }`}
            >
                <PageErrorBoundary resetKey={location.pathname}>
                {!sessionChecked ? (
                    // While it is unknown whether the player is signed in: the page place is empty (a fraction of a second), the header is already in place.
                    <div className="flex-1" data-testid="session-restoring" aria-busy="true"/>
                ) : (
                <Routes>
                    <Route path="/" element={<Chessboard key={token ? token : 'guest'}/>}/>
                    <Route path="/challenge/:inviteCode" element={<Chessboard key={token ? token : 'guest'}/>}/>
                    <Route path="/leaderboard" element={<Leaderboard/>}/>
                    <Route path="/puzzles" element={<PuzzlesPage/>}/>
                    <Route path="/learn" element={<LearnPage/>}/>
                        <Route path="/learn/course" element={<SupercoursePage/>}/>
                        <Route path="/learn/basics" element={<BasicsPage/>}/>
                        <Route path="/learn/basics/:sectionId" element={<BasicsSectionPage/>}/>
                        <Route path="/learn/mates" element={<MateCoursePage/>}/>
                        <Route path="/learn/mates/exam" element={<MateExamPage/>}/>
                        <Route path="/learn/mates/:theme" element={<MateConstructionPage/>}/>
                        <Route path="/learn/classics" element={<ClassicsPage/>}/>
                        <Route path="/learn/classics/:gameId" element={<ClassicGamePage/>}/>
                        <Route path="/learn/endgames" element={<EndgamesPage/>}/>
                        <Route path="/learn/endgames/:exerciseId" element={<EndgameTrainerPage/>}/>
                        <Route path="/tools" element={<ToolsPage/>}/>
                        <Route path="/watch" element={<WatchPage/>}/>
                        <Route path="/arenas" element={<ArenasPage/>}/>
                        <Route path="/arenas/:arenaId" element={<ArenaPage/>}/>
                        <Route path="/conferences" element={<ConferencesPage/>}/>
                        <Route path="/teams" element={<TeamsPage/>}/>
                        <Route path="/study" element={<StudyLobby/>}/>
                        <Route path="/study/:code" element={<StudyRoomPage/>}/>
                        <Route path="/moderation" element={<ModerationPage/>}/>
                        <Route path="/messages" element={<MessagesPage/>}/>
                        <Route path="/messages/:username" element={<MessagesPage/>}/>
                        <Route path="/feed" element={<FeedPage/>}/>
                        <Route path="/feed/post/:postId" element={<PostPage/>}/>
                        <Route path="/rules" element={<CommunityRulesPage/>}/>
                        <Route path="/privacy" element={<PrivacyPage/>}/>
                        {/* Showcase of shared design components: not in the menu (docs/design-system.md). */}
                        <Route path="/design" element={<DesignGallery/>}/>
                        <Route path="/train" element={<TrainersPage/>}/>
                        <Route path="/train/games" element={<MiniGamesPage/>}/>
                        <Route path="/play/960" element={<Chess960Page/>}/>
                        <Route path="/play/960/live" element={<Chess960LiveGame/>}/>
                        <Route path="/workout" element={<WorkoutPage/>}/>
                        <Route path="/exam" element={<ExamPage/>}/>
                        <Route path="/programs" element={<ProgramsPage/>}/>
                        <Route path="/programs/:programId" element={<ProgramPage/>}/>
                        <Route path="/repertoire" element={<RepertoireListPage/>}/>
                        <Route path="/repertoire/:repertoireId" element={<RepertoireEditorPage/>}/>
                        <Route path="/repertoire/:repertoireId/drill" element={<RepertoireDrillPage/>}/>
                        <Route path="/train/games/:gameId" element={<MiniGamePage/>}/>
                        <Route path="/train/games/room/:code" element={<MiniGameRoomPage/>}/>
                        <Route path="/train/:trainerId" element={<TrainerPage/>}/>
                        <Route path="/guess" element={<GuessPage/>}/>
                        <Route path="/guess/:positionId" element={<GuessPage/>}/>
                    <Route path="/learn/:lessonId" element={<LessonPage/>}/>
                    <Route path="/tournaments" element={<TournamentsPage/>}/>
                    <Route path="/tournaments/:tournamentId" element={<TournamentView/>}/>
                    <Route path="/time-machine" element={<TimeMachinePage/>}/>
                    <Route path="/masters" element={<MastersPage/>}/>
                    <Route path="/profile/:targetUsername" element={<Profile/>}/>
                    <Route path="/game/:gameId" element={<GameViewer/>}/>
                    <Route path="/import" element={<ImportPage/>}/>
                    <Route path="/import/game/:gameId" element={<GameViewer key="imported" imported/>}/>
                    <Route path="/library" element={<LibraryPage/>}/>
                    <Route path="/library/game/:gameId" element={<GameViewer key="library" library/>}/>
                    <Route path="/champions/:championId" element={<ChampionGames/>}/>
                    <Route path="/about" element={<About/>}/>
                    <Route path="/transparency" element={<TransparencyPage username={username}/>}/>
                    <Route path="/verify-email" element={<VerifyEmailPage/>}/>
                    <Route path="/reset-password" element={<ResetPasswordPage/>}/>
                    <Route
                        path="/settings"
                        element={
                            <Settings
                                token={token}
                                username={userProfile?.username ?? null}
                                onTokenChange={setToken}
                                onLogoutEverywhere={handleLogoutEverywhere}
                                onAccountDeleted={handleLogout}
                            />
                        }
                    />
                </Routes>
                )}
                </PageErrorBoundary>
            </main>
            <TranslationHelper/>
            {showReport && <ReportProblem onClose={() => setShowReport(false)}/>}

            {showAuthModal && (
                <AuthModal
                    onSuccess={(newToken) => {
                        setToken(newToken);
                        setShowAuthModal(false);
                    }}
                    onClose={() => setShowAuthModal(false)}
                    onFirstGame={(rating) => navigate('/', {state: {firstGame: {rating}}})}
                    onBasics={() => navigate('/learn/basics')}
                    inviteOnly={siteConfig.inviteOnly}
                    inviteCode={inviteCode}
                />
            )}
        </div>
    );
}