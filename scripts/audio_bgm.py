#!/usr/bin/env python3
"""Generate 100% original, procedural royalty-free stereo BGM tracks for TikTok Shop videos."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
DIR_BGM = ROOT_DIR / "06_assets_audio" / "bgm"

SR = 44100


def _adsr(n_samples: int, attack_s: float = 0.015, decay_s: float = 0.25) -> np.ndarray:
    t = np.arange(n_samples, dtype=np.float32) / SR
    att = np.minimum(1.0, t / max(1e-4, attack_s))
    dec = np.exp(-np.maximum(0.0, t - attack_s) / max(1e-3, decay_s))
    return (att * dec).astype(np.float32)


def _add_note(
    buf_l: np.ndarray,
    buf_r: np.ndarray,
    start_s: float,
    freq: float,
    dur_s: float,
    amp: float = 0.14,
    pan: float = 0.0,
    warm: bool = True,
) -> None:
    s0 = int(round(start_s * SR))
    n = int(round(dur_s * SR))
    if s0 >= len(buf_l) or n <= 0:
        return
    n = min(n, len(buf_l) - s0)
    t = np.arange(n, dtype=np.float32) / SR
    env = _adsr(n, attack_s=0.012, decay_s=max(0.08, dur_s * 0.65))
    wave_sig = np.sin(2.0 * math.pi * freq * t)
    if warm:
        wave_sig = 0.72 * wave_sig + 0.20 * np.sin(4.0 * math.pi * freq * t) + 0.08 * np.sin(6.0 * math.pi * freq * t)
    else:
        wave_sig = 0.65 * wave_sig + 0.25 * np.sin(4.0 * math.pi * freq * t) + 0.10 * np.sin(8.0 * math.pi * freq * t)
    sig = (wave_sig * env * amp).astype(np.float32)
    gain_l = math.sqrt(0.5 * (1.0 - max(-0.8, min(0.8, pan))))
    gain_r = math.sqrt(0.5 * (1.0 + max(-0.8, min(0.8, pan))))
    buf_l[s0 : s0 + n] += sig * gain_l
    buf_r[s0 : s0 + n] += sig * gain_r


def _add_kick(buf_l: np.ndarray, buf_r: np.ndarray, start_s: float, amp: float = 0.24) -> None:
    s0 = int(round(start_s * SR))
    n = min(int(0.16 * SR), len(buf_l) - s0)
    if s0 >= len(buf_l) or n <= 0:
        return
    t = np.arange(n, dtype=np.float32) / SR
    freq_env = 52.0 + 95.0 * np.exp(-t / 0.032)
    phase = 2.0 * math.pi * np.cumsum(freq_env) / SR
    env = np.exp(-t / 0.055)
    sig = (np.sin(phase) * env * amp).astype(np.float32)
    buf_l[s0 : s0 + n] += sig
    buf_r[s0 : s0 + n] += sig


def _add_hat(buf_l: np.ndarray, buf_r: np.ndarray, start_s: float, amp: float = 0.05, rng: np.random.Generator | None = None) -> None:
    s0 = int(round(start_s * SR))
    n = min(int(0.055 * SR), len(buf_l) - s0)
    if s0 >= len(buf_l) or n <= 0:
        return
    gen = rng or np.random.default_rng(42)
    noise = gen.uniform(-1.0, 1.0, size=n).astype(np.float32)
    # Simple high-pass difference for crisp light hi-hat
    hp = np.diff(noise, prepend=0.0)
    t = np.arange(n, dtype=np.float32) / SR
    sig = (hp * np.exp(-t / 0.014) * amp).astype(np.float32)
    buf_l[s0 : s0 + n] += sig * 0.9
    buf_r[s0 : s0 + n] += sig * 1.1


def _finalize_and_save(path: Path, buf_l: np.ndarray, buf_r: np.ndarray, target_rms: float = 0.18) -> Path:
    # Smooth loop boundaries (15ms fade in/out) and normalize loudness cleanly
    fade_n = int(0.015 * SR)
    ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
    buf_l[:fade_n] *= ramp
    buf_r[:fade_n] *= ramp
    buf_l[-fade_n:] *= ramp[::-1]
    buf_r[-fade_n:] *= ramp[::-1]

    stereo = np.stack([buf_l, buf_r], axis=1)
    rms = float(np.sqrt(np.mean(stereo ** 2))) or 1e-5
    stereo = stereo * (target_rms / rms)
    stereo = np.tanh(stereo * 0.95) * 0.92
    pcm = np.clip(stereo * 32767.0, -32767.0, 32767.0).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return path


def _synth_upbeat_tiktok(path: Path) -> Path:
    bpm = 116.0
    beat = 60.0 / bpm
    bar = beat * 4.0
    total_bars = 16  # ~33.1s clean loop
    n_samples = int(round(total_bars * bar * SR))
    bl = np.zeros(n_samples, dtype=np.float32)
    br = np.zeros(n_samples, dtype=np.float32)
    rng = np.random.default_rng(101)

    # Bright TikTok Pop progression: Fmaj7 -> G6 -> Em7 -> Am7
    chords = [
        ([174.61, 220.00, 261.63, 329.63], 87.31),   # Fmaj7
        ([196.00, 246.94, 293.66, 329.63], 98.00),   # G6
        ([164.81, 196.00, 246.94, 293.66], 82.41),   # Em7
        ([220.00, 261.63, 329.63, 392.00], 110.00),  # Am7
    ]
    melody = [523.25, 659.25, 587.33, 440.00, 523.25, 659.25, 783.99, 659.25]

    for b_idx in range(total_bars):
        t_bar = b_idx * bar
        chord_freqs, bass_f = chords[b_idx % len(chords)]
        # Warm rhythmic chords on beats 1 and 2.5
        for cf in chord_freqs:
            _add_note(bl, br, t_bar, cf, beat * 1.4, amp=0.065, pan=-0.15, warm=True)
            _add_note(bl, br, t_bar + beat * 1.5, cf, beat * 1.6, amp=0.055, pan=0.15, warm=True)
        # Bouncy bass
        _add_note(bl, br, t_bar, bass_f, beat * 0.9, amp=0.18, pan=0.0, warm=True)
        _add_note(bl, br, t_bar + beat * 1.5, bass_f, beat * 0.8, amp=0.14, pan=0.0, warm=True)
        _add_note(bl, br, t_bar + beat * 3.0, bass_f * 1.5, beat * 0.7, amp=0.12, pan=0.0, warm=True)
        # Pluck melody
        m1 = melody[(b_idx * 2) % len(melody)]
        m2 = melody[(b_idx * 2 + 1) % len(melody)]
        _add_note(bl, br, t_bar + beat * 0.5, m1, beat * 0.7, amp=0.075, pan=0.28, warm=False)
        _add_note(bl, br, t_bar + beat * 2.5, m2, beat * 0.8, amp=0.075, pan=-0.28, warm=False)
        # Four-on-the-floor soft kick + offbeat hi-hats
        for k in range(4):
            _add_kick(bl, br, t_bar + k * beat, amp=0.22)
            _add_hat(bl, br, t_bar + (k + 0.5) * beat, amp=0.045, rng=rng)

    return _finalize_and_save(path, bl, br, target_rms=0.18)


def _synth_chill_lofi(path: Path) -> Path:
    bpm = 88.0
    beat = 60.0 / bpm
    bar = beat * 4.0
    total_bars = 12  # ~32.7s clean loop
    n_samples = int(round(total_bars * bar * SR))
    bl = np.zeros(n_samples, dtype=np.float32)
    br = np.zeros(n_samples, dtype=np.float32)
    rng = np.random.default_rng(202)

    chords = [
        ([261.63, 329.63, 392.00, 493.88], 130.81),  # Cmaj7
        ([220.00, 261.63, 329.63, 392.00], 110.00),  # Am7
        ([174.61, 220.00, 261.63, 329.63], 87.31),   # Fmaj7
        ([196.00, 246.94, 293.66, 349.23], 98.00),   # G7
    ]
    for b_idx in range(total_bars):
        t_bar = b_idx * bar
        chord_freqs, bass_f = chords[b_idx % len(chords)]
        for ci, cf in enumerate(chord_freqs):
            _add_note(bl, br, t_bar + ci * 0.025, cf, bar * 0.92, amp=0.072, pan=-0.2 + ci * 0.12, warm=True)
        _add_note(bl, br, t_bar, bass_f, beat * 2.2, amp=0.17, pan=0.0, warm=True)
        _add_note(bl, br, t_bar + beat * 2.5, bass_f * 1.25, beat * 1.2, amp=0.12, pan=0.0, warm=True)
        _add_kick(bl, br, t_bar, amp=0.18)
        _add_kick(bl, br, t_bar + beat * 2.5, amp=0.15)
        for k in range(8):
            _add_hat(bl, br, t_bar + k * (beat * 0.5), amp=0.032 if k % 2 == 0 else 0.022, rng=rng)

    return _finalize_and_save(path, bl, br, target_rms=0.17)


def _synth_flash_sale(path: Path) -> Path:
    bpm = 126.0
    beat = 60.0 / bpm
    bar = beat * 4.0
    total_bars = 16  # ~30.5s clean loop
    n_samples = int(round(total_bars * bar * SR))
    bl = np.zeros(n_samples, dtype=np.float32)
    br = np.zeros(n_samples, dtype=np.float32)
    rng = np.random.default_rng(303)

    roots = [110.00, 130.81, 146.83, 164.81]  # A2, C3, D3, E3 energetic groove
    arp = [440.0, 523.25, 659.25, 523.25, 440.0, 587.33, 659.25, 783.99]

    for b_idx in range(total_bars):
        t_bar = b_idx * bar
        root = roots[b_idx % len(roots)]
        for step in range(8):
            t_s = t_bar + step * (beat * 0.5)
            _add_note(bl, br, t_s, root * (1.0 if step % 2 == 0 else 2.0), beat * 0.42, amp=0.13, pan=0.0, warm=True)
            _add_note(bl, br, t_s, arp[(step + b_idx) % len(arp)], beat * 0.38, amp=0.068, pan=-0.25 if step % 2 == 0 else 0.25, warm=False)
        for k in range(4):
            _add_kick(bl, br, t_bar + k * beat, amp=0.25)
            _add_hat(bl, br, t_bar + (k + 0.5) * beat, amp=0.052, rng=rng)

    return _finalize_and_save(path, bl, br, target_rms=0.19)


def _synth_styled_bgm(
    path: Path,
    *,
    bpm: float,
    chords: list[tuple[list[float], float]],
    melody_notes: list[float],
    seed: int,
    has_kick: bool = True,
    has_hat: bool = True,
    warm: bool = True,
    arp_step_mult: float = 0.5,
    target_rms: float = 0.17,
) -> Path:
    beat = 60.0 / bpm
    bar = beat * 4.0
    total_bars = 16
    n_samples = int(round(total_bars * bar * SR))
    bl = np.zeros(n_samples, dtype=np.float32)
    br = np.zeros(n_samples, dtype=np.float32)
    rng = np.random.default_rng(seed)

    steps_per_bar = max(2, int(round(4.0 / arp_step_mult)))
    for b_idx in range(total_bars):
        t_bar = b_idx * bar
        chord_freqs, bass_freq = chords[b_idx % len(chords)]
        for cf in chord_freqs:
            _add_note(bl, br, t_bar, cf, bar * 0.90, amp=0.085, pan=0.0, warm=warm)
        _add_note(bl, br, t_bar, bass_freq, beat * 1.8, amp=0.14, pan=0.0, warm=True)
        _add_note(bl, br, t_bar + beat * 2.0, bass_freq * 1.5, beat * 1.6, amp=0.10, pan=0.0, warm=True)
        for s_i in range(steps_per_bar):
            t_s = t_bar + s_i * (beat * arp_step_mult)
            mf = melody_notes[(b_idx * 3 + s_i) % len(melody_notes)]
            pan = -0.35 if s_i % 2 == 0 else 0.35
            _add_note(bl, br, t_s, mf, beat * arp_step_mult * 0.85, amp=0.072, pan=pan, warm=warm)
        if has_kick:
            for k in range(4):
                _add_kick(bl, br, t_bar + k * beat, amp=0.22)
        if has_hat:
            for k in range(4):
                _add_hat(bl, br, t_bar + (k + 0.5) * beat, amp=0.045, rng=rng)
    return _finalize_and_save(path, bl, br, target_rms=target_rms)


BGM_TRACK_CATALOG: list[dict[str, str]] = [
    {"id": "bgm_upbeat_tiktok.wav", "label": "🎵 Upbeat TikTok Shop (116 BPM · Năng động)"},
    {"id": "bgm_chill_lofi.wav", "label": "🌿 Chill Lo-Fi Review (88 BPM · Nhẹ nhàng)"},
    {"id": "bgm_flash_sale.wav", "label": "⚡ Flash Sale Săn Deal (126 BPM · Sôi động)"},
    {"id": "bgm_acoustic_warm.wav", "label": "🎸 Acoustic Warm (96 BPM · Mỹ phẩm / Thực phẩm)"},
    {"id": "bgm_funky_groove.wav", "label": "🕺 Funky Groove (114 BPM · Lifestyle / Đồ ăn)"},
    {"id": "bgm_tech_minimal.wav", "label": "💻 Tech Minimal (118 BPM · Công nghệ / Gia dụng)"},
    {"id": "bgm_luxury_piano.wav", "label": "✨ Luxury Piano (82 BPM · Hàng cao cấp)"},
    {"id": "bgm_trap_hype.wav", "label": "🔥 Trap Viral Hype (132 BPM · Bùng nổ chốt đơn)"},
    {"id": "bgm_bossa_cafe.wav", "label": "☕ Bossa Nova Cafe (94 BPM · Thư giãn tinh tế)"},
    {"id": "bgm_kpop_sparkle.wav", "label": "🌟 Synth Pop Sparkle (122 BPM · Trẻ trung)"},
    {"id": "bgm_cyber_pulse.wav", "label": "💜 Cyber Neon Pulse (120 BPM · Đêm / Neon)"},
    {"id": "bgm_happy_ukulele.wav", "label": "🌼 Happy Ukulele (108 BPM · Gia đình / Mẹ & Bé)"},
    {"id": "bgm_cinematic_rise.wav", "label": "🎬 Cinematic Story (90 BPM · Kể chuyện sâu)"},
    {"id": "bgm_tropical_house.wav", "label": "🌴 Tropical Fresh (112 BPM · Mát mẻ sảng khoái)"},
    {"id": "bgm_deep_focus.wav", "label": "🎧 Deep Focus Ambient (84 BPM · Review chuyên sâu)"},
    {"id": "bgm_upbeat_default.wav", "label": "🎹 Nhạc Synth Mặc Định"},
]


def ensure_royalty_free_bgm_library(force: bool = False) -> list[dict[str, Any]]:
    DIR_BGM.mkdir(parents=True, exist_ok=True)
    builders: dict[str, Any] = {
        "bgm_upbeat_tiktok.wav": _synth_upbeat_tiktok,
        "bgm_chill_lofi.wav": _synth_chill_lofi,
        "bgm_flash_sale.wav": _synth_flash_sale,
        "bgm_acoustic_warm.wav": lambda p: _synth_styled_bgm(
            p, bpm=96.0, seed=401, has_kick=False, has_hat=False, warm=True, arp_step_mult=1.0, target_rms=0.14,
            chords=[([261.63, 329.63, 392.00], 130.81), ([196.00, 246.94, 293.66], 98.00), ([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31)],
            melody_notes=[523.25, 659.25, 587.33, 493.88, 440.00, 523.25],
        ),
        "bgm_funky_groove.wav": lambda p: _synth_styled_bgm(
            p, bpm=114.0, seed=402, has_kick=True, has_hat=True, warm=False, arp_step_mult=0.5, target_rms=0.18,
            chords=[([164.81, 196.00, 246.94, 293.66], 82.41), ([146.83, 174.61, 220.00, 261.63], 73.42)],
            melody_notes=[329.63, 392.00, 493.88, 587.33, 493.88, 392.00],
        ),
        "bgm_tech_minimal.wav": lambda p: _synth_styled_bgm(
            p, bpm=118.0, seed=403, has_kick=True, has_hat=True, warm=False, arp_step_mult=0.5, target_rms=0.16,
            chords=[([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31), ([196.00, 246.94, 293.66], 98.00)],
            melody_notes=[440.00, 523.25, 659.25, 440.00, 783.99, 659.25],
        ),
        "bgm_luxury_piano.wav": lambda p: _synth_styled_bgm(
            p, bpm=82.0, seed=404, has_kick=False, has_hat=False, warm=True, arp_step_mult=1.0, target_rms=0.13,
            chords=[([174.61, 220.00, 261.63, 329.63], 87.31), ([146.83, 174.61, 220.00, 261.63], 73.42), ([196.00, 246.94, 293.66, 349.23], 98.00)],
            melody_notes=[523.25, 659.25, 783.99, 659.25, 587.33, 523.25],
        ),
        "bgm_trap_hype.wav": lambda p: _synth_styled_bgm(
            p, bpm=132.0, seed=405, has_kick=True, has_hat=True, warm=False, arp_step_mult=0.5, target_rms=0.19,
            chords=[([130.81, 155.56, 196.00], 65.41), ([116.54, 146.83, 174.61], 58.27), ([103.83, 130.81, 155.56], 51.91)],
            melody_notes=[523.25, 622.25, 783.99, 622.25, 523.25, 466.16],
        ),
        "bgm_bossa_cafe.wav": lambda p: _synth_styled_bgm(
            p, bpm=94.0, seed=406, has_kick=False, has_hat=True, warm=True, arp_step_mult=0.75, target_rms=0.14,
            chords=[([261.63, 329.63, 392.00, 493.88], 130.81), ([293.66, 349.23, 440.00, 523.25], 146.83)],
            melody_notes=[659.25, 587.33, 523.25, 493.88, 440.00, 523.25],
        ),
        "bgm_kpop_sparkle.wav": lambda p: _synth_styled_bgm(
            p, bpm=122.0, seed=407, has_kick=True, has_hat=True, warm=False, arp_step_mult=0.5, target_rms=0.18,
            chords=[([293.66, 369.99, 440.00], 146.83), ([220.00, 277.18, 329.63], 110.00), ([246.94, 293.66, 369.99], 123.47), ([196.00, 246.94, 293.66], 98.00)],
            melody_notes=[587.33, 739.99, 880.00, 739.99, 659.25, 587.33],
        ),
        "bgm_cyber_pulse.wav": lambda p: _synth_styled_bgm(
            p, bpm=120.0, seed=408, has_kick=True, has_hat=True, warm=False, arp_step_mult=0.5, target_rms=0.18,
            chords=[([220.00, 261.63, 329.63], 110.00), ([196.00, 246.94, 293.66], 98.00), ([174.61, 220.00, 261.63], 87.31), ([164.81, 196.00, 246.94], 82.41)],
            melody_notes=[440.00, 523.25, 659.25, 880.00, 659.25, 523.25],
        ),
        "bgm_happy_ukulele.wav": lambda p: _synth_styled_bgm(
            p, bpm=108.0, seed=409, has_kick=True, has_hat=False, warm=True, arp_step_mult=0.5, target_rms=0.16,
            chords=[([261.63, 329.63, 392.00], 130.81), ([174.61, 220.00, 261.63], 87.31), ([196.00, 246.94, 293.66], 98.00)],
            melody_notes=[523.25, 587.33, 659.25, 783.99, 659.25, 523.25],
        ),
        "bgm_cinematic_rise.wav": lambda p: _synth_styled_bgm(
            p, bpm=90.0, seed=410, has_kick=False, has_hat=False, warm=True, arp_step_mult=1.0, target_rms=0.15,
            chords=[([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31), ([130.81, 164.81, 196.00], 65.41), ([196.00, 246.94, 293.66], 98.00)],
            melody_notes=[440.00, 523.25, 659.25, 587.33, 523.25, 493.88],
        ),
        "bgm_tropical_house.wav": lambda p: _synth_styled_bgm(
            p, bpm=112.0, seed=411, has_kick=True, has_hat=True, warm=True, arp_step_mult=0.5, target_rms=0.17,
            chords=[([174.61, 220.00, 261.63], 87.31), ([196.00, 246.94, 293.66], 98.00), ([220.00, 261.63, 329.63], 110.00)],
            melody_notes=[698.46, 659.25, 523.25, 587.33, 659.25, 783.99],
        ),
        "bgm_deep_focus.wav": lambda p: _synth_styled_bgm(
            p, bpm=84.0, seed=412, has_kick=False, has_hat=False, warm=True, arp_step_mult=1.0, target_rms=0.13,
            chords=[([196.00, 233.08, 293.66], 98.00), ([155.56, 196.00, 233.08], 77.78), ([174.61, 207.65, 261.63], 87.31)],
            melody_notes=[392.00, 466.16, 587.33, 466.16, 392.00, 349.23],
        ),
    }
    for fname, fn in builders.items():
        p = DIR_BGM / fname
        if force or not p.exists() or p.stat().st_size < 100_000:
            fn(p)

    out: list[dict[str, Any]] = []
    known = {item["id"]: item["label"] for item in BGM_TRACK_CATALOG}
    for p in sorted(DIR_BGM.iterdir()):
        if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".m4a"):
            out.append(
                {
                    "id": p.name,
                    "label": known.get(p.name, f"🎶 {p.name}"),
                    "url": f"/files/06_assets_audio/bgm/{p.name}",
                }
            )
    # Sort preferred tracks first
    order = {item["id"]: i for i, item in enumerate(BGM_TRACK_CATALOG)}
    out.sort(key=lambda x: order.get(x["id"], 99))
    return out


if __name__ == "__main__":
    tracks = ensure_royalty_free_bgm_library(force=True)
    print("Generated BGM library:", [t["id"] for t in tracks])
