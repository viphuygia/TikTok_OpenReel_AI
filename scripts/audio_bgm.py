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

_EXTRA_BGM_PRESETS: list[dict[str, Any]] = [
    # --- Vlog & Camping / Thiên nhiên ---
    {
        "id": "bgm_vlog_campfire_guitar.wav",
        "label": "🏕️ [Vlog] Campfire Guitar (80 BPM · Lửa trại ấm áp)",
        "bpm": 80.0, "seed": 501, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.13,
        "chords": [([196.00, 246.94, 293.66], 98.00), ([164.81, 196.00, 246.94], 82.41), ([130.81, 164.81, 196.00], 65.41), ([146.83, 185.00, 220.00], 73.42)],
        "melody_notes": [392.00, 493.88, 587.33, 493.88, 440.00, 392.00],
    },
    {
        "id": "bgm_vlog_morning_mist.wav",
        "label": "🌄 [Vlog] Sương Sớm Rừng Thông (76 BPM · Bình minh nhẹ)",
        "bpm": 76.0, "seed": 502, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([174.61, 220.00, 261.63, 329.63], 87.31), ([130.81, 164.81, 196.00, 246.94], 65.41)],
        "melody_notes": [523.25, 440.00, 392.00, 329.63, 392.00, 440.00],
    },
    {
        "id": "bgm_vlog_sunset_acoustic.wav",
        "label": "🌅 [Vlog] Hoàng Hôn Bờ Hồ (86 BPM · Thư thái)",
        "bpm": 86.0, "seed": 503, "has_kick": False, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.13,
        "chords": [([220.00, 277.18, 329.63], 110.00), ([196.00, 246.94, 293.66], 98.00), ([146.83, 185.00, 220.00], 73.42), ([164.81, 207.65, 246.94], 82.41)],
        "melody_notes": [440.00, 554.37, 659.25, 587.33, 493.88, 440.00],
    },
    {
        "id": "bgm_vlog_forest_breeze.wav",
        "label": "🍃 [Vlog] Gió Rừng Thư Giãn (74 BPM · Thiên nhiên)",
        "bpm": 74.0, "seed": 504, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([146.83, 174.61, 220.00, 261.63], 73.42), ([196.00, 233.08, 293.66, 349.23], 98.00)],
        "melody_notes": [349.23, 440.00, 523.25, 440.00, 392.00, 349.23],
    },
    {
        "id": "bgm_vlog_weekend_picnic.wav",
        "label": "🧺 [Vlog] Dã Ngoại Cuối Tuần (98 BPM · Tươi sáng)",
        "bpm": 98.0, "seed": 505, "has_kick": True, "has_hat": False, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.15,
        "chords": [([261.63, 329.63, 392.00], 130.81), ([196.00, 246.94, 293.66], 98.00), ([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31)],
        "melody_notes": [523.25, 659.25, 783.99, 659.25, 587.33, 523.25],
    },
    # --- Du lịch & Roadtrip ---
    {
        "id": "bgm_travel_coastal_drive.wav",
        "label": "🚗 [Du Lịch] Coastal Roadtrip (106 BPM · Phóng khoáng)",
        "bpm": 106.0, "seed": 506, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.16,
        "chords": [([293.66, 369.99, 440.00], 146.83), ([220.00, 277.18, 329.63], 110.00), ([246.94, 293.66, 369.99], 123.47), ([196.00, 246.94, 293.66], 98.00)],
        "melody_notes": [587.33, 659.25, 739.99, 880.00, 739.99, 587.33],
    },
    {
        "id": "bgm_travel_mountain_pass.wav",
        "label": "⛰️ [Du Lịch] Vượt Đèo Đón Gió (102 BPM · Hùng vĩ)",
        "bpm": 102.0, "seed": 507, "has_kick": True, "has_hat": False, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.16,
        "chords": [([164.81, 196.00, 246.94], 82.41), ([130.81, 164.81, 196.00], 65.41), ([196.00, 246.94, 293.66], 98.00), ([146.83, 185.00, 220.00], 73.42)],
        "melody_notes": [392.00, 493.88, 659.25, 587.33, 493.88, 392.00],
    },
    {
        "id": "bgm_travel_golden_horizon.wav",
        "label": "☀️ [Du Lịch] Chân Trời Nắng Vàng (110 BPM · Rạng rỡ)",
        "bpm": 110.0, "seed": 508, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.17,
        "chords": [([174.61, 220.00, 261.63], 87.31), ([261.63, 329.63, 392.00], 130.81), ([196.00, 246.94, 293.66], 98.00)],
        "melody_notes": [523.25, 587.33, 698.46, 783.99, 659.25, 523.25],
    },
    {
        "id": "bgm_travel_train_window.wav",
        "label": "🚆 [Du Lịch] Khung Cửa Tàu Chiều (89 BPM · Hoài niệm)",
        "bpm": 89.0, "seed": 509, "has_kick": False, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.13,
        "chords": [([220.00, 261.63, 329.63, 392.00], 110.00), ([174.61, 220.00, 261.63, 329.63], 87.31)],
        "melody_notes": [659.25, 587.33, 523.25, 440.00, 493.88, 523.25],
    },
    {
        "id": "bgm_travel_island_breeze.wav",
        "label": "🏝️ [Du Lịch] Gió Biển Đảo Xanh (104 BPM · Mát lành)",
        "bpm": 104.0, "seed": 510, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.15,
        "chords": [([246.94, 311.13, 369.99], 123.47), ([164.81, 207.65, 246.94], 82.41), ([220.00, 277.18, 329.63], 110.00)],
        "melody_notes": [493.88, 622.25, 739.99, 659.25, 554.37, 493.88],
    },
    # --- Piano & Ambient Chậm ---
    {
        "id": "bgm_piano_rainy_window.wav",
        "label": "🌧️ [Piano] Mưa Ngoài Cửa Sổ (72 BPM · Sâu lắng)",
        "bpm": 72.0, "seed": 511, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([220.00, 261.63, 329.63], 110.00), ([174.61, 207.65, 261.63], 87.31), ([130.81, 164.81, 196.00], 65.41), ([196.00, 246.94, 293.66], 98.00)],
        "melody_notes": [523.25, 493.88, 440.00, 392.00, 329.63, 392.00],
    },
    {
        "id": "bgm_piano_midnight_letters.wav",
        "label": "🌙 [Piano] Thư Đêm Yên Tĩnh (75 BPM · Trầm ấm)",
        "bpm": 75.0, "seed": 512, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([146.83, 174.61, 220.00], 73.42), ([116.54, 146.83, 174.61], 58.27), ([130.81, 164.81, 196.00], 65.41), ([110.00, 138.59, 164.81], 55.00)],
        "melody_notes": [440.00, 392.00, 349.23, 329.63, 293.66, 349.23],
    },
    {
        "id": "bgm_piano_soft_sunrise.wav",
        "label": "☀️ [Piano] Nắng Sớm Nhẹ Nhàng (80 BPM · Trong trẻo)",
        "bpm": 80.0, "seed": 513, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.13,
        "chords": [([261.63, 329.63, 392.00, 493.88], 130.81), ([174.61, 220.00, 261.63, 329.63], 87.31)],
        "melody_notes": [523.25, 659.25, 783.99, 987.77, 783.99, 659.25],
    },
    {
        "id": "bgm_ambient_starry_night.wav",
        "label": "✨ [Ambient] Đêm Sao Lấp Lánh (70 BPM · Chill sâu)",
        "bpm": 70.0, "seed": 514, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([164.81, 196.00, 246.94, 293.66], 82.41), ([130.81, 164.81, 196.00, 246.94], 65.41)],
        "melody_notes": [493.88, 587.33, 659.25, 587.33, 493.88, 392.00],
    },
    {
        "id": "bgm_ambient_warm_horizon.wav",
        "label": "🕯️ [Ambient] Ánh Nến Ấm Áp (78 BPM · Tâm sự)",
        "bpm": 78.0, "seed": 515, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.12,
        "chords": [([196.00, 246.94, 293.66, 369.99], 98.00), ([146.83, 185.00, 220.00, 261.63], 73.42)],
        "melody_notes": [440.00, 493.88, 587.33, 523.25, 440.00, 392.00],
    },
    # --- Lo-Fi & Café Chill ---
    {
        "id": "bgm_lofi_late_night.wav",
        "label": "🌃 [Lo-Fi] Phố Đêm Tĩnh Lặng (82 BPM · Chill)",
        "bpm": 82.0, "seed": 516, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.14,
        "chords": [([174.61, 207.65, 261.63, 311.13], 87.31), ([155.56, 196.00, 233.08, 293.66], 77.78)],
        "melody_notes": [466.16, 523.25, 622.25, 587.33, 466.16, 392.00],
    },
    {
        "id": "bgm_lofi_coffee_corner.wav",
        "label": "☕ [Lo-Fi] Góc Quán Cà Phê (85 BPM · Mộc mạc)",
        "bpm": 85.0, "seed": 517, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.14,
        "chords": [([196.00, 246.94, 293.66, 349.23], 98.00), ([261.63, 329.63, 392.00, 493.88], 130.81)],
        "melody_notes": [523.25, 493.88, 440.00, 392.00, 493.88, 523.25],
    },
    {
        "id": "bgm_lofi_study_clouds.wav",
        "label": "☁️ [Lo-Fi] Trôi Theo Đám Mây (84 BPM · Nhẹ đầu)",
        "bpm": 84.0, "seed": 518, "has_kick": True, "has_hat": False, "warm": True, "arp_step_mult": 1.0, "target_rms": 0.13,
        "chords": [([220.00, 261.63, 329.63, 392.00], 110.00), ([196.00, 233.08, 293.66, 349.23], 98.00)],
        "melody_notes": [587.33, 523.25, 440.00, 392.00, 440.00, 523.25],
    },
    {
        "id": "bgm_lofi_vinyl_sunday.wav",
        "label": "💿 [Lo-Fi] Chủ Nhật Đĩa Than (87 BPM · Cổ điển)",
        "bpm": 87.0, "seed": 519, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.14,
        "chords": [([146.83, 174.61, 220.00, 261.63], 73.42), ([196.00, 246.94, 293.66, 349.23], 98.00), ([130.81, 164.81, 196.00, 246.94], 65.41)],
        "melody_notes": [523.25, 587.33, 659.25, 523.25, 440.00, 392.00],
    },
    {
        "id": "bgm_jazz_evening_lounge.wav",
        "label": "🎷 [Jazz] Lounge Buổi Tối (92 BPM · Sang trọng)",
        "bpm": 92.0, "seed": 520, "has_kick": False, "has_hat": True, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.14,
        "chords": [([164.81, 196.00, 246.94, 293.66], 82.41), ([220.00, 277.18, 329.63, 392.00], 110.00), ([146.83, 174.61, 220.00, 261.63], 73.42)],
        "melody_notes": [659.25, 587.33, 523.25, 493.88, 392.00, 440.00],
    },
    # --- Review & Lifestyle Hiện Đại ---
    {
        "id": "bgm_lifestyle_clean_morning.wav",
        "label": "🏡 [Lifestyle] Nhà Gọn Sáng Nay (100 BPM · Tinh tươm)",
        "bpm": 100.0, "seed": 521, "has_kick": True, "has_hat": False, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.15,
        "chords": [([261.63, 329.63, 392.00], 130.81), ([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31)],
        "melody_notes": [523.25, 659.25, 783.99, 659.25, 523.25, 440.00],
    },
    {
        "id": "bgm_lifestyle_kitchen_vibe.wav",
        "label": "🍳 [Lifestyle] Góc Bếp Thơm Lừng (104 BPM · Ấm cúng)",
        "bpm": 104.0, "seed": 522, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.15,
        "chords": [([196.00, 246.94, 293.66], 98.00), ([261.63, 329.63, 392.00], 130.81), ([146.83, 185.00, 220.00], 73.42)],
        "melody_notes": [392.00, 493.88, 587.33, 659.25, 587.33, 493.88],
    },
    {
        "id": "bgm_lifestyle_fashion_walk.wav",
        "label": "👗 [Lifestyle] Sải Bước Phố Chiều (112 BPM · Thời trang)",
        "bpm": 112.0, "seed": 523, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.17,
        "chords": [([220.00, 261.63, 329.63], 110.00), ([164.81, 196.00, 246.94], 82.41), ([196.00, 246.94, 293.66], 98.00)],
        "melody_notes": [440.00, 523.25, 659.25, 783.99, 659.25, 587.33],
    },
    {
        "id": "bgm_lifestyle_unbox_clean.wav",
        "label": "📦 [Review] Mở Hộp Tinh Tế (108 BPM · Sạch sẽ)",
        "bpm": 108.0, "seed": 524, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.16,
        "chords": [([293.66, 349.23, 440.00], 146.83), ([261.63, 329.63, 392.00], 130.81), ([233.08, 293.66, 349.23], 116.54)],
        "melody_notes": [587.33, 698.46, 880.00, 698.46, 587.33, 523.25],
    },
    {
        "id": "bgm_lifestyle_skincare_silk.wav",
        "label": "🧴 [Review] Chăm Da Dịu Êm (90 BPM · Mềm mại)",
        "bpm": 90.0, "seed": 525, "has_kick": False, "has_hat": False, "warm": True, "arp_step_mult": 0.75, "target_rms": 0.13,
        "chords": [([246.94, 311.13, 369.99, 440.00], 123.47), ([220.00, 277.18, 329.63, 392.00], 110.00)],
        "melody_notes": [659.25, 587.33, 493.88, 440.00, 493.88, 554.37],
    },
    # --- TikTok Sôi Động & Chốt Đơn ---
    {
        "id": "bgm_tiktok_mega_deal.wav",
        "label": "🛍️ [TikTok] Mega Deal Bùng Nổ (128 BPM · Cực cháy)",
        "bpm": 128.0, "seed": 526, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.19,
        "chords": [([130.81, 155.56, 196.00], 65.41), ([146.83, 174.61, 220.00], 73.42), ([164.81, 196.00, 246.94], 82.41)],
        "melody_notes": [523.25, 622.25, 783.99, 932.33, 783.99, 622.25],
    },
    {
        "id": "bgm_tiktok_dance_bounce.wav",
        "label": "💃 [TikTok] Bounce Bắt Tai (124 BPM · Nhún nhảy)",
        "bpm": 124.0, "seed": 527, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.18,
        "chords": [([196.00, 246.94, 293.66], 98.00), ([164.81, 196.00, 246.94], 82.41), ([174.61, 220.00, 261.63], 87.31)],
        "melody_notes": [587.33, 783.99, 659.25, 587.33, 493.88, 587.33],
    },
    {
        "id": "bgm_tiktok_future_bass.wav",
        "label": "🚀 [TikTok] Future Bass Viral (130 BPM · Hiện đại)",
        "bpm": 130.0, "seed": 528, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.18,
        "chords": [([174.61, 220.00, 261.63, 329.63], 87.31), ([196.00, 246.94, 293.66, 369.99], 98.00)],
        "melody_notes": [698.46, 783.99, 880.00, 783.99, 659.25, 523.25],
    },
    {
        "id": "bgm_tiktok_electro_pop.wav",
        "label": "⚡ [TikTok] Electro Pop Sáng (120 BPM · Tươi trẻ)",
        "bpm": 120.0, "seed": 529, "has_kick": True, "has_hat": True, "warm": False, "arp_step_mult": 0.5, "target_rms": 0.18,
        "chords": [([261.63, 329.63, 392.00], 130.81), ([293.66, 369.99, 440.00], 146.83), ([220.00, 277.18, 329.63], 110.00)],
        "melody_notes": [523.25, 659.25, 783.99, 880.00, 783.99, 659.25],
    },
    {
        "id": "bgm_tiktok_retro_synth.wav",
        "label": "🕹️ [TikTok] Retro Synthwave 80s (116 BPM · Nổi bật)",
        "bpm": 116.0, "seed": 530, "has_kick": True, "has_hat": True, "warm": True, "arp_step_mult": 0.5, "target_rms": 0.17,
        "chords": [([220.00, 261.63, 329.63], 110.00), ([174.61, 220.00, 261.63], 87.31), ([196.00, 246.94, 293.66], 98.00), ([164.81, 196.00, 246.94], 82.41)],
        "melody_notes": [440.00, 659.25, 587.33, 523.25, 493.88, 440.00],
    },
]

BGM_TRACK_CATALOG.extend({"id": p["id"], "label": p["label"]} for p in _EXTRA_BGM_PRESETS)

CUSTOM_BGM_META_FILE = DIR_BGM / "custom_bgm_meta.json"

BGM_MOOD_PRESETS: dict[str, dict[str, Any]] = {
    "review_upbeat": {
        "id": "review_upbeat",
        "label": "🛍️ Review Sản phẩm / Unbox Sạch sẽ",
        "vibes": ["learned_dna", "creative_internet", "daily_story"],
        "pacing": "auto",
    },
    "tiktok_sale": {
        "id": "tiktok_sale",
        "label": "⚡ Săn Deal / Flash Sale Bùng nổ",
        "vibes": ["creative_internet", "learned_dna"],
        "pacing": "fast",
    },
    "comedy_pov": {
        "id": "comedy_pov",
        "label": "😂 POV Hài hước / Tấu hài Dí dỏm",
        "vibes": ["pov_comedy", "creative_internet"],
        "pacing": "fast",
    },
    "detective_mystery": {
        "id": "detective_mystery",
        "label": "🕵️ Thám tử / Bí ẩn / Soi chi tiết",
        "vibes": ["detective_mystery"],
        "pacing": "auto",
    },
    "field_report": {
        "id": "field_report",
        "label": "🎙️ Phóng sự / Tin nóng Hiện trường",
        "vibes": ["field_report"],
        "pacing": "fast",
    },
    "vlog_acoustic": {
        "id": "vlog_acoustic",
        "label": "🏕️ Vlog Dã ngoại / Acoustic Ấm áp",
        "vibes": ["outdoor_picnic", "daily_story"],
        "pacing": "chill",
    },
    "travel_adventure": {
        "id": "travel_adventure",
        "label": "✈️ Du lịch / Phiêu lưu Phóng khoáng",
        "vibes": ["travel_vlog", "outdoor_picnic"],
        "pacing": "auto",
    },
    "cafe_chill": {
        "id": "cafe_chill",
        "label": "🍜 Ẩm thực / Cafe / Lo-Fi Thư giãn",
        "vibes": ["food_cafe", "daily_story"],
        "pacing": "chill",
    },
    "cinema_piano": {
        "id": "cinema_piano",
        "label": "🎬 Điện ảnh / Piano Sâu lắng Cảm xúc",
        "vibes": ["cinematic_deep", "daily_story"],
        "pacing": "chill",
    },
}

CC0_BGM_CATALOG: list[dict[str, Any]] = [
    {
        "id": "cc0_review_upbeat_clean.mp3",
        "label": "🌟 [CC0 Nhạc Thật] Review Tươi Sáng Sạch Sẽ (Upbeat Pop)",
        "mood": "review_upbeat",
        "vibes": ["learned_dna", "daily_story", "outdoor_picnic"],
        "pacing": "auto",
        "keywords": ["review", "unbox", "mở hộp", "sạch", "tươi", "gọn", "skincare", "gia dụng", "mẹo", "chăm sóc"],
        "is_real": True,
    },
    {
        "id": "cc0_tiktok_electronic_beat.mp3",
        "label": "⚡ [CC0 Nhạc Thật] TikTok Săn Deal Điện Tử (Electronic Beat)",
        "mood": "tiktok_sale",
        "vibes": ["creative_internet", "learned_dna"],
        "pacing": "fast",
        "keywords": ["deal", "sale", "giảm giá", "giỏ hàng", "chốt đơn", "voucher", "freeship", "bùng nổ", "sốc", "rẻ"],
        "is_real": True,
    },
    {
        "id": "cc0_comedy_pov_mischief.mp3",
        "label": "😂 [CC0 Nhạc Thật] POV Hài Hước Tinh Nghịch (Mischief)",
        "mood": "comedy_pov",
        "vibes": ["pov_comedy", "creative_internet"],
        "pacing": "fast",
        "keywords": ["hài", "cười", "tấu", "bất ngờ", "ngáo", "trời ơi", "lầy", "troll", "pov", "bạn thân"],
        "is_real": True,
    },
    {
        "id": "cc0_comedy_light_quirky.mp3",
        "label": "😜 [CC0 Nhạc Thật] Đời Thường Vui Nhộn Dí Dỏm (Quirky)",
        "mood": "comedy_pov",
        "vibes": ["pov_comedy", "daily_story", "food_cafe"],
        "pacing": "auto",
        "keywords": ["vui", "dí dỏm", "dễ thương", "bé", "ăn vặt", "nhí nhảnh", "tò mò", "sinh nhật"],
        "is_real": True,
    },
    {
        "id": "cc0_detective_heist_mystery.mp3",
        "label": "🕵️ [CC0 Nhạc Thật] Thám Tử Bí Ẩn Soi Manh Mối (Heist Mystery)",
        "mood": "detective_mystery",
        "vibes": ["detective_mystery", "field_report"],
        "pacing": "auto",
        "keywords": ["bí ẩn", "manh mối", "thám tử", "nghi", "phát hiện", "soi", "sự thật", "lộ", "ẩn số", "tò mò"],
        "is_real": True,
    },
    {
        "id": "cc0_news_field_report.mp3",
        "label": "🎙️ [CC0 Nhạc Thật] Phóng Sự Hiện Trường Tin Nóng (News Beat)",
        "mood": "field_report",
        "vibes": ["field_report", "detective_mystery"],
        "pacing": "fast",
        "keywords": ["hiện trường", "phóng sự", "khẩn", "cảnh báo", "tin", "thực tế", "kiểm chứng", "bóc phốt", "sự cố"],
        "is_real": True,
    },
    {
        "id": "cc0_action_city_run.mp3",
        "label": "🔥 [CC0 Nhạc Thật] Nhịp Nhanh Kịch Tính Cao Trào (City Run)",
        "mood": "tiktok_sale",
        "vibes": ["field_report", "creative_internet", "travel_vlog"],
        "pacing": "turbo",
        "keywords": ["nhanh", "gấp", "chạy", "đua", "cao trào", "kịch tính", "cực", "đỉnh", "test", "so sánh"],
        "is_real": True,
    },
    {
        "id": "cc0_vlog_slice_of_life.mp3",
        "label": "🌿 [CC0 Nhạc Thật] Nhật Ký Đời Thường Nhẹ Nhàng (Slice of Life)",
        "mood": "vlog_acoustic",
        "vibes": ["daily_story", "outdoor_picnic", "learned_dna"],
        "pacing": "chill",
        "keywords": ["nhật ký", "một ngày", "cuối tuần", "gia đình", "bình yên", "trải nghiệm", "kể", "chia sẻ"],
        "is_real": True,
    },
    {
        "id": "cc0_camping_bonfire_acoustic.mp3",
        "label": "🏕️ [CC0 Nhạc Thật] Dã Ngoại Lửa Trại Mộc Mạc (Bonfire)",
        "mood": "vlog_acoustic",
        "vibes": ["outdoor_picnic", "travel_vlog"],
        "pacing": "chill",
        "keywords": ["cắm trại", "camping", "picnic", "lửa trại", "rừng", "biển", "nướng", "thiên nhiên", "ngoài trời"],
        "is_real": True,
    },
    {
        "id": "cc0_travel_adventure.mp3",
        "label": "✈️ [CC0 Nhạc Thật] Du Lịch Phiêu Lưu Hào Hứng (Adventure)",
        "mood": "travel_adventure",
        "vibes": ["travel_vlog", "outdoor_picnic"],
        "pacing": "auto",
        "keywords": ["du lịch", "chuyến đi", "khám phá", "hành trình", "cảnh đẹp", "đường", "núi", "bay", "check-in"],
        "is_real": True,
    },
    {
        "id": "cc0_cafe_food_chill.mp3",
        "label": "☕ [CC0 Nhạc Thật] Ẩm Thực Quán Cafe Thư Thái (Baguette Chill)",
        "mood": "cafe_chill",
        "vibes": ["food_cafe", "daily_story"],
        "pacing": "chill",
        "keywords": ["quán", "cafe", "cà phê", "món ăn", "ngon", "bếp", "nấu", "chill", "trà", "bánh", "ăn"],
        "is_real": True,
    },
    {
        "id": "cc0_cinema_lovely_piano.mp3",
        "label": "🎬 [CC0 Nhạc Thật] Điện Ảnh Piano Sâu Lắng (Lovely Piano)",
        "mood": "cinema_piano",
        "vibes": ["cinematic_deep", "daily_story"],
        "pacing": "chill",
        "keywords": ["cảm xúc", "kỷ niệm", "tâm sự", "sâu lắng", "đêm", "hoàng hôn", "điện ảnh", "nhớ", "trân trọng"],
        "is_real": True,
    },
]

_SYNTH_HINTS: dict[str, tuple[str, list[str], str]] = {
    "bgm_upbeat_tiktok.wav": ("review_upbeat", ["learned_dna", "creative_internet"], "auto"),
    "bgm_chill_lofi.wav": ("cafe_chill", ["food_cafe", "daily_story"], "chill"),
    "bgm_flash_sale.wav": ("tiktok_sale", ["creative_internet"], "fast"),
    "bgm_acoustic_warm.wav": ("vlog_acoustic", ["outdoor_picnic", "daily_story", "learned_dna"], "chill"),
    "bgm_funky_groove.wav": ("comedy_pov", ["pov_comedy", "food_cafe"], "fast"),
    "bgm_tech_minimal.wav": ("review_upbeat", ["learned_dna", "field_report"], "auto"),
    "bgm_luxury_piano.wav": ("cinema_piano", ["cinematic_deep", "daily_story"], "chill"),
    "bgm_trap_hype.wav": ("tiktok_sale", ["creative_internet"], "turbo"),
    "bgm_bossa_cafe.wav": ("cafe_chill", ["food_cafe"], "chill"),
    "bgm_kpop_sparkle.wav": ("tiktok_sale", ["creative_internet", "pov_comedy"], "fast"),
    "bgm_cyber_pulse.wav": ("field_report", ["detective_mystery", "field_report"], "fast"),
    "bgm_happy_ukulele.wav": ("comedy_pov", ["outdoor_picnic", "pov_comedy", "daily_story"], "auto"),
    "bgm_cinematic_rise.wav": ("cinema_piano", ["cinematic_deep"], "chill"),
    "bgm_tropical_house.wav": ("travel_adventure", ["travel_vlog", "outdoor_picnic"], "auto"),
    "bgm_deep_focus.wav": ("detective_mystery", ["detective_mystery", "cinematic_deep"], "chill"),
    "bgm_tiktok_retro_synth.wav": ("detective_mystery", ["detective_mystery", "field_report"], "auto"),
    "bgm_tiktok_dance_bounce.wav": ("comedy_pov", ["pov_comedy", "creative_internet"], "fast"),
    "bgm_piano_midnight_letters.wav": ("cinema_piano", ["cinematic_deep", "daily_story"], "chill"),
    "bgm_vlog_campfire_guitar.wav": ("vlog_acoustic", ["outdoor_picnic", "travel_vlog"], "chill"),
    "bgm_vlog_weekend_picnic.wav": ("vlog_acoustic", ["outdoor_picnic"], "auto"),
    "bgm_travel_coastal_drive.wav": ("travel_adventure", ["travel_vlog"], "auto"),
    "bgm_lifestyle_unbox_clean.wav": ("review_upbeat", ["learned_dna"], "auto"),
    "bgm_lifestyle_skincare_silk.wav": ("review_upbeat", ["learned_dna", "cinematic_deep"], "chill"),
    "bgm_lifestyle_kitchen_vibe.wav": ("cafe_chill", ["food_cafe"], "auto"),
}


def load_custom_bgm_meta() -> dict[str, dict[str, Any]]:
    import json

    if not CUSTOM_BGM_META_FILE.exists():
        return {}
    try:
        data = json.loads(CUSTOM_BGM_META_FILE.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_custom_bgm_meta(meta: dict[str, dict[str, Any]]) -> None:
    import json

    DIR_BGM.mkdir(parents=True, exist_ok=True)
    CUSTOM_BGM_META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def register_custom_bgm(filename: str, label: str = "", mood: str = "review_upbeat") -> dict[str, Any]:
    fname = Path(filename).name
    m_key = mood if mood in BGM_MOOD_PRESETS else "review_upbeat"
    m_info = BGM_MOOD_PRESETS[m_key]
    clean_lbl = (label or "").strip() or Path(fname).stem.replace("custom_", "").replace("_", " ").strip()
    entry = {
        "id": fname,
        "label": f"⭐ [Nhạc Của Tôi] {clean_lbl}",
        "mood": m_key,
        "vibes": list(m_info.get("vibes") or ["learned_dna"]),
        "pacing": str(m_info.get("pacing") or "auto"),
    }
    meta = load_custom_bgm_meta()
    meta[fname] = entry
    save_custom_bgm_meta(meta)
    return entry


def delete_custom_bgm(filename: str) -> bool:
    fname = Path(filename).name
    if not fname.startswith("custom_"):
        return False
    p = DIR_BGM / fname
    removed = False
    if p.exists() and p.is_file():
        p.unlink()
        removed = True
    meta = load_custom_bgm_meta()
    if fname in meta:
        meta.pop(fname, None)
        save_custom_bgm_meta(meta)
        removed = True
    return removed


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
    for preset in _EXTRA_BGM_PRESETS:
        builders[preset["id"]] = lambda p, pr=preset: _synth_styled_bgm(
            p,
            bpm=pr["bpm"],
            seed=pr["seed"],
            has_kick=pr["has_kick"],
            has_hat=pr["has_hat"],
            warm=pr["warm"],
            arp_step_mult=pr["arp_step_mult"],
            target_rms=pr["target_rms"],
            chords=pr["chords"],
            melody_notes=pr["melody_notes"],
        )
    for fname, fn in builders.items():
        p = DIR_BGM / fname
        if force or not p.exists() or p.stat().st_size < 100_000:
            fn(p)

    out: list[dict[str, Any]] = []
    known_synth = {item["id"]: item["label"] for item in BGM_TRACK_CATALOG}
    cc0_map = {item["id"]: item for item in CC0_BGM_CATALOG}
    custom_meta = load_custom_bgm_meta()

    for p in sorted(DIR_BGM.iterdir()):
        if not (p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".m4a")):
            continue
        fname = p.name
        if fname in custom_meta:
            cm = custom_meta[fname]
            out.append(
                {
                    "id": fname,
                    "label": str(cm.get("label") or f"⭐ [Nhạc Của Tôi] {fname}"),
                    "url": f"/files/06_assets_audio/bgm/{fname}",
                    "is_custom": True,
                    "is_real": True,
                    "mood": str(cm.get("mood") or "review_upbeat"),
                    "vibes": list(cm.get("vibes") or ["learned_dna"]),
                    "pacing": str(cm.get("pacing") or "auto"),
                    "keywords": [],
                }
            )
        elif fname.startswith("custom_"):
            out.append(
                {
                    "id": fname,
                    "label": f"⭐ [Nhạc Của Tôi] {p.stem.replace('custom_', '').replace('_', ' ')}",
                    "url": f"/files/06_assets_audio/bgm/{fname}",
                    "is_custom": True,
                    "is_real": True,
                    "mood": "review_upbeat",
                    "vibes": ["learned_dna"],
                    "pacing": "auto",
                    "keywords": [],
                }
            )
        elif fname in cc0_map:
            cm = cc0_map[fname]
            out.append(
                {
                    "id": fname,
                    "label": cm["label"],
                    "url": f"/files/06_assets_audio/bgm/{fname}",
                    "is_custom": False,
                    "is_real": True,
                    "mood": cm["mood"],
                    "vibes": list(cm["vibes"]),
                    "pacing": cm["pacing"],
                    "keywords": list(cm.get("keywords") or []),
                }
            )
        else:
            s_hint = _SYNTH_HINTS.get(fname)
            out.append(
                {
                    "id": fname,
                    "label": known_synth.get(fname, f"🎶 {fname}"),
                    "url": f"/files/06_assets_audio/bgm/{fname}",
                    "is_custom": False,
                    "is_real": fname.endswith(".mp3"),
                    "mood": s_hint[0] if s_hint else "review_upbeat",
                    "vibes": list(s_hint[1]) if s_hint else ["learned_dna"],
                    "pacing": s_hint[2] if s_hint else "auto",
                    "keywords": [],
                }
            )

    cc0_order = {item["id"]: i for i, item in enumerate(CC0_BGM_CATALOG)}
    synth_order = {item["id"]: i for i, item in enumerate(BGM_TRACK_CATALOG)}

    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        if item.get("is_custom"):
            return (0, 0, item["id"])
        if item["id"] in cc0_order:
            return (1, cc0_order[item["id"]], item["id"])
        if item.get("is_real"):
            return (1, 50, item["id"])
        return (2, synth_order.get(item["id"], 999), item["id"])

    out.sort(key=_sort_key)
    return out


def select_ai_bgm_track(
    *,
    script_text: str = "",
    content_vibe: str = "learned_dna",
    pacing_preset: str = "auto",
    pipeline_category: str = "short_tiktok",
    title: str = "",
    product_note: str = "",
    recent_tracks: list[str] | None = None,
    gemini_api_key: str = "",
    agy_caller: Any = None,
) -> dict[str, Any]:
    """Select the best matching BGM track using Tier 1 AI (optional) + Tier 2 scored heuristic."""
    import json
    import re
    import urllib.request

    tracks = ensure_royalty_free_bgm_library()
    if not tracks:
        return {"track_id": "bgm_upbeat_tiktok.wav", "label": "Default", "source": "heuristic", "reason": "Kho nhạc trống."}

    track_map = {t["id"]: t for t in tracks}
    vibe_clean = str(content_vibe or "learned_dna").strip() or "learned_dna"
    pacing_clean = str(pacing_preset or "auto").strip().lower() or "auto"
    recent_list = [str(x).strip() for x in (recent_tracks or []) if str(x).strip()]
    recent_top = recent_list[:2]

    text_blob = f"{title} {product_note} {script_text}".lower()

    vibe_mood_pref: dict[str, list[str]] = {
        "learned_dna": ["review_upbeat", "tiktok_sale", "comedy_pov"],
        "creative_internet": ["tiktok_sale", "comedy_pov", "review_upbeat"],
        "pov_comedy": ["comedy_pov", "tiktok_sale"],
        "detective_mystery": ["detective_mystery", "field_report"],
        "field_report": ["field_report", "detective_mystery", "tiktok_sale"],
        "outdoor_picnic": ["vlog_acoustic", "travel_adventure"],
        "travel_vlog": ["travel_adventure", "vlog_acoustic"],
        "food_cafe": ["cafe_chill", "comedy_pov"],
        "daily_story": ["vlog_acoustic", "review_upbeat", "cinema_piano"],
        "cinematic_deep": ["cinema_piano", "vlog_acoustic"],
    }

    scored: list[tuple[float, dict[str, Any], str]] = []
    pref_moods = vibe_mood_pref.get(vibe_clean, ["review_upbeat"])
    for t in tracks:
        score = 0.0
        reasons: list[str] = []
        if t.get("is_custom"):
            score += 5.0
            reasons.append("nhạc tự upload")
        elif t.get("is_real"):
            score += 4.0
            reasons.append("CC0 nhạc thật")

        t_vibes = t.get("vibes") or []
        if vibe_clean in t_vibes:
            score += 4.5
            reasons.append(f"khớp vibe {vibe_clean}")
        elif t.get("mood") in pref_moods:
            idx_m = pref_moods.index(t["mood"])
            score += max(1.5, 3.5 - idx_m * 0.8)

        t_pac = str(t.get("pacing") or "auto")
        if pacing_clean != "auto" and t_pac == pacing_clean:
            score += 2.2
            reasons.append(f"khớp nhịp {pacing_clean}")
        elif pacing_clean == "auto" and pipeline_category == "long_vlog" and t_pac in ("chill", "auto"):
            score += 1.0
        elif pacing_clean == "auto" and pipeline_category != "long_vlog" and t_pac in ("fast", "auto"):
            score += 1.0

        kw_hits = [kw for kw in (t.get("keywords") or []) if kw in text_blob]
        if kw_hits:
            score += min(3.6, len(kw_hits) * 1.2)
            reasons.append(f"khớp từ khóa ({', '.join(kw_hits[:2])})")

        if any(w in text_blob for w in ("deal", "sale", "giảm giá", "freeship", "chốt đơn", "voucher")):
            if t.get("mood") == "tiktok_sale":
                score += 2.5
        elif any(w in text_blob for w in ("bí ẩn", "manh mối", "thám tử", "kiểm chứng")):
            if t.get("mood") in ("detective_mystery", "field_report"):
                score += 2.5
        elif any(w in text_blob for w in ("hài", "cười", "pov", "troll")):
            if t.get("mood") == "comedy_pov":
                score += 2.5

        if t["id"] in recent_top:
            score -= 3.8

        reason_str = ", ".join(reasons) if reasons else "cân bằng tổng thể"
        scored.append((score, t, reason_str))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_h = scored[0][1]
    best_h_reason = scored[0][2]

    has_ai = bool(agy_caller or str(gemini_api_key or "").strip())
    if has_ai and text_blob.strip():
        custom_cands = [t for t in tracks if t.get("is_custom")]
        cc0_cands = [t for t in tracks if not t.get("is_custom") and t.get("is_real")]
        synth_top = [x[1] for x in scored if not x[1].get("is_real")][:6]
        seen_ids: set[str] = set()
        candidates: list[dict[str, Any]] = []
        for t in [*custom_cands, *cc0_cands, *synth_top]:
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                candidates.append(t)

        cand_lines = "\n".join(
            f"- {t['id']} | {t['label']} | mood={t.get('mood')} | vibes={','.join(t.get('vibes') or [])} | pacing={t.get('pacing')}"
            for t in candidates
        )
        avoid_txt = f"Tránh chọn lại các bài vừa dùng gần đây nếu có lựa chọn phù hợp khác: {', '.join(recent_top)}." if recent_top else ""
        prompt = (
            "Bạn là Đạo diễn Âm nhạc cho video TikTok/Vlog.\n"
            "Hãy chọn 1 track_id nhạc nền phù hợp NHẤT với nội dung dưới đây.\n"
            f"- Định dạng: {'Video Dài Vlog' if pipeline_category == 'long_vlog' else 'Video Ngắn TikTok'}\n"
            f"- Vibe: {vibe_clean} | Tiết tấu: {pacing_clean}\n"
            f"- Tiêu đề / Note: {(title + ' ' + product_note).strip()[:300]}\n"
            f"- Trích đoạn Kịch bản: {script_text.strip()[:900]}\n"
            f"{avoid_txt}\n\n"
            "Ưu tiên nhạc [Nhạc Của Tôi] hoặc [CC0 Nhạc Thật] nếu hợp mood.\n"
            f"Danh sách ứng viên:\n{cand_lines}\n\n"
            'Chỉ trả về JSON thuần: {"track_id": "<đúng id ở trên>", "reason": "<lý do ngắn tiếng Việt tối đa 18 từ>"}'
        )

        raw_resp = ""
        if agy_caller:
            try:
                raw_resp = str(agy_caller(prompt) or "")
            except Exception:
                raw_resp = ""
        if not raw_resp and str(gemini_api_key or "").strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key.strip()}"
                payload = json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"},
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    raw_resp = (
                        ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
                    )[0].get("text", "")
            except Exception:
                raw_resp = ""

        if raw_resp:
            m = re.search(r"\{.*\}", raw_resp, flags=re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    picked_id = Path(str(parsed.get("track_id") or "")).name
                    if picked_id in track_map:
                        return {
                            "track_id": picked_id,
                            "label": track_map[picked_id]["label"],
                            "source": "ai",
                            "reason": str(parsed.get("reason") or "AI chọn theo kịch bản & vibe").strip()[:140],
                        }
                except Exception:
                    pass

    return {
        "track_id": best_h["id"],
        "label": best_h["label"],
        "source": "heuristic",
        "reason": best_h_reason,
    }


if __name__ == "__main__":
    tracks = ensure_royalty_free_bgm_library(force=True)
    print("Generated BGM library:", [t["id"] for t in tracks])
