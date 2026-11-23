// --- FILE: frontend/src/services/soundEngine.ts ---
// Interface sounds. All sounds are synthesized in the browser (Web Audio) — the project has no ready-made recordings; sound sets
// (SOUND_SETS) are synthesis profiles. Which sound a move gets is determined by its notation (resolveMoveSound); the check sound is
// only in learning sections (isLearningPath), in games — the ordinary move sound.
// Settings are stored only in the browser (localStorage): regence_sound_muted — sound off, regence_sound_set —
// the selected set. They are not sent to the server.

/** Interface events that have a sound: moves, game signals (start, result, offer, chat) and warnings. */
export type SoundEventType =
    | 'move'
    | 'capture'
    | 'check'
    | 'castle'
    | 'promote'
    | 'premove'
    | 'illegal'
    | 'start'
    | 'victory'
    | 'defeat'
    | 'draw'
    | 'offer'
    | 'decline'
    | 'chat'
    | 'low_time';

const MUTE_STORAGE_KEY = 'regence_sound_muted';
const SOUND_SET_STORAGE_KEY = 'regence_sound_set';

/**
 * Sound sets (task 18.3) — synthesis profiles, not recordings: pitch and volume of the thud, pitch and timbre of the signals.
 * Warning signals (illegal move, low time) do not change timbre — they must be recognizable in any set.
 */
export interface SoundSet {
    /** Multiplier of the piece-thud pitch (center frequency of the noise filter). */
    knock: number;
    /** Multiplier of the thud and melodic signal volume. */
    volume: number;
    /** Multiplier of the melodic signal pitch (sine and triangle). */
    pitch: number;
    /** Waveform of melodic signals; null — each signal has its own, as set in play(). */
    wave: OscillatorType | null;
}

/** Four sets; wood — the original (all multipliers equal one). Set names are in the translation catalog. */
export const SOUND_SETS = {
    wood: {knock: 1, volume: 1, pitch: 1, wave: null},
    marble: {knock: 1.6, volume: 0.85, pitch: 1.12, wave: 'sine'},
    soft: {knock: 0.7, volume: 0.6, pitch: 0.85, wave: 'sine'},
    bright: {knock: 1.25, volume: 1, pitch: 1.25, wave: 'triangle'},
} satisfies Record<string, SoundSet>;

export type SoundSetId = keyof typeof SOUND_SETS;

/** Whether the set is known: a value in localStorage may be left over from another version. */
export function isSoundSetId(value: unknown): value is SoundSetId {
    return typeof value === 'string' && Object.prototype.hasOwnProperty.call(SOUND_SETS, value);
}

class SoundEngine {
    private ctx: AudioContext | null = null;
    private muted: boolean = false;
    private soundSet: SoundSetId = 'wood';

    constructor() {
        if (typeof window !== 'undefined') {
            this.muted = localStorage.getItem(MUTE_STORAGE_KEY) === 'true';
            const saved = localStorage.getItem(SOUND_SET_STORAGE_KEY);
            if (isSoundSetId(saved)) this.soundSet = saved;
        }
    }

    public getSoundSet(): SoundSetId {
        return this.soundSet;
    }

    public setSoundSet(id: SoundSetId): void {
        this.soundSet = id;
        if (typeof window !== 'undefined') {
            try {
                localStorage.setItem(SOUND_SET_STORAGE_KEY, id);
            } catch {
                // Storage unavailable — the set stays in effect until reload.
            }
        }
    }

    public isMuted(): boolean {
        return this.muted;
    }

    public setMuted(mute: boolean): void {
        this.muted = mute;
        if (typeof window !== 'undefined') {
            localStorage.setItem(MUTE_STORAGE_KEY, String(mute));
        }
    }

    public toggleMute(): boolean {
        this.setMuted(!this.muted);
        return this.muted;
    }

    /**
     * AudioContext is created on the first sound, not at load: browsers do not allow sound before a player action, and
     * a context created earlier stays "suspended" — so it is resumed here.
     */
    private getContext(): AudioContext | null {
        if (typeof window === 'undefined') return null;
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || (window as unknown as {
                webkitAudioContext?: typeof AudioContext
            }).webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().catch(() => {
            });
        }
        return this.ctx;
    }

    /**
     * One tone: frequency freq (with a smooth glide to endFreq if given), duration, delay from "now", waveform
     * and peak volume. The set profile applies only to sine and triangle: sawtooth and square are
     * warning signals and sound the same in any set.
     */
    private playTone(
        freq: number,
        durationSec: number,
        delaySec: number = 0,
        type: OscillatorType = 'sine',
        peakGain: number = 0.14,
        endFreq?: number
    ): void {
        const ctx = this.getContext();
        if (!ctx) return;

        const startTime = ctx.currentTime + delaySec;
        const stopTime = startTime + durationSec;
        const profile: SoundSet = SOUND_SETS[this.soundSet];
        if (type === 'sine' || type === 'triangle') {
            freq *= profile.pitch;
            if (endFreq !== undefined) endFreq *= profile.pitch;
            type = profile.wave ?? type;
            peakGain *= profile.volume;
        }

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = type;
        osc.frequency.setValueAtTime(freq, startTime);
        if (endFreq !== undefined) {
            osc.frequency.exponentialRampToValueAtTime(Math.max(20, endFreq), stopTime);
        }

        gain.gain.setValueAtTime(0.0001, startTime);
        gain.gain.linearRampToValueAtTime(peakGain, startTime + Math.min(0.015, durationSec * 0.2));
        gain.gain.exponentialRampToValueAtTime(0.0001, stopTime);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(startTime);
        osc.stop(stopTime + 0.01);
    }

    /**
     * Piece thud on the board: a short noise burst through a band-pass filter. Sounds are synthesized
     * entirely — the project has no ready-made recordings (see ATTRIBUTION.md), so there are no
     * licensing questions about them.
     */
    private playKnock(volume: number = 0.5, centerFreq: number = 950, delaySec: number = 0): void {
        const ctx = this.getContext();
        if (!ctx) return;

        const profile: SoundSet = SOUND_SETS[this.soundSet];
        centerFreq *= profile.knock;
        volume *= profile.volume;
        const durationSec = 0.07;
        const frameCount = Math.max(1, Math.floor(ctx.sampleRate * durationSec));
        const buffer = ctx.createBuffer(1, frameCount, ctx.sampleRate);
        const samples = buffer.getChannelData(0);
        for (let i = 0; i < frameCount; i++) {
            // Noise with a fast decay: a sharp attack and a short "wooden" tail.
            samples[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / frameCount, 3);
        }

        const startTime = ctx.currentTime + delaySec;
        const source = ctx.createBufferSource();
        source.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(centerFreq, startTime);
        filter.Q.setValueAtTime(1.4, startTime);

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(volume, startTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, startTime + durationSec);

        source.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        source.start(startTime);

        // A low "body" of the impact — without it the thud sounds like a click.
        this.playTone(centerFreq / 5.5, 0.06, delaySec, 'triangle', volume * 0.3, centerFreq / 11);
    }

    /** Brass fanfare voice: a sawtooth through a filter with light vibrato — a "trumpet" by synthesis, without recordings. */
    private brass(freq: number, start: number, duration: number, gain = 0.07): void {
        const ctx = this.getContext();
        if (!ctx) return;
        const t0 = ctx.currentTime + start;
        const osc = ctx.createOscillator();
        const filter = ctx.createBiquadFilter();
        const amp = ctx.createGain();
        const vibrato = ctx.createOscillator();
        const depth = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(freq, t0);
        vibrato.frequency.setValueAtTime(5.5, t0);
        depth.gain.setValueAtTime(freq * 0.006, t0);
        vibrato.connect(depth);
        depth.connect(osc.frequency);
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(900, t0);
        filter.frequency.linearRampToValueAtTime(2600, t0 + 0.08);
        filter.frequency.linearRampToValueAtTime(1500, t0 + duration);
        amp.gain.setValueAtTime(0.0001, t0);
        amp.gain.linearRampToValueAtTime(gain, t0 + 0.04);
        amp.gain.setValueAtTime(gain * 0.85, t0 + duration * 0.7);
        amp.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
        osc.connect(filter);
        filter.connect(amp);
        amp.connect(ctx.destination);
        osc.start(t0);
        vibrato.start(t0);
        osc.stop(t0 + duration + 0.05);
        vibrato.stop(t0 + duration + 0.05);
    }

    /**
     * Fanfares for a tournament prizewinner (owner decision, 17.11): for the winner — a solemn signal with a chord at the end,
     * for silver and bronze — shorter. Sound off — silence.
     */
    public playFanfare(place: number): void {
        if (this.muted) return;
        const chord = (notes: number[], start: number, duration: number) =>
            notes.forEach((freq) => this.brass(freq, start, duration, 0.05));
        // C major: C5 E5 G5 C6.
        const [c5, e5, g5, c6] = [523.25, 659.25, 783.99, 1046.5];
        if (place === 1) {
            this.brass(g5 / 2, 0, 0.16);
            this.brass(g5 / 2, 0.18, 0.16);
            this.brass(g5 / 2, 0.36, 0.16);
            this.brass(c5, 0.54, 0.55);
            this.brass(g5 / 2, 1.12, 0.16);
            this.brass(c5, 1.3, 0.16);
            this.brass(e5, 1.48, 0.16);
            chord([c5, e5, g5, c6], 1.66, 1.6);
        } else if (place === 2) {
            this.brass(g5 / 2, 0, 0.16);
            this.brass(c5, 0.18, 0.16);
            this.brass(e5, 0.36, 0.16);
            chord([c5, e5, g5], 0.54, 1.3);
        } else {
            this.brass(c5, 0, 0.18);
            this.brass(e5, 0.2, 0.18);
            chord([c5, g5], 0.4, 1.1);
        }
    }

    /** Play an event sound; with sound off — nothing. Notes and durations are set right here, per event. */
    public play(event: SoundEventType): void {
        if (this.muted) return;

        switch (event) {
            case 'move':
                this.playKnock(0.5, 950);
                break;

            case 'capture':
                // Capture: two thuds in a row — the piece is removed, the piece is placed.
                this.playKnock(0.55, 1500);
                this.playKnock(0.6, 800, 0.045);
                break;

            case 'castle':
                this.playKnock(0.45, 950);
                this.playKnock(0.5, 850, 0.095);
                break;

            case 'check':
                this.playKnock(0.4, 1100);
                this.playTone(587.33, 0.11, 0, 'triangle', 0.16);
                this.playTone(880.0, 0.24, 0.08, 'sine', 0.18, 830.0);
                break;

            case 'promote':
                this.playKnock(0.4, 950);
                this.playTone(523.25, 0.10, 0, 'triangle', 0.14);
                this.playTone(659.25, 0.10, 0.07, 'triangle', 0.15);
                this.playTone(783.99, 0.12, 0.14, 'triangle', 0.16);
                this.playTone(1046.5, 0.25, 0.21, 'sine', 0.18);
                break;

            case 'premove':
                this.playTone(420, 0.045, 0, 'sine', 0.09, 310);
                break;

            case 'illegal':
                this.playTone(155, 0.11, 0, 'sawtooth', 0.14, 115);
                this.playTone(130, 0.14, 0.09, 'sawtooth', 0.14, 95);
                break;

            case 'start':
                this.playTone(440.0, 0.12, 0, 'triangle', 0.12);
                this.playTone(554.37, 0.14, 0.09, 'triangle', 0.13);
                this.playTone(659.25, 0.26, 0.18, 'sine', 0.15);
                break;

            case 'chat':
                this.playTone(660, 0.07, 0, 'sine', 0.11);
                this.playTone(880, 0.11, 0.06, 'sine', 0.12);
                break;

            case 'offer':
                this.playTone(587.33, 0.14, 0, 'sine', 0.16);
                this.playTone(783.99, 0.22, 0.12, 'sine', 0.16);
                this.playTone(987.77, 0.28, 0.24, 'triangle', 0.14);
                break;

            case 'decline':
                this.playTone(440.0, 0.12, 0, 'triangle', 0.13);
                this.playTone(329.63, 0.22, 0.11, 'triangle', 0.13);
                break;

            case 'low_time':
                this.playTone(880.0, 0.08, 0, 'square', 0.11);
                this.playTone(880.0, 0.08, 0.12, 'square', 0.11);
                this.playTone(1046.5, 0.14, 0.24, 'square', 0.13);
                break;

            case 'victory':
                this.playTone(523.25, 0.12, 0, 'triangle', 0.16);
                this.playTone(659.25, 0.12, 0.10, 'triangle', 0.16);
                this.playTone(783.99, 0.14, 0.20, 'triangle', 0.17);
                this.playTone(1046.5, 0.38, 0.30, 'sine', 0.20);
                break;

            case 'defeat':
                this.playTone(392.0, 0.16, 0, 'triangle', 0.15);
                this.playTone(349.23, 0.16, 0.14, 'triangle', 0.15);
                this.playTone(311.13, 0.18, 0.28, 'triangle', 0.15);
                this.playTone(261.63, 0.40, 0.42, 'sine', 0.17);
                break;

            case 'draw':
                this.playTone(440.0, 0.16, 0, 'triangle', 0.14);
                this.playTone(523.25, 0.16, 0.14, 'triangle', 0.14);
                this.playTone(440.0, 0.30, 0.28, 'sine', 0.14);
                break;
        }
    }
}

/** Single instance per tab: settings are read from localStorage when the module loads. */
export const soundEngine = new SoundEngine();

/**
 * Check sound — only in learning (owner decision, 17.11): in lessons, puzzles and trainers it hints that the
 * king is under attack, while in games — rated, vs bots, tournament, any — it annoys and distracts. The mode is
 * toggled by App from the page address (isLearningPath); outside learning a checking move sounds like an ordinary move or capture.
 */
let checkSounds = false;

/** Turn the check sound on or off; App calls it on every page address change. */
export function setCheckSounds(enabled: boolean): void {
    checkSounds = enabled;
}

/** Whether check currently sounds as a separate signal. */
export function checkSoundsEnabled(): boolean {
    return checkSounds;
}

/** Prefixes of learning-section addresses (an exact match or a continuation after "/"). */
const LEARNING_PATHS = ['/learn', '/puzzles', '/train', '/workout', '/programs', '/guess'];

/** Learning section: school and course, puzzles, trainers, warm-up, programs, "Guess the move"; and repertoire training. */
export function isLearningPath(pathname: string): boolean {
    if (/^\/repertoire\/[^/]+\/drill\/?$/.test(pathname)) return true;
    return LEARNING_PATHS.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * Determines the suitable move sound effect from its SAN notation. Checks go in order of precedence: check or mate (only
 * when the check sound is on), promotion, castling, capture; everything else is an ordinary move.
 */
export function resolveMoveSound(san?: string | null): SoundEventType {
    if (!san) return 'move';
    if (checkSounds && (san.includes('#') || san.includes('+'))) return 'check';
    if (san.includes('=')) return 'promote';
    if (san.startsWith('O-O')) return 'castle';
    if (san.includes('x')) return 'capture';
    return 'move';
}