// "Must-know positions" of the endgame (task 27.9): three tiers from the exercises of trainer 14.4 (content/endgames.json),
// each verified by endgame tablebases. The "mastered" mark is a completed exercise (record endgame-<id>).
// The tiers sit in the Big course as modules E2.4, E3.5 and E5.3.

export const MUST_KNOW: readonly (readonly string[])[] = [
    // I - level 2: elementary mates, king and pawn, opposition, rook pawn, queen versus pawn.
    ['kq_center', 'kr_edge', 'square_win', 'kp_key_square', 'kp_sixth', 'kp_opposition_def', 'rook_pawn_def', 'q_vs_pawn'],
    // II - level 3: Lucena, Philidor, rook behind a passed pawn, "wrong" bishop, queen versus pawn on the c- and a-file.
    ['lucena', 'philidor', 'rook_behind_pawn', 'rook_vs_pawn', 'wrong_bishop', 'two_pawns', 'q_vs_c_pawn_def',
        'q_vs_a_pawn_def', 'bb_center'],
    // III - level 5: bishop and knight, queen versus rook and knight, defences against a rook, opposite-coloured bishops, Vancura.
    ['bn_corner', 'q_vs_rook', 'q_vs_knight', 'rook_vs_bishop_def', 'rook_vs_knight_def', 'opposite_bishops_def', 'vancura'],
];

// Studies (27.9) - only by long-dead composers, each with an entry in ATTRIBUTION.md; course module E4.4.
export const STUDIES: readonly string[] = ['study_saavedra', 'study_reti'];
