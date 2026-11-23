// The sound engine (soundEngine.ts): reading settings from localStorage on creation, choosing a sound set, turning the
// sound off, synthesizing each event and fanfares on a fake AudioContext (checking that the sound is built, and that with the sound off
// and without Web Audio there is silence without errors), resolveMoveSound for an empty record.

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {SoundEventType} from '../soundEngine';

const EVENTS: SoundEventType[] = ['move', 'capture', 'check', 'castle', 'promote', 'premove', 'illegal', 'start',
    'victory', 'defeat', 'draw', 'offer', 'decline', 'chat', 'low_time'];

function node() {
    const param = {setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn()};
    return {
        connect: vi.fn(), start: vi.fn(), stop: vi.fn(), type: '', buffer: null as unknown,
        frequency: param, gain: param, Q: param,
        getChannelData: () => new Float32Array(4096),
    };
}

const created = {oscillators: 0, sources: 0};

class FakeAudioContext {
    static resume = vi.fn(async () => undefined);
    currentTime = 0;
    sampleRate = 8000;
    destination = {};
    state = 'suspended';
    resume = FakeAudioContext.resume;
    createOscillator() {
        created.oscillators += 1;
        return node();
    }
    createGain() {
        return node();
    }
    createBiquadFilter() {
        return node();
    }
    createBuffer() {
        return node();
    }
    createBufferSource() {
        created.sources += 1;
        return node();
    }
}

async function freshEngine() {
    vi.resetModules();
    return import('../soundEngine');
}

beforeEach(() => {
    localStorage.clear();
    created.oscillators = 0;
    created.sources = 0;
    vi.stubGlobal('AudioContext', FakeAudioContext);
    (window as unknown as {AudioContext: unknown}).AudioContext = FakeAudioContext;
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('sound settings', () => {
    it('reads the sound off and the saved set from localStorage, ignores an unknown set', async () => {
        localStorage.setItem('regence_sound_muted', 'true');
        localStorage.setItem('regence_sound_set', 'marble');
        const {soundEngine} = await freshEngine();
        expect(soundEngine.isMuted()).toBe(true);
        expect(soundEngine.getSoundSet()).toBe('marble');

        localStorage.setItem('regence_sound_set', 'stale');
        const again = await freshEngine();
        expect(again.soundEngine.getSoundSet()).toBe('wood');
        expect(again.isSoundSetId('soft')).toBe(true);
        expect(again.isSoundSetId('nope')).toBe(false);
        expect(again.isSoundSetId(5)).toBe(false);
    });

    it('changing the set and turning off are written to localStorage; a storage failure does not break changing the set', async () => {
        const {soundEngine} = await freshEngine();
        soundEngine.setSoundSet('bright');
        expect(localStorage.getItem('regence_sound_set')).toBe('bright');
        soundEngine.setMuted(true);
        expect(localStorage.getItem('regence_sound_muted')).toBe('true');
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
            throw new Error('quota');
        });
        expect(() => soundEngine.setSoundSet('soft')).not.toThrow();
        expect(soundEngine.getSoundSet()).toBe('soft');
    });

    it('check is turned on and off by a flag', async () => {
        const {checkSoundsEnabled, setCheckSounds, resolveMoveSound} = await freshEngine();
        expect(checkSoundsEnabled()).toBe(false);
        setCheckSounds(true);
        expect(checkSoundsEnabled()).toBe(true);
        expect(resolveMoveSound(null)).toBe('move');
        expect(resolveMoveSound('')).toBe('move');
    });
});

describe('sound synthesis', () => {
    it.each(['wood', 'marble', 'soft', 'bright'] as const)('set %s: every event builds a sound', async (set) => {
        const {soundEngine} = await freshEngine();
        soundEngine.setSoundSet(set);
        for (const event of EVENTS) soundEngine.play(event);
        expect(created.oscillators).toBeGreaterThan(EVENTS.length);
        expect(created.sources).toBeGreaterThan(0);
        expect(FakeAudioContext.resume).toHaveBeenCalled();
    });

    it('fanfares: the winner, silver and bronze have different melodies', async () => {
        const {soundEngine} = await freshEngine();
        const counts: number[] = [];
        for (const place of [1, 2, 3]) {
            created.oscillators = 0;
            soundEngine.playFanfare(place);
            counts.push(created.oscillators);
        }
        expect(counts[0]).toBeGreaterThan(counts[1]);
        expect(counts[1]).toBeGreaterThan(counts[2]);
        expect(counts[2]).toBeGreaterThan(0);
    });

    it('with the sound off nothing is built', async () => {
        const {soundEngine} = await freshEngine();
        soundEngine.setMuted(true);
        soundEngine.play('move');
        soundEngine.playFanfare(1);
        expect(created.oscillators + created.sources).toBe(0);
    });

    it('without Web Audio the sound is silent without errors', async () => {
        (window as unknown as {AudioContext: unknown}).AudioContext = undefined;
        vi.stubGlobal('AudioContext', undefined);
        const {soundEngine} = await freshEngine();
        expect(() => {
            soundEngine.play('victory');
            soundEngine.play('move');
        }).not.toThrow();
    });

    it('the context is created once', async () => {
        const ctor = vi.fn(function (this: unknown) {
            return new FakeAudioContext();
        });
        (window as unknown as {AudioContext: unknown}).AudioContext = ctor;
        const {soundEngine} = await freshEngine();
        soundEngine.play('chat');
        soundEngine.play('chat');
        expect(ctor).toHaveBeenCalledTimes(1);
    });
});
