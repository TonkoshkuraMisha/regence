// --- FILE: frontend/src/components/trainers/trainerGame.ts ---
// Shared by level-based trainer games (BlindGames, BoardPuzzleGames, CalcGames, MemoryGames, VisionGames): what
// a game receives from the trainers page (TrainersPage.tsx) and loading of the classic games that tasks are built from.
// Games come from content/classics.ts (loadAllClassics): a separate build chunk loaded on demand, not over the network from the API.

import {useEffect, useState} from 'react';
import {loadAllClassics} from '../../content/classics';
import type {ClassicGame} from '../../content/classics';

/**
 * Trainer game props: level (task difficulty), seed (the same seed gives the same attempt - tasks
 * are deterministic) and onFinish - the attempt result: score and mistake count, saved by the trainers page.
 */
export interface TrainerGameProps {
    level: number;
    seed: number;
    onFinish: (score: number, mistakes: number) => void;
}

/** Classic games used for tasks; null - still loading, empty list - loading failed. */
export function useClassics(): ClassicGame[] | null {
    const [games, setGames] = useState<ClassicGame[] | null>(null);
    useEffect(() => {
        let alive = true;
        loadAllClassics().then((list) => alive && setGames(list)).catch(() => alive && setGames([]));
        return () => {
            alive = false;
        };
    }, []);
    return games;
}
