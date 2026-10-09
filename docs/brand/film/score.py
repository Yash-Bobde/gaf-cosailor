"""Original soundtrack for the Cosailor brand film, synthesized from scratch.

    python docs/brand/film/score.py [out.wav]

Warm, unhurried, practical: a D-major pad (I–vi–IV–V), a plucked arpeggio, a soft
half-time pulse, and a riser + chime on every scene change of brand-film.html.
No samples or third-party audio, so there is nothing to license.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44_100
DURATION = 54.0
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT                       # 2.5 s
SCENES = [5.0, 10.5, 16.5, 22.5, 28.5, 35.5, 42.5, 48.5]   # must match render(t)
END = 48.5                            # end card: rhythm stops, final chord rings

N = int(SR * DURATION)
rng = np.random.default_rng(7)
L = np.zeros(N)
R = np.zeros(N)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(sig, start, gain=1.0, pan=0.0):
    """Mix a mono signal in at start seconds; pan -1 (left) … 1 (right)."""
    i = int(start * SR)
    if i >= N:
        return
    sig = sig[: N - i] * gain
    L[i : i + len(sig)] += sig * np.sqrt((1 - pan) / 2)
    R[i : i + len(sig)] += sig * np.sqrt((1 + pan) / 2)


def lowpass(sig, cutoff, order=2):
    return sosfilt(butter(order, cutoff, 'low', fs=SR, output='sos'), sig)


def highpass(sig, cutoff, order=2):
    return sosfilt(butter(order, cutoff, 'high', fs=SR, output='sos'), sig)


def envelope(n, attack, release, total):
    t = np.arange(n) / SR
    env = np.minimum(1, t / attack) if attack > 0 else np.ones(n)
    return env * np.clip((total - t) / release, 0, 1)


# ---- Harmony: I – vi – IV – V in D, one chord per bar ----------------------
CHORDS = [
    ([62, 66, 69, 73], 38),   # Dmaj7
    ([59, 62, 66, 69], 35),   # Bm7
    ([55, 59, 62, 66], 43),   # Gmaj7
    ([57, 64, 69, 71], 45),   # Aadd9 (no 3rd, open)
]
FINAL = ([62, 66, 69, 73, 76], 38)   # Dmaj9 on the end card


def pad_note(freq, length):
    """Soft additive 'analog' pad: 3 detuned voices, rolled-off harmonics."""
    n = int(length * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for cents in (-7, 0, 7):
        f = freq * 2 ** (cents / 1200)
        phase = rng.uniform(0, 2 * np.pi)
        for h in range(1, 9):
            out += np.sin(2 * np.pi * f * h * t + phase * h) / h ** 1.8
    return out / 3


def pad_level(t):
    """Quiet intro, full body from scene 2, a lift at the product scenes."""
    return 0.55 + 0.25 * np.clip((t - 4) / 3, 0, 1) + 0.1 * np.clip((t - 42) / 2, 0, 1)


bar = 0
while bar * BAR < END:
    start = bar * BAR
    notes, root = CHORDS[bar % 4]
    length = BAR + 1.6
    for k, m in enumerate(notes):
        sig = lowpass(pad_note(hz(m), length), 1800) * envelope(int(length * SR), 0.9, 1.6, length)
        add(sig, start, 0.05 * pad_level(start), pan=(-0.35, 0.35)[k % 2])
    # Bass: sine + a touch of 2nd harmonic on beats 1 and 3.
    if start >= 5.0:
        for b in (0, 2):
            n = int(1.4 * SR)
            t = np.arange(n) / SR
            f = hz(root)
            sig = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * np.exp(-t * 2.2)
            add(sig * envelope(n, 0.01, 0.2, 1.4), start + b * BEAT, 0.16)
    bar += 1

# Final chord: long, open, with a slow bloom.
notes, root = FINAL
for k, m in enumerate(notes + [root + 12]):
    length = DURATION - END
    sig = lowpass(pad_note(hz(m), length), 2200) * envelope(int(length * SR), 0.4, 3.5, length)
    add(sig, END, 0.055, pan=(-0.4, 0.4)[k % 2])


# ---- Plucked arpeggio (8ths) from scene 2 to the end card ------------------
def pluck(freq, length=0.9):
    n = int(length * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t) + 0.12 * np.sin(6 * np.pi * freq * t)
    return lowpass(tone * np.exp(-t * 5.5) * np.minimum(1, t / 0.004), 4200)


PATTERN = [0, 2, 1, 3, 2, 1, 3, 2]
step = 0
t = 5.0
while t < END - 0.05:
    bar_i = int(t // BAR)
    notes, _ = CHORDS[bar_i % 4]
    m = notes[PATTERN[step % 8]] + 12
    accent = 1.0 if step % 2 == 0 else 0.7
    add(pluck(hz(m)), t, 0.07 * accent, pan=0.45 if step % 2 else -0.45)
    step += 1
    t = 5.0 + step * BEAT / 2          # 5.0 s is exactly beat 8, so the arp sits on the grid


# ---- Pulse: soft half-time kick, then off-beat shaker ----------------------
def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 42 + 70 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def shaker():
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    return highpass(rng.standard_normal(n), 6000) * np.exp(-t * 60)


beat_t = np.ceil(10.5 / BEAT) * BEAT
while beat_t < END - 0.1:
    idx = round(beat_t / BEAT)
    if idx % 2 == 0:
        add(kick(), beat_t, 0.20)
    if beat_t >= 16.5:
        add(shaker(), beat_t + BEAT / 2, 0.035, pan=0.3)
    beat_t += BEAT


# ---- Transitions: noise riser into each scene, chime on arrival ------------
def riser(length=1.1):
    n = int(length * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    # Sweep a band upward by blending three fixed bands with a rising weight.
    low, mid, high = lowpass(noise, 900), lowpass(highpass(noise, 900), 3500), highpass(noise, 3500)
    x = t / length
    sig = low * (1 - x) + mid * np.sin(np.pi * x) + high * x
    return sig * x ** 2.2


def chime(freq, length=2.6):
    """Bell: inharmonic partials with staggered decays."""
    n = int(length * SR)
    t = np.arange(n) / SR
    parts = [(1.0, 1.0, 1.6), (2.0, 0.45, 2.4), (2.76, 0.25, 3.4), (5.4, 0.08, 5.0)]
    sig = sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * d) for r, a, d in parts)
    return sig * np.minimum(1, t / 0.003)


CHIME_NOTES = [81, 78, 76, 81, 83, 78, 76, 74]   # A5 F#5 E5 A5 B5 F#5 E5 D5
for s, m in zip(SCENES, CHIME_NOTES):
    add(riser(), s - 1.1, 0.045)
    add(chime(hz(m)), s, 0.06, pan=0.15)

# Logo reveal (the wordmark wipes in at 1.6 s) and the final "Know who to call first."
add(chime(hz(74), 4.0), 1.55, 0.07)
add(chime(hz(81), 4.0), 1.95, 0.04, pan=0.3)
add(chime(hz(86), 4.5), 49.4, 0.035, pan=-0.2)

# The roof rising (29.6–33.6 s): a gentle upward glide, D5 → D6.
n = int(4.4 * SR)
tt = np.arange(n) / SR
x = np.clip(tt / 4.0, 0, 1)
x = np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)       # matches easeInOut
f = hz(74) * 2 ** x
glide = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.2 * np.sin(4 * np.pi * np.cumsum(f) / SR)
add(glide * envelope(n, 0.6, 0.8, 4.4), 29.6, 0.03, pan=0.2)


# ---- Master: plate-ish reverb, gentle glue, fade ---------------------------
def reverb_ir(seconds=2.4, seed=0):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-t * 3.0)
    return lowpass(ir, 5000) / np.sqrt(np.sum(ir ** 2))


wet_l = fftconvolve(L, reverb_ir(seed=1))[:N]
wet_r = fftconvolve(R, reverb_ir(seed=2))[:N]
mix = np.stack([L + 0.32 * wet_l, R + 0.32 * wet_r], axis=1)

time = np.arange(N) / SR
fade = np.clip(time / 0.4, 0, 1) * np.clip((DURATION - time) / 2.5, 0, 1)
mix *= fade[:, None]
mix = np.tanh(mix * 1.6) / 1.6                     # soft saturation / glue
mix *= 10 ** (-1.0 / 20) / np.max(np.abs(mix))    # peak at -1 dBFS

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('score.wav')
wavfile.write(out, SR, (mix * 32767).astype(np.int16))
print(f'wrote {out} ({DURATION:.0f}s, {SR} Hz stereo)')
