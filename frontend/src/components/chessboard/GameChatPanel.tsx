// --- FILE: frontend/src/components/chessboard/GameChatPanel.tsx ---
// Game chat: message feed, quick replies and an input field; visible in a game against a human and when spectating. Messages
// go over the WebSocket (the chat_message action and event, the useGameSocket hook), the server limits the rate. Only the
// players of the game may write: a spectator reads the chat, and the server would reject their message (code chat_forbidden). A quick
// reply is sent as a code and shown to everyone in their own language. A typed message from another player can be
// reported: POST /moderation/reports (services/moderation.ts); the last 50 messages are kept in memory.

import {useState} from 'react';
import {Flag, MessageSquare, Send} from 'lucide-react';
import {moderationApi} from '../../services/moderation';
import {useI18n} from '../../i18n';
import {QUICK_CHAT_PRESETS} from './types';
import {useKidMode} from '../../services/kidMode';
import {CHAT_TEXT_MAX} from './gameChat';
import type {ChatMessageItem, ChatPresetId} from './types';

export interface GameChatPanelProps {
    messages: ChatMessageItem[];
    chatInput: string;
    onChatInputChange: (value: string) => void;
    onSendMessage: () => void;
    onSendPreset: (preset: ChatPresetId) => void;
    /** The "leave spectating" button is visible only to a spectator, not to the game's participants. */
    isSpectator: boolean;
    onLeaveSpectate: () => void;
    /** Own name and the game: for reporting an opponent's message (task 17.4). */
    myName?: string;
    gameId?: number | null;
}

/** Game chat: message feed, quick replies and an input field. Visible only in PvP/spectating. */
export function GameChatPanel({
    messages, chatInput, onChatInputChange, onSendMessage, onSendPreset, isSpectator, onLeaveSpectate, myName, gameId,
}: GameChatPanelProps) {
    const {t} = useI18n();
    // Kid mode (task 23.1): only quick phrases - free text is neither shown nor typed (the server refuses it in such a game).
    const kidMode = useKidMode();
    const shown = kidMode ? messages.filter((msg) => msg.preset) : messages;
    // Numbers of messages that have already been reported: a mark instead of the flag (also when sending failed).
    const [reported, setReported] = useState<Set<number>>(new Set());
    const report = (index: number, sender: string, text: string) => {
        moderationApi.report({target: sender, kind: 'message', reason: 'abuse', message_text: text, game_id: gameId ?? null})
            .catch(() => undefined)
            .finally(() => setReported((s) => new Set(s).add(index)));
    };
    return (
        <div className="bg-acacia-dark p-2 rounded-md border border-amber-900/50 flex flex-col gap-1.5 shrink-0">
            <div className="flex items-center justify-between text-xs uppercase tracking-wider text-amber-400 font-bold">
                <span className="flex items-center gap-1.5">
                    <MessageSquare size={13}/> {t('chat.title')}
                </span>
                {isSpectator && (
                    <button
                        type="button"
                        onClick={onLeaveSpectate}
                        className="text-rose-300 hover:text-rose-200 underline text-xs font-sans cursor-pointer"
                    >
                        {t('chat.leaveSpectating')}
                    </button>
                )}
            </div>

            <div
                className="h-16 overflow-y-auto bg-black/40 rounded p-2 text-xs space-y-1 font-sans border border-amber-950/50 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:bg-amber-900/50">
                {shown.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-xs text-boxwood/45 italic">
                        {t(isSpectator ? 'chat.emptySpectator' : 'chat.emptyPlayer')}
                    </div>
                ) : (
                    shown.map((msg, i) => (
                        <div key={i} className="leading-snug wrap-break-word">
                            <span className="font-bold text-amber-300 mr-1.5">{msg.sender}:</span>
                            <span className="text-boxwood-light">{msg.preset ? t(`chat.presets.${msg.preset}`) : msg.text}</span>
                            {!msg.preset && msg.text && myName && msg.sender !== myName && (
                                reported.has(i)
                                    ? <span className="ml-1 text-boxwood/50">{t('moderation.reportSent')}</span>
                                    : <button type="button" onClick={() => report(i, msg.sender, msg.text)} aria-label={t('moderation.reportMessage')}
                                              data-testid={`report-message-${i}`} className="ml-1 text-rose-300/70 hover:text-rose-300 align-middle">
                                        <Flag size={10} className="inline"/>
                                    </button>
                            )}
                        </div>
                    ))
                )}
            </div>

            {/* Only the players may write in the game chat (the server rejects spectators' messages). */}
            {isSpectator && (
                <div className="text-xs text-boxwood/60 italic">{t('chat.spectatorReadOnly')}</div>
            )}

            {!isSpectator && <div className="flex flex-wrap gap-1">
                {QUICK_CHAT_PRESETS.map((preset) => (
                    <button
                        key={preset}
                        type="button"
                        onClick={() => onSendPreset(preset)}
                        className="px-2 py-0.5 rounded bg-black/40 hover:bg-amber-900/50 border border-amber-800/40 text-xs text-amber-200 transition cursor-pointer"
                    >
                        {t(`chat.presets.${preset}`)}
                    </button>
                ))}
            </div>}

            {!isSpectator && kidMode && (
                <div className="text-xs text-boxwood/60 italic" data-testid="chat-kid-mode">{t('chat.kidModeNote')}</div>
            )}

            {!isSpectator && !kidMode && <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onSendMessage();
                }}
                className="flex gap-1.5"
            >
                <input
                    type="text"
                    maxLength={CHAT_TEXT_MAX}
                    value={chatInput}
                    onChange={(e) => onChatInputChange(e.target.value)}
                    placeholder={t('chat.placeholder')}
                    className="flex-1 bg-black/50 border border-amber-800/50 rounded px-2.5 py-1 text-xs text-amber-100 outline-none focus:border-amber-500 font-sans"
                />
                <button
                    type="submit"
                    className="px-3 py-1 bg-amber-700 hover:bg-amber-600 text-amber-100 rounded text-xs font-bold flex items-center justify-center transition cursor-pointer"
                    title={t('chat.send')}
                    aria-label={t('chat.send')}
                >
                    <Send size={13}/>
                </button>
            </form>}
        </div>
    );
}
