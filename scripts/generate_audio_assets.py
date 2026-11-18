#!/usr/bin/env python3
"""Tạo sẵn bộ hiệu ứng âm thanh (SFX) và nhạc nền mẫu sạch trong 06_assets_audio/."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIR_ASSETS_AUDIO = PROJECT_ROOT / "06_assets_audio"
DIR_BGM = DIR_ASSETS_AUDIO / "bgm"
SR = 44100


def _write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -0.98, 0.98)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def make_whoosh(path: Path) -> None:
    dur = 0.38
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, n)
    # Moving simple lowpass-like smoothing envelope + sweep sine
    env = np.sin(math.pi * (t / dur)) ** 1.6
    # Smooth noise with rolling window
    kernel = np.ones(45) / 45.0
    smooth_noise = np.convolve(noise, kernel, mode="same")
    sweep = np.sin(2 * math.pi * (120 + 520 * (t / dur) ** 1.4) * t) * 0.25
    out = (smooth_noise * 1.4 + sweep) * env * 0.55
    _write_wav(path, out)


def make_pop(path: Path) -> None:
    dur = 0.14
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 320 + 620 * np.exp(-t * 28)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 32) * (1 - np.exp(-t * 350))
    out = np.sin(phase) * env * 0.75
    _write_wav(path, out)


def make_ding(path: Path) -> None:
    dur = 0.65
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 6.5) * (1 - np.exp(-t * 400))
    tone = (
        0.65 * np.sin(2 * math.pi * 1046.5 * t)
        + 0.25 * np.sin(2 * math.pi * 1567.98 * t)
        + 0.15 * np.sin(2 * math.pi * 2093.0 * t)
    )
    out = tone * env * 0.55
    _write_wav(path, out)


def make_upbeat_bgm(path: Path, dur: float = 32.0) -> None:
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    bpm = 116.0
    beat_dur = 60.0 / bpm
    # Warm 4-chord progression (C - G - Am - F)
    chords = [
        (261.63, 329.63, 392.00),
        (196.00, 246.94, 293.66),
        (220.00, 261.63, 329.63),
        (174.61, 220.00, 261.63),
    ]
    beat_idx = (t / beat_dur).astype(int)
    chord_idx = (beat_idx // 4) % len(chords)
    beat_pos = (t % beat_dur) / beat_dur

    pad = np.zeros(n, dtype=np.float64)
    for ci, freqs in enumerate(chords):
        mask = chord_idx == ci
        if not np.any(mask):
            continue
        tm = t[mask]
        chord_sig = sum(np.sin(2 * math.pi * f * tm) for f in freqs) / 3.0
        # Gentle rhythmic sidechain pump per beat
        pump = 0.55 + 0.45 * np.sin(math.pi * beat_pos[mask]) ** 0.8
        pad[mask] = chord_sig * pump * 0.26

    # Soft bass pulse on downbeats
    bass_freqs = np.array([130.81, 98.00, 110.00, 87.31])[chord_idx]
    bass_env = np.exp(-beat_pos * 4.5)
    bass = np.sin(2 * math.pi * np.cumsum(bass_freqs) / SR) * bass_env * 0.22

    # Soft hi-hat tick every half beat
    sub_pos = (t % (beat_dur / 2)) / (beat_dur / 2)
    rng = np.random.default_rng(11)
    hat_noise = rng.normal(0, 1, n)
    hat_env = np.exp(-sub_pos * 35) * 0.04
    hat = hat_noise * hat_env

    out = pad + bass + hat
    # Fade in 0.8s & fade out 1.2s
    fade_in = min(n, int(0.8 * SR))
    fade_out = min(n, int(1.2 * SR))
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    _write_wav(path, out)


def make_bubble_pop(path: Path) -> None:
    dur = 0.16
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 440 + 780 * (1 - np.exp(-t * 38))
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 28) * (1 - np.exp(-t * 420))
    _write_wav(path, np.sin(phase) * env * 0.72)


def make_camera_shutter(path: Path) -> None:
    dur = 0.22
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(23)
    noise = rng.normal(0, 1, n)
    click1 = np.exp(-((t - 0.015) / 0.008) ** 2)
    click2 = np.exp(-((t - 0.075) / 0.010) ** 2) * 0.75
    tone = np.sin(2 * math.pi * 1650 * t) * 0.25 + np.sin(2 * math.pi * 2400 * t) * 0.15
    out = (noise * 0.7 + tone) * (click1 + click2) * 0.65
    _write_wav(path, out)


def make_swoosh_soft(path: Path) -> None:
    dur = 0.42
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(31)
    noise = rng.normal(0, 1, n)
    kernel = np.ones(85) / 85.0
    smooth = np.convolve(noise, kernel, mode="same")
    env = np.sin(math.pi * (t / dur)) ** 2.0
    warm = np.sin(2 * math.pi * (160 + 280 * (t / dur)) * t) * 0.18
    _write_wav(path, (smooth * 1.2 + warm) * env * 0.45)


def make_sparkle_chime(path: Path) -> None:
    dur = 0.75
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    notes = [(0.00, 1318.5), (0.06, 1567.98), (0.12, 1975.53), (0.18, 2637.02)]
    out = np.zeros(n, dtype=np.float64)
    for st, freq in notes:
        dt = np.maximum(0.0, t - st)
        mask = t >= st
        env = np.exp(-dt[mask] * 7.5) * (1 - np.exp(-dt[mask] * 450))
        out[mask] += (np.sin(2 * math.pi * freq * dt[mask]) + 0.25 * np.sin(4 * math.pi * freq * dt[mask])) * env * 0.30
    _write_wav(path, out)


def make_coin_clink(path: Path) -> None:
    dur = 0.48
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env1 = np.exp(-t * 11.0) * (1 - np.exp(-t * 600))
    t2 = np.maximum(0.0, t - 0.08)
    env2 = np.where(t >= 0.08, np.exp(-t2 * 9.0) * (1 - np.exp(-t2 * 600)), 0.0)
    s1 = np.sin(2 * math.pi * 1975.5 * t) * env1 * 0.45
    s2 = (np.sin(2 * math.pi * 2637.0 * t2) + 0.3 * np.sin(2 * math.pi * 3951.0 * t2)) * env2 * 0.45
    _write_wav(path, s1 + s2)


def make_typewriter_tick(path: Path) -> None:
    dur = 0.09
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(47)
    noise = rng.normal(0, 1, n)
    env = np.exp(-t * 75.0) * (1 - np.exp(-t * 900))
    sig = (noise * 0.4 + np.sin(2 * math.pi * 1200 * t) * 0.6) * env * 0.55
    _write_wav(path, sig)


def make_riser_short(path: Path) -> None:
    dur = 0.85
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 180 + 980 * (t / dur) ** 2.2
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = (t / dur) ** 1.6 * np.exp(-np.maximum(0.0, t - 0.72) * 24)
    _write_wav(path, np.sin(phase) * env * 0.45)


def make_snap_finger(path: Path) -> None:
    dur = 0.14
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(59)
    noise = rng.normal(0, 1, n)
    env = np.exp(-t * 48.0) * (1 - np.exp(-t * 800))
    tone = np.sin(2 * math.pi * (1400 * np.exp(-t * 18) + 600) * t)
    _write_wav(path, (tone * 0.7 + noise * 0.3) * env * 0.65)


def make_notification(path: Path) -> None:
    dur = 0.50
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    e1 = np.exp(-t * 9.0) * (1 - np.exp(-t * 500))
    t2 = np.maximum(0.0, t - 0.11)
    e2 = np.where(t >= 0.11, np.exp(-t2 * 7.5) * (1 - np.exp(-t2 * 500)), 0.0)
    s = np.sin(2 * math.pi * 880 * t) * e1 * 0.42 + np.sin(2 * math.pi * 1318.5 * t2) * e2 * 0.48
    _write_wav(path, s)


def make_bass_drop_soft(path: Path) -> None:
    dur = 0.55
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 48 + 130 * np.exp(-t * 12)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 5.5) * (1 - np.exp(-t * 250))
    _write_wav(path, np.sin(phase) * env * 0.72)


def ensure_audio_assets() -> dict[str, Path]:
    DIR_ASSETS_AUDIO.mkdir(parents=True, exist_ok=True)
    DIR_BGM.mkdir(parents=True, exist_ok=True)
    sfx_builders = {
        "whoosh": ("sfx_whoosh.wav", make_whoosh),
        "pop": ("sfx_pop.wav", make_pop),
        "ding": ("sfx_ding.wav", make_ding),
        "bubble_pop": ("sfx_bubble_pop.wav", make_bubble_pop),
        "camera_shutter": ("sfx_camera_shutter.wav", make_camera_shutter),
        "swoosh_soft": ("sfx_swoosh_soft.wav", make_swoosh_soft),
        "sparkle_chime": ("sfx_sparkle_chime.wav", make_sparkle_chime),
        "coin_clink": ("sfx_coin_clink.wav", make_coin_clink),
        "typewriter_tick": ("sfx_typewriter_tick.wav", make_typewriter_tick),
        "riser_short": ("sfx_riser_short.wav", make_riser_short),
        "snap_finger": ("sfx_snap_finger.wav", make_snap_finger),
        "notification": ("sfx_notification.wav", make_notification),
        "bass_drop_soft": ("sfx_bass_drop_soft.wav", make_bass_drop_soft),
    }
    out: dict[str, Path] = {}
    for key, (fname, fn) in sfx_builders.items():
        p = DIR_ASSETS_AUDIO / fname
        if not p.exists():
            fn(p)
        out[key] = p
    bgm = DIR_BGM / "bgm_upbeat_default.wav"
    if not bgm.exists():
        make_upbeat_bgm(bgm)
    out["bgm"] = bgm
    return out


if __name__ == "__main__":
    res = ensure_audio_assets()
    for k, p in res.items():
        print(f"{k}: {p} ({p.stat().st_size} bytes)")
