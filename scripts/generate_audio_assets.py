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
    dur = 0.12
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 240 + 360 * np.exp(-t * 32)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 38) * (1 - np.exp(-t * 280))
    out = np.sin(phase) * env * 0.42
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
    dur = 0.13
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = 340 + 460 * (1 - np.exp(-t * 34))
    phase = 2 * math.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 34) * (1 - np.exp(-t * 320))
    _write_wav(path, np.sin(phase) * env * 0.40)


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
    dur = 0.36
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(31)
    noise = rng.normal(0, 1, n)
    kernel = np.ones(120) / 120.0
    smooth = np.convolve(noise, kernel, mode="same")
    env = np.sin(math.pi * (t / dur)) ** 2.2
    warm = np.sin(2 * math.pi * (140 + 180 * (t / dur)) * t) * 0.10
    _write_wav(path, (smooth * 1.1 + warm) * env * 0.30)


def make_sparkle_chime(path: Path) -> None:
    dur = 0.55
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    notes = [(0.00, 1046.5), (0.06, 1318.5), (0.12, 1567.98)]
    out = np.zeros(n, dtype=np.float64)
    for st, freq in notes:
        dt = np.maximum(0.0, t - st)
        mask = t >= st
        env = np.exp(-dt[mask] * 9.5) * (1 - np.exp(-dt[mask] * 320))
        out[mask] += np.sin(2 * math.pi * freq * dt[mask]) * env * 0.22
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


def make_dramatic_boom(path: Path) -> None:
    dur = 1.35
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(101)
    freq = 42.0 + 135.0 * np.exp(-t * 8.5)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    sub = np.sin(phase) + 0.35 * np.sin(2.0 * phase)
    env = np.exp(-t * 2.8) * (1 - np.exp(-t * 320))
    transient = rng.normal(0, 1, n)
    kernel = np.ones(18) / 18.0
    thud = np.convolve(transient, kernel, mode="same") * np.exp(-t * 24.0) * 0.65
    _write_wav(path, (sub * 0.75 * env) + thud)


def make_heartbeat_low(path: Path) -> None:
    dur = 1.15
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    out = np.zeros(n, dtype=np.float64)
    for center, amp, f0 in [(0.08, 0.85, 58.0), (0.28, 0.62, 50.0), (0.66, 0.85, 58.0), (0.86, 0.62, 50.0)]:
        dt = np.maximum(0.0, t - center)
        mask = (t >= center) & (t < center + 0.19)
        if not np.any(mask):
            continue
        f_sweep = f0 + 48.0 * np.exp(-dt[mask] * 28.0)
        ph = 2 * math.pi * np.cumsum(f_sweep) / SR
        env = np.exp(-dt[mask] * 20.0) * (1 - np.exp(-dt[mask] * 260))
        out[mask] += np.sin(ph) * env * amp
    _write_wav(path, out)


def make_clock_tick(path: Path) -> None:
    dur = 0.95
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(103)
    noise = rng.normal(0, 1, n)
    out = np.zeros(n, dtype=np.float64)
    for idx, t0 in enumerate([0.04, 0.27, 0.50, 0.73]):
        dt = np.maximum(0.0, t - t0)
        mask = (t >= t0) & (t < t0 + 0.08)
        if not np.any(mask):
            continue
        tone_f = 2150.0 if idx % 2 == 0 else 1680.0
        env = np.exp(-dt[mask] * 95.0) * (1 - np.exp(-dt[mask] * 1200))
        sig = (0.65 * np.sin(2 * math.pi * tone_f * dt[mask]) + 0.35 * noise[mask]) * env
        out[mask] += sig * 0.62
    _write_wav(path, out)


def make_suspense_sting(path: Path) -> None:
    dur = 1.10
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(107)
    noise = rng.normal(0, 1, n)
    kernel = np.ones(35) / 35.0
    smooth_noise = np.convolve(noise, kernel, mode="same")
    # Dissonant minor-second cluster swelling up before sharp tail release
    swell = (t / dur) ** 1.45 * np.exp(-np.maximum(0.0, t - 0.88) * 18.0)
    f1 = 293.66 + 38.0 * (t / dur)
    f2 = 311.13 + 42.0 * (t / dur)
    f3 = 415.30 + 55.0 * (t / dur)
    sig = (
        0.38 * np.sin(2 * math.pi * np.cumsum(f1) / SR)
        + 0.36 * np.sin(2 * math.pi * np.cumsum(f2) / SR)
        + 0.24 * np.sin(2 * math.pi * np.cumsum(f3) / SR)
        + 0.22 * smooth_noise
    )
    _write_wav(path, sig * swell * 0.58)


def make_vine_boom(path: Path) -> None:
    dur = 0.72
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(109)
    freq = 54.0 + 185.0 * np.exp(-t * 16.0)
    phase = 2 * math.pi * np.cumsum(freq) / SR
    body = np.tanh((np.sin(phase) + 0.28 * np.sin(2.0 * phase)) * 1.45)
    env = np.exp(-t * 4.8) * (1 - np.exp(-t * 480))
    kick = np.convolve(rng.normal(0, 1, n), np.ones(12) / 12.0, mode="same") * np.exp(-t * 36.0) * 0.50
    _write_wav(path, (body * env * 0.78) + kick)


def make_record_scratch(path: Path) -> None:
    dur = 0.42
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(113)
    zip_hz = 460.0 + 680.0 * np.sin(2 * math.pi * 11.5 * t) * np.exp(-t * 3.0)
    zip_hz = np.maximum(140.0, zip_hz * np.exp(-t * 2.2))
    phase = 2 * math.pi * np.cumsum(zip_hz) / SR
    grit = rng.normal(0, 1, n) * 0.25
    env = np.sin(math.pi * (t / dur)) ** 0.7 * np.exp(-t * 2.4)
    out = np.tanh((np.sin(phase) + 0.45 * np.sin(2.5 * phase) + grit) * 1.2) * env * 0.62
    _write_wav(path, out)


def make_boing(path: Path) -> None:
    dur = 0.46
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    base_f = 260.0 + 210.0 * (1 - np.exp(-t * 10.0)) + 135.0 * np.sin(2 * math.pi * 16.0 * t) * np.exp(-t * 4.0)
    phase = 2 * math.pi * np.cumsum(base_f) / SR
    env = np.exp(-t * 5.2) * (1 - np.exp(-t * 380))
    _write_wav(path, (np.sin(phase) + 0.25 * np.sin(2 * phase)) * env * 0.56)


def make_cricket(path: Path) -> None:
    dur = 0.95
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    out = np.zeros(n, dtype=np.float64)
    for burst_start in (0.04, 0.50):
        for p in range(4):
            t0 = burst_start + p * 0.055
            mask = (t >= t0) & (t < t0 + 0.036)
            if not np.any(mask):
                continue
            dt = t[mask] - t0
            env = np.sin(math.pi * (dt / 0.036)) ** 1.3
            chirp = np.sin(2 * math.pi * 4320.0 * dt) + 0.35 * np.sin(2 * math.pi * 4480.0 * dt)
            out[mask] += chirp * env * 0.36
    _write_wav(path, out)


def ensure_audio_assets(force_soft: bool = False) -> dict[str, Path]:
    DIR_ASSETS_AUDIO.mkdir(parents=True, exist_ok=True)
    DIR_BGM.mkdir(parents=True, exist_ok=True)
    soft_keys = {"pop", "bubble_pop", "swoosh_soft", "sparkle_chime"}
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
        "dramatic_boom": ("sfx_dramatic_boom.wav", make_dramatic_boom),
        "heartbeat_low": ("sfx_heartbeat_low.wav", make_heartbeat_low),
        "clock_tick": ("sfx_clock_tick.wav", make_clock_tick),
        "suspense_sting": ("sfx_suspense_sting.wav", make_suspense_sting),
        "vine_boom": ("sfx_vine_boom.wav", make_vine_boom),
        "record_scratch": ("sfx_record_scratch.wav", make_record_scratch),
        "boing": ("sfx_boing.wav", make_boing),
        "cricket": ("sfx_cricket.wav", make_cricket),
    }
    out: dict[str, Path] = {}
    for key, (fname, fn) in sfx_builders.items():
        p = DIR_ASSETS_AUDIO / fname
        if not p.exists() or (force_soft and key in soft_keys):
            fn(p)
        out[key] = p
    bgm = DIR_BGM / "bgm_upbeat_default.wav"
    if not bgm.exists():
        make_upbeat_bgm(bgm)
    out["bgm"] = bgm
    return out


if __name__ == "__main__":
    res = ensure_audio_assets(force_soft=True)
    for k, p in res.items():
        print(f"{k}: {p} ({p.stat().st_size} bytes)")
