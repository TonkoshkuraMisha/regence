// Звуковой движок (soundEngine.ts): чтение настроек из localStorage при создании, выбор набора звуков, отключение
// звука, синтез каждого события и фанфар на поддельном AudioContext (проверяется, что звук строится, а при выключенном
// звуке и без Web Audio — тишина без ошибок), resolveMoveSound для пустой записи.

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

describe('настройки звука', () => {
    it('читает выключенный звук и сохранённый набор из localStorage, неизвестный набор игнорирует', async () => {
        localStorage.setItem('regence_sound_muted', 'true');
        localStorage.setItem('regence_sound_set', 'marble');
        const {soundEngine} = await freshEngine();
        expect(soundEngine.isMuted()).toBe(true);
        expect(soundEngine.getSoundSet()).toBe('marble');

        localStorage.setItem('regence_sound_set', 'устарел');
        const again = await freshEngine();
        expect(again.soundEngine.getSoundSet()).toBe('wood');
        expect(again.isSoundSetId('soft')).toBe(true);
        expect(again.isSoundSetId('nope')).toBe(false);
        expect(again.isSoundSetId(5)).toBe(false);
    });

    it('смена набора и выключение пишутся в localStorage; сбой хранилища не ломает смену набора', async () => {
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

    it('шах включается и выключается флагом', async () => {
        const {checkSoundsEnabled, setCheckSounds, resolveMoveSound} = await freshEngine();
        expect(checkSoundsEnabled()).toBe(false);
        setCheckSounds(true);
        expect(checkSoundsEnabled()).toBe(true);
        expect(resolveMoveSound(null)).toBe('move');
        expect(resolveMoveSound('')).toBe('move');
    });
});

describe('синтез звуков', () => {
    it.each(['wood', 'marble', 'soft', 'bright'] as const)('набор %s: каждое событие строит звук', async (set) => {
        const {soundEngine} = await freshEngine();
        soundEngine.setSoundSet(set);
        for (const event of EVENTS) soundEngine.play(event);
        expect(created.oscillators).toBeGreaterThan(EVENTS.length);
        expect(created.sources).toBeGreaterThan(0);
        expect(FakeAudioContext.resume).toHaveBeenCalled();
    });

    it('фанфары: у победителя, серебра и бронзы разные мелодии', async () => {
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

    it('при выключенном звуке ничего не строится', async () => {
        const {soundEngine} = await freshEngine();
        soundEngine.setMuted(true);
        soundEngine.play('move');
        soundEngine.playFanfare(1);
        expect(created.oscillators + created.sources).toBe(0);
    });

    it('без Web Audio звук молчит без ошибок', async () => {
        (window as unknown as {AudioContext: unknown}).AudioContext = undefined;
        vi.stubGlobal('AudioContext', undefined);
        const {soundEngine} = await freshEngine();
        expect(() => {
            soundEngine.play('victory');
            soundEngine.play('move');
        }).not.toThrow();
    });

    it('контекст создаётся один раз и используется повторно', async () => {
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
