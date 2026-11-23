// A separate theme for game review (task 18.3): without a record — as in the game; a record does not touch the game theme.

import {afterEach, describe, expect, it} from 'vitest';
import {
    getAnalysisBoardThemeKey, getAnalysisPieceSetKey, getSavedBoardThemeKey, getSavedPieceSetKey, hasAnalysisAppearance,
    setAnalysisAppearance,
} from '../boardAppearance';

afterEach(() => localStorage.clear());

describe('review theme', () => {
    it('by default it matches the game theme', () => {
        localStorage.setItem('regence_board_theme', 'oak');
        localStorage.setItem('regence_piece_set', 'cburnett');
        expect(hasAnalysisAppearance()).toBe(false);
        expect(getAnalysisBoardThemeKey()).toBe('oak');
        expect(getAnalysisPieceSetKey()).toBe('cburnett');
    });

    it('its own review theme does not change the game theme; reset returns "as in the game"', () => {
        localStorage.setItem('regence_board_theme', 'oak');
        setAnalysisAppearance('marble', 'celtic');
        expect(hasAnalysisAppearance()).toBe(true);
        expect([getAnalysisBoardThemeKey(), getAnalysisPieceSetKey()]).toEqual(['marble', 'celtic']);
        expect([getSavedBoardThemeKey(), getSavedPieceSetKey()]).toEqual(['oak', 'merida']);
        setAnalysisAppearance(null, null);
        expect(getAnalysisBoardThemeKey()).toBe('oak');
    });

    it('an unknown board in storage is ignored', () => {
        localStorage.setItem('regence_analysis_board_theme', 'gone');
        localStorage.setItem('regence_analysis_piece_set', 'celtic');
        expect(hasAnalysisAppearance()).toBe(false);
        expect(getAnalysisPieceSetKey()).toBe('merida');
    });
});
