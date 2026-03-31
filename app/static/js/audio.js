let sfxCtx = null;
let sfxWarmupPromise = null;

export function getSfxCtx() {
    if (!sfxCtx) {
        sfxCtx = new (window.AudioContext || window.webkitAudioContext)();
    }

    return sfxCtx;
}

export async function warmUpSfx() {
    alert('warmUpSfx: entered');

    if (!sfxWarmupPromise) {
        alert('warmUpSfx: creating promise');

        sfxWarmupPromise = (async () => {
            alert('warmUpSfx: before getSfxCtx');
            const ctx = getSfxCtx();
            alert(`warmUpSfx: got ctx state=${ctx.state}`);

            alert('warmUpSfx: before resume');
            await ctx.resume();
            alert(`warmUpSfx: after resume state=${ctx.state}`);

            alert('warmUpSfx: before oscillator promise');
            await new Promise((resolve) => {
                alert('warmUpSfx: inside promise start');

                const o = ctx.createOscillator();
                const g = ctx.createGain();
                const start = ctx.currentTime + 0.05;
                const end = start + 0.25;

                alert(`warmUpSfx: start=${start} end=${end}`);

                o.type = 'sine';
                o.frequency.setValueAtTime(440, start);

                g.gain.setValueAtTime(0.0001, start);
                g.gain.linearRampToValueAtTime(0.02, start + 0.02);
                g.gain.exponentialRampToValueAtTime(0.0001, end);

                o.onended = () => {
                    alert('warmUpSfx: oscillator ended');
                    resolve();
                };

                alert('warmUpSfx: before connect');
                o.connect(g);
                g.connect(ctx.destination);

                alert('warmUpSfx: before start');
                o.start(start);
                alert('warmUpSfx: before stop');
                o.stop(end);
                alert('warmUpSfx: after stop');
            });

            alert('warmUpSfx: after oscillator promise');
        })();
    }

    alert('warmUpSfx: returning promise');
    return sfxWarmupPromise;
}

function playTone({ type, frequency, duration, volume = 0.03, startTime = 0.00 }) {
    const ctx = getSfxCtx();
    const start = ctx.currentTime + 0.10 + startTime;
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

export function playComplete() {
    playTone({ type: 'triangle', frequency: 500, duration: 0.20, volume: 0.03 });
    playTone({ type: 'triangle', frequency: 1200, duration: 0.50, volume: 0.035, startTime: 0.20 });
}

export function playPerfect() {
    playTone({ type: 'triangle', frequency: 500, duration: 0.20, volume: 0.03 });
    playTone({ type: 'triangle', frequency: 600, duration: 0.30, volume: 0.035, startTime: 0.20 });
    playTone({ type: 'triangle', frequency: 700, duration: 0.40, volume: 0.035, startTime: 0.50 });
    playTone({ type: 'triangle', frequency: 800, duration: 0.50, volume: 0.035, startTime: 0.90 });
    playTone({ type: 'triangle', frequency: 900, duration: 0.60, volume: 0.035, startTime: 1.40 });
    playTone({ type: 'triangle', frequency: 1000, duration: 0.70, volume: 0.035, startTime: 2.00 });
    playTone({ type: 'triangle', frequency: 1100, duration: 0.80, volume: 0.035, startTime: 2.70 });
    playTone({ type: 'triangle', frequency: 1200, duration: 0.90, volume: 0.035, startTime: 3.50 });
    playTone({ type: 'triangle', frequency: 1300, duration: 1.00, volume: 0.035, startTime: 4.40 });
}