// --- FILE: frontend/src/i18n/messages/glossary.ts ---
// One glossary of chess terms in two languages (task 17.7). Rule: a term in the catalogs is written as here, not as one
// of the variants in `avoid` (case-insensitive regular expressions matched from the start of a word). Test:
// i18n/__tests__/glossary.test.ts; it lives in messages/ because it is text too. When adding a term, first check that it is not here yet.

import type {Language} from '../core';

export interface GlossaryTerm {
    id: string;
    en: string;
    uk: string;
    /** Wrong or undesirable spellings per language. */
    avoid?: Partial<Record<Language, string[]>>;
}

export const GLOSSARY: GlossaryTerm[] = [
    {id: 'king', en: 'king', uk: 'король'},
    {
        id: 'queen', en: 'queen', uk: 'ферзь',
        // The colloquial word for the queen is not accepted in Ukrainian; the 'king's flank' phrase is a legitimate term and is not affected.
        avoid: {uk: ['королев(а|у|ою|и|і)(?!\\p{L})']},
    },
    {id: 'rook', en: 'rook', uk: 'тура', avoid: {uk: ['ладд(я|і|ю|ею)'], en: ['castle piece']}},
    {id: 'bishop', en: 'bishop', uk: 'слон', avoid: {uk: ['офіцер']}},
    {id: 'knight', en: 'knight', uk: 'кінь', avoid: {en: ['horse']}},
    {id: 'pawn', en: 'pawn', uk: 'пішак', avoid: {uk: ['пішк(а|у|ою|и|і)(?!\\p{L})', 'пєшк']}},
    {id: 'castling', en: 'castling', uk: 'рокіровка'},
    {
        id: 'en_passant', en: 'en passant', uk: 'взяття на проході',
        avoid: {en: ['en-passant', 'enpassant', 'en passent']},
    },
    {id: 'promotion', en: 'promotion', uk: 'перетворення', avoid: {uk: ['промоці']}},
    {id: 'check', en: 'check', uk: 'шах'},
    {id: 'checkmate', en: 'checkmate', uk: 'мат', avoid: {en: ['check-mate', 'check mate']}},
    {id: 'stalemate', en: 'stalemate', uk: 'пат', avoid: {en: ['stale-mate', 'stale mate']}},
    {id: 'zugzwang', en: 'zugzwang', uk: 'цугцванг', avoid: {uk: ['цугцвангу?ом'], en: ['zugswang']}},
    {id: 'opening', en: 'opening', uk: 'дебют'},
    {id: 'middlegame', en: 'middlegame', uk: 'мітельшпіль', avoid: {uk: ['міттельшп'], en: ['middle game', 'middle-game']}},
    {id: 'endgame', en: 'endgame', uk: 'ендшпіль', avoid: {uk: ['ендшпил'], en: ['end game', 'end-game']}},
    {id: 'fork', en: 'fork', uk: 'вилка'},
    {id: 'pin', en: 'pin', uk: 'зв’язка', avoid: {uk: ["зв'язк", 'звязк']}},
    {id: 'skewer', en: 'skewer', uk: 'лінійний удар'},
    {id: 'blunder', en: 'blunder', uk: 'груба помилка'},
];
