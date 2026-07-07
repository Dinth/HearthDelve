"""Procedural background music — a long, evolving fantasy piece.

Aims for a 16-bit tracker / SNES-JRPG voice rather than bare 8-bit chiptune:
warm detuned-oscillator instruments (a plucked lute, a string pad, a soft lead),
a real bass, a light drum kit, all sweetened with a convolution reverb + echo so
it sounds produced rather than dry. The arrangement is a ~90s intro → A → B → A
→ bridge → A structure that develops instead of looping every few bars.

Everything is synthesised from numpy and played through tcod's bundled SDL audio
(no extra dependency), rendered off-thread so it never stalls startup. Fails
silent: with no audio device, the whole module no-ops and the game is unaffected.
"""
from __future__ import annotations

import threading

import numpy as np

SR = 44100
BPM = 100
STEP = 60.0 / BPM / 2                 # one 8th-note, seconds
STEP_N = int(STEP * SR)
STEPS_PER_BAR = 8


# --- oscillators & envelopes -------------------------------------------------
def _wave(kind, ph, duty=0.5):
    if kind == "saw":
        return 2.0 * (ph - np.floor(ph + 0.5))
    if kind == "square":
        return np.where((ph % 1.0) < duty, 1.0, -1.0).astype(np.float64)
    if kind == "tri":
        return 2.0 * np.abs(2.0 * (ph - np.floor(ph + 0.5))) - 1.0
    return np.sin(2.0 * np.pi * ph)   # sine


def _phase(freq, n, vib=0.0, vib_hz=5.2):
    t = np.arange(n) / SR
    f = freq * (1.0 + vib * np.sin(2.0 * np.pi * vib_hz * t))
    return np.cumsum(f / SR)


def _detuned(freq, n, kind, cents, duty=0.5, vib=0.0):
    """A stack of slightly detuned oscillators — the core of the warm, wide,
    'sampled' timbre (versus a single hard 8-bit square)."""
    out = np.zeros(n)
    for c in cents:
        out += _wave(kind, _phase(freq * 2 ** (c / 1200.0), n, vib=vib), duty)
    return out / len(cents)


def _adsr(n, a, d, s, r):
    e = np.zeros(n)
    ai = min(int(a * SR), n)
    if ai:
        e[:ai] = np.linspace(0.0, 1.0, ai)
    rest = n - ai
    if rest > 0:
        di = max(1, int(d * SR))
        e[ai:] = s + (1.0 - s) * np.exp(-np.arange(rest) / di)
    ri = min(int(r * SR), n)
    if ri:
        e[-ri:] *= np.linspace(1.0, 0.0, ri)
    return e


def _midi(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


# --- instruments (return mono float64) --------------------------------------
def _lute(freq, dur):
    """A plucked-string lute: bright detuned saws with a fast, natural decay."""
    n = max(1, int(dur * SR))
    tone = 0.7 * _detuned(freq, n, "saw", (-6, 0, 6)) + 0.3 * _detuned(freq, n, "tri", (0,))
    env = _adsr(n, 0.002, 0.22, 0.0, 0.03)
    return tone * env


def _pad(freq, dur):
    """A soft string pad: several detuned saws, slow swell, long tail."""
    n = max(1, int(dur * SR))
    tone = _detuned(freq, n, "saw", (-9, -4, 3, 8), vib=0.004)
    tone = 0.8 * tone + 0.2 * np.sin(2 * np.pi * _phase(freq, n))   # a little body
    env = _adsr(n, 0.18, 0.9, 0.55, 0.35)
    return tone * env


def _lead(freq, dur):
    """A singing lead: detuned pulse+saw with vibrato, gentle decay."""
    n = max(1, int(dur * SR))
    tone = 0.6 * _detuned(freq, n, "square", (-4, 5), duty=0.42, vib=0.010) \
        + 0.4 * _detuned(freq, n, "saw", (0,), vib=0.010)
    env = _adsr(n, 0.012, 0.6, 0.35, 0.09)
    return tone * env


def _bass(freq, dur):
    n = max(1, int(dur * SR))
    tone = 0.6 * _wave("tri", _phase(freq, n)) + 0.4 * np.sin(2 * np.pi * _phase(freq / 2, n))
    env = _adsr(n, 0.006, 0.5, 0.6, 0.05)
    return tone * env


def _kick(rng, dur=0.18):
    n = int(dur * SR); t = np.arange(n) / SR
    f = 118.0 * np.exp(-t * 30.0) + 46.0
    return np.sin(2 * np.pi * np.cumsum(f / SR)) * np.exp(-t * 13.0)


def _snare(rng, dur=0.15):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = rng.random(n) * 2 - 1
    noise[1:] = 0.5 * (noise[1:] + noise[:-1])          # soften the hiss
    return (noise * 0.45 + np.sin(2 * np.pi * 190 * t) * 0.45) * np.exp(-t * 24.0)


def _hat(rng, dur=0.045):
    n = int(dur * SR); t = np.arange(n) / SR
    noise = rng.random(n) * 2 - 1
    noise[1:] = 0.5 * (noise[1:] + noise[:-1])          # a touch less white/harsh
    return noise * np.exp(-t * 95.0)


# --- harmony & arrangement ---------------------------------------------------
_CHORDS = {
    "Am": (57, (0, 3, 7)), "F": (53, (0, 4, 7)), "C": (60, (0, 4, 7)),
    "G": (55, (0, 4, 7)), "Dm": (50, (0, 3, 7)), "Em": (52, (0, 3, 7)),
    "E": (52, (0, 4, 7)),                          # dominant (with G#) of A-minor
}
_A_PROG = ["Am", "F", "C", "G", "Am", "F", "E", "Am"]
_B_PROG = ["C", "G", "Am", "Em", "F", "C", "Dm", "E"]
_INTRO = ["Am", "F", "C", "E"]
_BRIDGE = ["Dm", "Am", "Dm", "E"]
_OUTRO = ["Am", "F", "E", "Am"]

# (progression, drums?, lead?) per section — the piece develops through them.
# It resolves on Am and loops back to the Am intro, so the seam is harmonically
# smooth as well as click-free (see _make_seamless).
_SECTIONS = [
    (_INTRO, False, False),   # bare: pad + lute wash
    (_A_PROG, True, True),    # full band
    (_B_PROG, True, True),    # brighter variation
    (_A_PROG, True, True),
    (_BRIDGE, False, True),   # drop the drums, let the lead breathe
    (_B_PROG, True, True),
    (_A_PROG, True, True),
    (_BRIDGE, False, True),
    (_A_PROG, True, True),
    (_OUTRO, False, False),   # gentle resolve back toward the intro
]

_A_MINOR_PCS = (9, 11, 0, 2, 4, 5, 7)


def _melodist(prog, rng, lo=69, hi=84):
    """A chord-aware random-walk melody in A-minor: chord tones on the strong
    beats, smooth stepwise motion between, with the odd rest and held note."""
    scale = [m for m in range(lo, hi + 1) if m % 12 in _A_MINOR_PCS]
    seq, prev = [], scale[len(scale) // 2]
    for name in prog:
        root, ivals = _CHORDS[name]
        pcs = {(root + iv) % 12 for iv in ivals}
        ctones = [m for m in scale if m % 12 in pcs] or scale
        for step in range(STEPS_PER_BAR):
            strong = step % 4 == 0
            r = rng.random()
            if not strong and r < 0.16:
                seq.append(None); continue
            if not strong and r < 0.40:
                seq.append("h"); continue
            if strong:
                note = min(ctones, key=lambda m: abs(m - prev))
            else:
                i = min(range(len(scale)), key=lambda k: abs(scale[k] - prev))
                i = max(0, min(len(scale) - 1, i + rng.choice([-2, -1, 1, 1, 2])))
                note = scale[i]
                if rng.random() < 0.3:
                    note = min(ctones, key=lambda m: abs(m - note))
            seq.append(note); prev = note
    return seq


def _place(buf, seg, start, gain=1.0):
    end = min(len(buf), start + len(seg))
    if end > start:
        buf[start:end] += seg[:end - start] * gain


# --- reverb / echo (circular, so the loop stays seamless) --------------------
def _impulse_response(rng):
    """A stereo IR: a couple of tempo-synced echoes plus an exponential reverb
    tail. Kept short relative to the loop; circular convolution wraps its tail
    to the top so the loop has no seam."""
    length = int(1.6 * SR)
    ir = np.zeros((length, 2))
    ir[0] = 1.0                                            # direct sound
    for delay, g in ((STEP_N * 3, 0.32), (STEP_N * 6, 0.16)):  # dotted echoes
        if delay < length:
            ir[delay] += (g, g * 0.85)
    t = np.arange(length) / SR
    tail = (rng.random((length, 2)) * 2 - 1) * np.exp(-t[:, None] * 5.2)
    for _ in range(3):                                     # smooth the tail so the
        tail[1:] = 0.5 * (tail[1:] + tail[:-1])            # reverb is a wash, not hiss
    tail[: int(0.03 * SR)] = 0.0                           # small pre-delay
    ir += tail * 0.11
    return ir


def _make_seamless(stereo, ms=70):
    """Crossfade the loop point so playback wraps with no click. The first `xf`
    samples become (head fading in + old-tail fading out), and the tail is then
    dropped — so the new end connects to the new start on originally-adjacent
    samples. Any clipped release at the old end is faded out rather than snapped."""
    xf = int(ms / 1000.0 * SR)
    if xf * 2 >= len(stereo):
        return stereo
    fi = np.linspace(0.0, 1.0, xf)[:, None]
    out = stereo.copy()
    out[:xf] = stereo[:xf] * fi + stereo[-xf:] * (1.0 - fi)
    return out[:-xf]


def _next_pow2(n):
    return 1 << ((int(n) - 1).bit_length())


def _fft_lowpass(sig, cutoff):
    N = len(sig); M = _next_pow2(N)                        # pow2 -> fast FFT
    roll = 1.0 / (1.0 + (np.fft.rfftfreq(M, 1 / SR) / cutoff) ** 4)   # ~4th-order
    return np.fft.irfft(np.fft.rfft(sig, M) * roll, M)[:N]


def _reverb(stereo, ir, wet=0.17):
    N = len(stereo); K = len(ir); M = _next_pow2(N + K)
    out = np.empty_like(stereo)
    for ch in range(2):
        conv = np.fft.irfft(np.fft.rfft(stereo[:, ch], M) * np.fft.rfft(ir[:, ch], M), M)
        wetc = conv[:N].copy()
        over = conv[N:N + K]
        wetc[:len(over)] += over                           # wrap tail -> seamless loop
        combined = stereo[:, ch] * (1.0 - wet) + wetc * wet
        out[:, ch] = _fft_lowpass(combined, 5600.0)        # warm; tames any hiss
    return out


# --- render ------------------------------------------------------------------
def _render_loop():
    """Synthesise the whole seamless stereo piece as float32 in [-1, 1]."""
    rng = np.random.default_rng(20250707)
    total_bars = sum(len(p) for p, _, _ in _SECTIONS)
    total = total_bars * STEPS_PER_BAR * STEP_N
    lead = np.zeros(total); pad = np.zeros(total)
    lute = np.zeros(total); bass = np.zeros(total); drums = np.zeros(total)

    bar0 = 0
    for prog, use_drums, use_lead in _SECTIONS:
        melody = _melodist(prog, rng) if use_lead else None
        for bi, name in enumerate(prog):
            bar = bar0 + bi
            base = bar * STEPS_PER_BAR * STEP_N
            root, ivals = _CHORDS[name]
            tones = [root + iv for iv in ivals]

            # sustained string pad across the whole bar (chord voicing)
            for iv in ivals:
                _place(pad, _pad(_midi(root + iv), STEP * STEPS_PER_BAR * 1.02),
                       base, gain=0.16)

            # plucked-lute arpeggio, an up/down sweep of the chord
            arp = tones + [root + 12] + tones[::-1][1:]
            for step in range(STEPS_PER_BAR):
                note = arp[step % len(arp)] + 12
                _place(lute, _lute(_midi(note), STEP * 1.4), base + step * STEP_N, gain=0.22)

            # bass: root then fifth, half-note feel
            for beat, off in enumerate((0, 4)):
                note = root - 12 + (7 if beat else 0)
                _place(bass, _bass(_midi(note), STEP * 2.0), base + off * STEP_N, gain=0.42)

            if use_drums:
                for off in (0, 4):
                    _place(drums, _kick(rng), base + off * STEP_N, gain=0.72)
                for off in (2, 6):
                    _place(drums, _snare(rng), base + off * STEP_N, gain=0.26)
                for off in range(1, STEPS_PER_BAR, 2):
                    _place(drums, _hat(rng), base + off * STEP_N, gain=0.12)

        # lead melody for the section
        if melody is not None:
            cur, cur_start = None, 0
            for i, v in enumerate(melody):
                if v == "h":
                    continue
                if cur is not None:
                    dur = (i - cur_start) * STEP
                    _place(lead, _lead(_midi(cur), dur * 1.05),
                           (bar0 * STEPS_PER_BAR + cur_start) * STEP_N, gain=0.36)
                cur, cur_start = (None if v is None else v), i
            if cur is not None:
                dur = (len(melody) - cur_start) * STEP
                _place(lead, _lead(_midi(cur), dur * 1.05),
                       (bar0 * STEPS_PER_BAR + cur_start) * STEP_N, gain=0.36)
        bar0 += len(prog)

    # mix with stereo placement
    def pan(mono, p):
        return mono * np.sqrt((1 - p) / 2), mono * np.sqrt((1 + p) / 2)

    ll = np.zeros(total); rr = np.zeros(total)
    for mono, p in ((lead, -0.22), (lute, 0.28), (pad, -0.05),
                    (bass, 0.0), (drums, 0.06)):
        l, r = pan(mono, p); ll += l; rr += r
    stereo = np.stack([ll, rr], axis=1)

    stereo = _make_seamless(stereo, ms=70)             # click-free loop point
    stereo = _reverb(stereo, _impulse_response(rng))   # circular: tail wraps too
    peak = float(np.max(np.abs(stereo))) or 1.0
    stereo = (stereo / peak) * 0.86
    return np.ascontiguousarray(stereo, dtype=np.float32)


# --- player ------------------------------------------------------------------
class Music:
    """Owns the audio device and a looping channel; renders off-thread. Robust
    to having no audio device at all."""

    def __init__(self, volume: float = 0.6):
        self.volume = volume
        self.muted = False
        self.ok = False
        self._dev = None
        self._mixer = None
        self._chan = None
        self._buf = None
        self._stopped = False
        self._thread = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._render_and_play, daemon=True)
        self._thread.start()

    def _render_and_play(self) -> None:
        try:
            buf = _render_loop()
            if self._stopped:
                return
            import tcod.sdl.audio as A
            try:
                self._dev = A.get_default_playback().open(
                    frequency=SR, channels=2, format=np.float32)
            except Exception:
                self._dev = A.open(frequency=SR, channels=2, format=np.float32)
            self._mixer = A.BasicMixer(self._dev)
            self._buf = buf
            if self._stopped:
                return
            vol = 0.0 if self.muted else self.volume
            self._chan = self._mixer.play(buf, volume=vol, loops=-1)
            self.ok = True
        except Exception:
            self.ok = False        # no audio available — carry on silently

    def _apply_volume(self) -> None:
        if self._chan is not None:
            try:
                self._chan.volume = 0.0 if self.muted else self.volume
            except Exception:
                pass

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        self._apply_volume()
        return self.muted

    def set_volume(self, v: float) -> None:
        self.volume = max(0.0, min(1.0, v))
        self.muted = False
        self._apply_volume()

    def stop(self) -> None:
        self._stopped = True
        try:
            if self._mixer is not None:
                self._mixer.close()
            if self._dev is not None:
                self._dev.close()
        except Exception:
            pass
        self._chan = self._mixer = self._dev = None
        self.ok = False
