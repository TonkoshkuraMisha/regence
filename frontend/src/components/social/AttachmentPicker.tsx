// --- FILE: frontend/src/components/social/AttachmentPicker.tsx ---
// Attachment choice for a feed post (FeedPage.tsx, Composer) and a direct message (MessagesPage.tsx): the attachment kind
// and a link or identifier. A pasted link to a game, puzzle, lesson etc. is recognised automatically
// (detectAttachment from services/messages.ts), and the kind is chosen by it. An achievement is not chosen manually: it arrives
// as a ready draft from the "share" button in the profile and is shown with a label. No network needed: the attachment goes to the
// server together with the text, and src/services/attachments.py validates it.

import {X} from 'lucide-react';
import {useI18n} from '../../i18n';
import {detectAttachment} from '../../services/messages';
import type {AttachmentKind} from '../../services/messages';

/** Attachment draft: the kind and a link or identifier (ref); it also comes from location.state.attach. */
export interface AttachmentDraft {
    kind: AttachmentKind;
    ref: string;
}

/** Attachment kinds chosen manually; an achievement is added only by the "share" button in the profile. */
export const ATTACHMENT_KINDS: AttachmentKind[] = ['game', 'position', 'puzzle', 'lesson', 'tournament', 'library'];

/** Maximum length of the link field: a whole page address from which detectAttachment extracts ref (on the server ref <= 100). */
const REF_INPUT_MAX = 200;

/**
 * Attachment choice row. testId is the section's data-testid prefix ("feed" or "dm"): for the ...-attach, ...-attach-kind,
 * ...-attach-ref fields. onRemove is the cross: the attachment is removed, the row closes.
 */
export function AttachmentPicker({draft, onChange, onRemove, testId}: {
    draft: AttachmentDraft | null;
    onChange: (draft: AttachmentDraft) => void;
    onRemove: () => void;
    testId: string;
}) {
    const {t} = useI18n();
    return (
        <div className="flex flex-wrap items-center gap-1.5 text-sm" data-testid={`${testId}-attach`}>
            {draft?.kind === 'achievement' ? (
                <span className="px-1.5 py-1">{t('dm.kinds.achievement')}</span>
            ) : (
                <>
                    <select value={draft?.kind ?? 'game'} className="bg-black/40 rounded px-1.5 py-1" data-testid={`${testId}-attach-kind`}
                            onChange={(e) => onChange({kind: e.target.value as AttachmentKind, ref: draft?.ref ?? ''})}>
                        {ATTACHMENT_KINDS.map((k) => <option key={k} value={k}>{t(`dm.kinds.${k}`)}</option>)}
                    </select>
                    <input value={draft?.ref ?? ''} maxLength={REF_INPUT_MAX} placeholder={t('dm.attachHint')}
                           data-testid={`${testId}-attach-ref`} className="flex-1 min-w-0 bg-black/40 rounded px-2 py-1"
                           onChange={(e) => {
                               const found = detectAttachment(e.target.value);
                               onChange(found ? {kind: found.kind, ref: found.ref} : {kind: draft?.kind ?? 'game', ref: e.target.value});
                           }}/>
                </>
            )}
            <button type="button" onClick={onRemove} aria-label={t('dm.removeAttachment')} title={t('dm.removeAttachment')}
                    className="p-1 text-boxwood/70">
                <X size={14}/>
            </button>
        </div>
    );
}
