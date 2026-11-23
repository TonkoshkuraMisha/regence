// --- FILE: frontend/src/test/newGame.ts ---
// Test helpers for the game hall: the "New game" window (owner scheme 18.11) at the "Start" step. The choice of an opponent
// is remembered in localStorage (regence_new_game_who), so the window opens straight at the start — like for a player who
// has already started such a game. The first walk through the steps is checked by a separate test in Chessboard.test.tsx.

import {fireEvent, screen} from '@testing-library/react';

async function openNewGame(who: 'human' | 'bot') {
    localStorage.setItem('regence_new_game_who', who);
    fireEvent.click(await screen.findByTestId('new-game-open'));
}

/** A window at the step with bots: historical masters, the workshop, the ladder. */
export const openBots = () => openNewGame('bot');

/** A window at the step with a person: the game type, searching for an opponent, challenging a friend. */
export const openHuman = () => openNewGame('human');
