let sfxCtx = null;
let sfxWarmupPromise = null;

export function getSfxCtx() {
    if (!sfxCtx) {
        sfxCtx = new (window.AudioContext || window.webkitAudioContext)();
    }

    return sfxCtx;
}

export async function warmUpSfx() {
    if (!sfxWarmupPromise) {
        sfxWarmupPromise = (async () => {
            const ctx = getSfxCtx();

            await ctx.resume();

            await new Promise((resolve) => {
                const o = ctx.createOscillator();
                const g = ctx.createGain();
                const start = ctx.currentTime + 0.05;
                const end = start + 0.25;

                o.type = 'sine';
                o.frequency.setValueAtTime(440, start);

                g.gain.setValueAtTime(0.0001, start);
                g.gain.linearRampToValueAtTime(0.02, start + 0.02);
                g.gain.exponentialRampToValueAtTime(0.0001, end);

                o.onended = resolve;

                o.connect(g);
                g.connect(ctx.destination);

                o.start(start);
                o.stop(end);
            });
        })();
    }

    return sfxWarmupPromise;
}

function playTone({ type, frequency, duration, volume = 0.03 }) {
    const ctx = getSfxCtx();
    const start = ctx.currentTime + 0.02;
    const end = start + duration;

    const o = ctx.createOscillator();
    const g = ctx.createGain();

    o.type = type;
    o.frequency.setValueAtTime(frequency, start);

    g.gain.cancelScheduledValues(start);
    g.gain.setValueAtTime(0.0001, start);
    g.gain.linearRampToValueAtTime(volume, start + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, end);

    o.connect(g);
    g.connect(ctx.destination);

    o.start(start);
    o.stop(end);
}

export function playSuccess() {
    playTone({ type: 'sine', frequency: 800, duration: 1.5 });
}

export function playFail() {
    playTone({ type: 'sawtooth', frequency: 200, duration: 1.5 });
}