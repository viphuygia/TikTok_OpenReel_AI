#!/usr/bin/env python3
"""
Engine nhân bản giọng nói tiếng Việt (F5-TTS Vietnamese) & tạo phụ đề từng mili-giây (Faster-Whisper).

Quy trình:
1. Tự động chuẩn hóa file giọng mẫu (03_voice_clone/giong_mau.*) về Mono, 24000Hz, cắt khoảng lặng thừa.
2. Đọc văn bản tham chiếu từ 03_voice_clone/noi_dung_giong_mau.txt (tự nhận diện nếu chưa có).
3. Chuẩn hóa văn bản kịch bản mới (phiên âm từ tiếng Anh TikTok Shop, chuẩn hóa số/ký tự, chữ thường).
4. Tổng hợp giọng đọc nhân bản bằng F5-TTS (hynt/F5-TTS-Vietnamese) -> 04_workspace/ready_for_openreel/02_giong_doc_ai.wav.
5. Giải phóng VRAM và chạy Faster-Whisper (word_timestamps=True) -> 04_workspace/ready_for_openreel/03_phu_de.srt.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from project_manager import get_project_root
from style_dna import (
    FILE_VOICE_BEATS,
    HALLUCINATION_RE,
    load_brand_brief,
    repair_subtitles_and_beats,
    restore_display_text,
)

DEFAULT_MODEL_CKPT = PROJECT_ROOT / "03_voice_clone" / "model" / "model_last.pt"
DEFAULT_VOCAB_FILE = PROJECT_ROOT / "03_voice_clone" / "model" / "vocab.txt"
DEFAULT_REF_TEXT_FILE = PROJECT_ROOT / "03_voice_clone" / "model" / "noi_dung_giong_mau.txt"
FALLBACK_REF_TEXT_FILE = PROJECT_ROOT / "03_voice_clone" / "noi_dung_giong_mau.txt"
ACTIVE_PROJECT_ROOT = get_project_root()
DEFAULT_SCRIPT_FILE = ACTIVE_PROJECT_ROOT / "04_workspace" / "kich_ban.txt"
DEFAULT_OUT_WAV = ACTIVE_PROJECT_ROOT / "04_workspace" / "ready_for_openreel" / "02_giong_doc_ai.wav"
DEFAULT_OUT_SRT = ACTIVE_PROJECT_ROOT / "04_workspace" / "ready_for_openreel" / "03_phu_de.srt"

SUPPORTED_AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma")

# Bảng phiên âm các từ tiếng Anh TikTok Shop phổ biến sang cách đọc tiếng Việt cho F5-TTS
ENGLISH_PHONETIC_MAP: list[tuple[str, str]] = [
    (r"\bhead\s*(?:&|and)\s*shoulders\b", "hét en sâu đơ"),
    (r"\bniacinamide\b", "ni a xi na mai"),
    (r"\bmenthol\b", "men thô"),
    (r"\b5\s*in\s*1\b", "năm trong một"),
    (r"\b5in1\b", "năm trong một"),
    (r"\btonic\b", "tô ních"),
    (r"\bleave[- ]on\b", "líp on"),
    (r"\b(\d+)\s*ml\b", r"\1 mi li lít"),
    (r"\bfreeship\s+xtra\b", "phờ ri síp ích tra"),
    (r"\bfree\s*ship\b", "phờ ri síp"),
    (r"\bflash\s*sale\b", "phờ lát sêu"),
    (r"\bbest\s*seller\b", "bét seo lơ"),
    (r"\blive\s*stream\b", "lai trym"),
    (r"\btik\s*tok\s*shop\b", "tích tóc sóp"),
    (r"\btik\s*tok\b", "tích tóc"),
    (r"\bvoucher\b", "vao chờ"),
    (r"\bfeedback\b", "phít bách"),
    (r"\bskincare\b", "xì kin ke"),
    (r"\bmakeup\b", "mếch ắp"),
    (r"\bunbox\b", "ăn bóc"),
    (r"\breview\b", "ri viu"),
    (r"\bcomment\b", "com men"),
    (r"\bfollow\b", "pho lâu"),
    (r"\binbox\b", "in bóc"),
    (r"\border\b", "o đờ"),
    (r"\bcombo\b", "com bo"),
    (r"\bserum\b", "xê rum"),
    (r"\btoner\b", "tô nơ"),
    (r"\bcheck\b", "chếch"),
    (r"\bdeal\b", "điu"),
    (r"\bsale\b", "sêu"),
    (r"\bsize\b", "sai"),
    (r"\bform\b", "phom"),
    (r"\blink\b", "linh"),
    (r"\bshop\b", "sóp"),
    (r"\bship\b", "síp"),
    (r"\blive\b", "lai"),
    (r"\bhot\b", "hót"),
    (r"\btop\b", "tóp"),
    (r"\bvip\b", "víp"),
]


def configure_runtime_paths() -> None:
    """Bổ sung đường dẫn FFmpeg (WinGet) và DLL CUDA trên Windows trước khi nạp thư viện."""
    if os.name != "nt":
        return

    extra_dirs: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_dir.exists():
            for pkg in winget_dir.glob("Gyan.FFmpeg*"):
                for exe in pkg.rglob("ffmpeg.exe"):
                    extra_dirs.append(exe.parent)
                    break

    site_pkgs = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    for rel in [Path("torch/lib"), Path("ctranslate2")]:
        p = site_pkgs / rel
        if p.exists():
            extra_dirs.append(p)
    nvidia_dir = site_pkgs / "nvidia"
    if nvidia_dir.exists():
        for bin_dir in nvidia_dir.glob("*/bin"):
            if bin_dir.is_dir():
                extra_dirs.append(bin_dir)

    current_path = os.environ.get("PATH", "")
    for d in extra_dirs:
        s = str(d)
        if s not in current_path:
            current_path = s + os.pathsep + current_path
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(s)
            except OSError:
                pass
    os.environ["PATH"] = current_path


def patch_torchaudio_load() -> None:
    """
    Monkey-patch torchaudio.load dùng soundfile làm fallback an toàn trên Windows
    (tránh lỗi thiếu DLL của torchcodec khi đọc file .wav).
    """
    import soundfile as sf
    import torch
    import torchaudio

    orig_load = torchaudio.load

    def safe_load(uri: Any, *args: Any, **kwargs: Any):
        try:
            return orig_load(uri, *args, **kwargs)
        except Exception:
            data, sr = sf.read(str(uri), dtype="float32", always_2d=True)
            # soundfile trả về (frames, channels) -> chuyển thành (channels, frames)
            tensor = torch.from_numpy(data.T.copy())
            return tensor, sr

    torchaudio.load = safe_load


def find_ref_audio(explicit_path: str | None) -> Path:
    if explicit_path:
        p = Path(explicit_path)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy file giọng mẫu: {p}")
        return p

    for voice_dir in (PROJECT_ROOT / "03_voice_clone" / "model", PROJECT_ROOT / "03_voice_clone"):
        for ext in SUPPORTED_AUDIO_EXTS:
            candidate = voice_dir / f"giong_mau{ext}"
            if candidate.exists():
                return candidate

    raise FileNotFoundError(
        "Không tìm thấy file giọng mẫu 03_voice_clone/model/giong_mau.(wav|mp3|m4a|flac). "
        "Hãy trích xuất hoặc thu âm giọng thật 8-15s trên Dashboard hoặc chép vào 03_voice_clone/model/giong_mau.wav."
    )


def normalize_reference_audio(src_audio: Path, dst_wav: Path) -> tuple[Path, bool]:
    """
    Chuẩn hóa file giọng mẫu về Mono, 24000Hz, 16-bit PCM, lọc tạp âm nhẹ (highpass 80Hz + loudnorm)
    và cắt khoảng lặng thừa để F5-TTS bám sát âm sắc gốc nhất.
    Trả về (đường dẫn file wav chuẩn hóa, đã bị cắt ngắn từ file >12s hay chưa).
    """
    from pydub import AudioSegment, silence

    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    cleaned_tmp = dst_wav.with_name(f"{dst_wav.stem}_ffclean.wav")
    ffmpeg_exe = shutil.which("ffmpeg")
    load_path = src_audio
    if ffmpeg_exe:
        try:
            subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-i",
                    str(src_audio),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-af",
                    "highpass=f=80,lowpass=f=11000,loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a",
                    "pcm_s16le",
                    str(cleaned_tmp),
                ],
                capture_output=True,
                check=True,
            )
            if cleaned_tmp.exists() and cleaned_tmp.stat().st_size > 1000:
                load_path = cleaned_tmp
        except Exception:
            load_path = src_audio

    audio = AudioSegment.from_file(str(load_path))
    if cleaned_tmp.exists():
        try:
            cleaned_tmp.unlink()
        except Exception:
            pass
    audio = audio.set_channels(1).set_frame_rate(24000).set_sample_width(2)

    # Cắt khoảng lặng ở đầu và cuối
    thresh = min(-40.0, audio.dBFS - 16.0) if audio.dBFS != float("-inf") else -42.0
    lead = silence.detect_leading_silence(audio, silence_threshold=thresh)
    audio = audio[lead:]
    trail = silence.detect_leading_silence(audio.reverse(), silence_threshold=thresh)
    if trail > 0 and trail < len(audio):
        audio = audio[: len(audio) - trail]

    was_clipped = False
    if len(audio) > 12000:
        # F5-TTS bám âm sắc chuẩn nhất với đoạn mẫu sạch 6-11s
        chunks = silence.split_on_silence(
            audio,
            min_silence_len=350,
            silence_thresh=thresh,
            keep_silence=180,
            seek_step=10,
        )
        merged = AudioSegment.silent(duration=0, frame_rate=24000)
        for seg in chunks:
            if len(merged) >= 6000 and len(merged) + len(seg) > 11000:
                break
            merged += seg
        if len(merged) < 4000:
            merged = audio[:11000]
        audio = merged
        was_clipped = True

    audio = audio + AudioSegment.silent(duration=50, frame_rate=24000)
    audio.export(str(dst_wav), format="wav")
    return dst_wav, was_clipped


def patch_av_open() -> None:
    """Đảm bảo av.open tương thích giữa faster-whisper và PyAV >= 17 (bỏ metadata_errors)."""
    import av

    if getattr(av.open, "_tiktok_patched", False):
        return
    orig_open = av.open

    def compat_open(*args: Any, **kwargs: Any):
        try:
            return orig_open(*args, **kwargs)
        except TypeError:
            kwargs.pop("metadata_errors", None)
            return orig_open(*args, **kwargs)

    compat_open._tiktok_patched = True  # type: ignore[attr-defined]
    av.open = compat_open


def load_whisper(model_size: str):
    patch_av_open()
    from faster_whisper import WhisperModel

    use_cuda = False
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            use_cuda = True
    except Exception:
        use_cuda = False

    if use_cuda:
        for compute_type in ("float16", "int8_float16", "int8"):
            try:
                return WhisperModel(model_size, device="cuda", compute_type=compute_type)
            except Exception:
                pass
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_audio_text(wav_path: Path, model_size: str = "small") -> str:
    model = load_whisper(model_size)
    segments, _ = model.transcribe(
        str(wav_path), language="vi", beam_size=5, vad_filter=True
    )
    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
    del model
    gc.collect()
    return text.strip()


_DIGITS_VI = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_three_digits(num: int, full: bool = False) -> str:
    hundreds = num // 100
    tens = (num % 100) // 10
    units = num % 10
    parts: list[str] = []

    if hundreds > 0 or full:
        parts.append(f"{_DIGITS_VI[hundreds]} trăm")
        if tens == 0 and units > 0:
            parts.append("lẻ")

    if tens > 1:
        parts.append(f"{_DIGITS_VI[tens]} mươi")
        if units == 1:
            parts.append("mốt")
        elif units == 4:
            parts.append("tư")
        elif units == 5:
            parts.append("lăm")
        elif units > 0:
            parts.append(_DIGITS_VI[units])
    elif tens == 1:
        parts.append("mười")
        if units == 5:
            parts.append("lăm")
        elif units > 0:
            parts.append(_DIGITS_VI[units])
    elif units > 0:
        parts.append(_DIGITS_VI[units])

    return " ".join(parts)


def number_to_vietnamese_words(n: int) -> str:
    """Chuyển số nguyên sang cách đọc tiếng Việt tự nhiên cho F5-TTS."""
    if n < 0:
        return "âm " + number_to_vietnamese_words(-n)
    if n == 0:
        return "không"

    units = ["", "nghìn", "triệu", "tỷ"]
    groups: list[int] = []
    while n > 0:
        groups.append(n % 1000)
        n //= 1000

    parts: list[str] = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        is_full = idx < len(groups) - 1
        chunk = _read_three_digits(g, full=is_full)
        unit = units[idx] if idx < len(units) else ""
        parts.append(f"{chunk} {unit}".strip())
    return " ".join(parts)


def normalize_vietnamese_numbers(text: str) -> str:
    """Chuẩn hóa ngày tháng, số thập phân và số nguyên sang chữ tiếng Việt khi vinorm không chạy."""
    # Ngày/tháng dạng 14/11 hoặc 14/11/2026
    text = re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda m: (
            f"ngày {number_to_vietnamese_words(int(m.group(1)))} "
            f"tháng {number_to_vietnamese_words(int(m.group(2)))} "
            f"năm {number_to_vietnamese_words(int(m.group(3)))}"
        ),
        text,
    )
    text = re.sub(
        r"\b(\d{1,2})/(\d{1,2})\b",
        lambda m: (
            f"{number_to_vietnamese_words(int(m.group(1)))} "
            f"tháng {number_to_vietnamese_words(int(m.group(2)))}"
        ),
        text,
    )
    # Số thập phân 1.5 hoặc 1,5
    text = re.sub(
        r"\b(\d+)[.,](\d+)\b",
        lambda m: (
            f"{number_to_vietnamese_words(int(m.group(1)))} phẩy "
            f"{' '.join(_DIGITS_VI[int(d)] for d in m.group(2))}"
            if len(m.group(2)) <= 2
            else f"{number_to_vietnamese_words(int(m.group(1) + m.group(2)))}"
        ),
        text,
    )
    # Số nguyên còn lại
    text = re.sub(
        r"\b\d+\b",
        lambda m: number_to_vietnamese_words(int(m.group(0))),
        text,
    )
    return text


def normalize_vietnamese_script(raw_text: str) -> str:
    """Chuẩn hóa kịch bản tiếng Việt để F5-TTS đọc chuẩn, không ngọng hoặc bỏ chữ."""
    text = raw_text.strip()

    # Áp dụng từ điển phiên âm tùy biến từ brand_brief.json trước
    try:
        brief = load_brand_brief()
        pm = brief.get("phonetic_map") or {}
        for display_tok, spoken_tok in sorted(pm.items(), key=lambda kv: -len(str(kv[0]))):
            dt = str(display_tok).strip()
            st = str(spoken_tok).strip()
            if dt and st:
                text = re.sub(re.escape(dt), st, text, flags=re.IGNORECASE)
    except Exception:
        pass

    # Thay thế từ tiếng Anh TikTok Shop sang phiên âm tiếng Việt (tránh thay chồng chéo)
    for pattern, repl in ENGLISH_PHONETIC_MAP:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # Chuẩn hóa dấu câu & ký hiệu để F5-TTS ngắt nhịp tự nhiên thay vì đọc tuột
    text = re.sub(r"\[([^\]]+)\]", r"\1, ", text)
    text = re.sub(r"\s*&\s*", " và ", text)
    text = re.sub(r"\s+[-–—]\s+", ", ", text)
    text = re.sub(r"\s*[:;]\s*", ", ", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)

    # Chuyển đổi đơn vị phổ biến
    text = re.sub(r"(\d+)\s*%", r"\1 phần trăm", text)
    text = re.sub(r"\b(\d+)\s*[kK]\b", r"\1 nghìn", text)

    # Chuẩn hóa số / ngày tháng bằng vinorm (nếu khả dụng), fallback sang bộ thuần Python
    used_vinorm = False
    try:
        from vinorm import TTSnorm

        normed = TTSnorm(text, punc=False, unknown=True, lower=True, rule=False)
        if normed and normed.strip():
            text = normed
            used_vinorm = True
    except Exception:
        used_vinorm = False

    if not used_vinorm:
        text = normalize_vietnamese_numbers(text)

    text = text.replace('"', "").replace("“", "").replace("”", "")
    text = re.sub(r"\s*([.,!?])\s*", r" \1 ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def format_srt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_tiktok_srt_entries(
    whisper_segments: list[Any],
    max_words: int = 4,
    max_chars: int = 22,
    pause_threshold: float = 0.25,
) -> list[tuple[float, float, str]]:
    """Nhóm từng từ từ Faster-Whisper thành các dòng phụ đề ngắn chuẩn TikTok (3-5 từ/cụm, <=22 ký tự)."""
    words: list[tuple[float, float, str]] = []
    for seg in whisper_segments:
        if getattr(seg, "words", None):
            for w in seg.words:
                token = w.word.strip()
                if token:
                    words.append((float(w.start), float(w.end), token))
        else:
            text = seg.text.strip()
            if text:
                words.append((float(seg.start), float(seg.end), text))

    if not words:
        return []

    entries: list[tuple[float, float, str]] = []
    buf: list[tuple[float, float, str]] = []

    def flush_buf() -> None:
        if not buf:
            return
        line = " ".join(item[2] for item in buf)
        line = re.sub(r"\s+([.,!?;:])", r"\1", line).strip()
        if line:
            entries.append((buf[0][0], buf[-1][1], line))
        buf.clear()

    for idx, item in enumerate(words):
        start, end, token = item
        if buf:
            prev_end = buf[-1][1]
            cur_text_len = sum(len(x[2]) + 1 for x in buf) + len(token)
            gap = start - prev_end
            if (
                len(buf) >= max_words
                or cur_text_len > max_chars
                or gap > pause_threshold
            ):
                flush_buf()

        buf.append((start, end, token))

        # Ngắt ngay sau dấu kết câu
        if token.endswith((".", "!", "?", ";")) and len(buf) >= 2:
            flush_buf()
        elif token.endswith(",") and len(buf) >= 4:
            flush_buf()

    flush_buf()
    return entries


def extract_word_timestamps(whisper_segments: list[Any]) -> list[dict[str, Any]]:
    """Trích xuất danh sách word-level timestamps từ Faster-Whisper cho Remotion Karaoke."""
    words_out: list[dict[str, Any]] = []
    for seg in whisper_segments:
        if getattr(seg, "words", None):
            for w in seg.words:
                token = str(getattr(w, "word", "")).strip()
                if token:
                    words_out.append(
                        {
                            "word": token,
                            "start": round(float(w.start), 3),
                            "end": round(float(w.end), 3),
                        }
                    )
        else:
            raw_tokens = str(getattr(seg, "text", "")).strip().split()
            if not raw_tokens:
                continue
            s_t = float(seg.start)
            e_t = float(seg.end)
            dur = max(0.1, e_t - s_t)
            total_chars = sum(len(t) for t in raw_tokens) or 1
            cur = s_t
            for idx, tok in enumerate(raw_tokens):
                share = dur * (len(tok) / total_chars)
                nxt = e_t if idx == len(raw_tokens) - 1 else round(cur + max(0.06, share), 3)
                words_out.append({"word": tok, "start": round(cur, 3), "end": round(nxt, 3)})
                cur = nxt
    return words_out


def generate_srt_from_audio(
    wav_path: Path,
    srt_path: Path,
    whisper_model_size: str,
    prompt_hint: str,
    voice_beats_file: Path | None = None,
) -> int:
    model = load_whisper(whisper_model_size)
    # KHÔNG truyền kịch bản làm initial_prompt để tránh Whisper bỏ qua đoạn đầu audio
    segments_iter, _ = model.transcribe(
        str(wav_path),
        language="vi",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        word_timestamps=True,
    )
    segments = [
        seg for seg in segments_iter
        if not HALLUCINATION_RE.search(str(getattr(seg, "text", "") or ""))
    ]
    entries = build_tiktok_srt_entries(segments)
    words_out = extract_word_timestamps(segments)

    srt_blocks = []
    for i, (start, end, text) in enumerate(entries, start=1):
        srt_blocks.append(
            f"{i}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{text}\n"
        )

    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    words_path = srt_path.parent / "03_words.json"
    words_path.write_text(json.dumps(words_out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Lưu mốc thời gian thô từ audio thật để repair_subtitles_and_beats neo đúng nhịp đọc
    whisper_raw_path = srt_path.parent / "03_whisper_raw.json"
    whisper_raw_path.write_text(json.dumps(words_out, ensure_ascii=False, indent=2), encoding="utf-8")

    del model
    gc.collect()

    # Luôn đồng bộ lại phụ đề từ display_text chuẩn trong voice_beats.json + mốc audio thật
    if voice_beats_file is not None and voice_beats_file.exists():
        rep = repair_subtitles_and_beats(force_rebuild=True)
        return int(rep.get("srt_lines") or len(entries))
    return len(entries)


def select_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> int:
    configure_runtime_paths()

    parser = argparse.ArgumentParser(
        description="Nhân bản giọng tiếng Việt (F5-TTS) và tạo phụ đề SRT chuẩn mili-giây (Faster-Whisper)."
    )
    parser.add_argument(
        "--script",
        default=str(DEFAULT_SCRIPT_FILE),
        help="File văn bản kịch bản tiếng Việt đầu vào (mặc định: 04_workspace/kich_ban.txt).",
    )
    parser.add_argument(
        "--text",
        default=None,
        help="Truyền trực tiếp chuỗi kịch bản (ghi đè --script nếu có).",
    )
    parser.add_argument(
        "--ref-audio",
        default=None,
        help="Đường dẫn file giọng mẫu (mặc định tự tìm 03_voice_clone/giong_mau.*).",
    )
    parser.add_argument(
        "--ref-text",
        default=str(DEFAULT_REF_TEXT_FILE),
        help="Đường dẫn file text giọng mẫu (mặc định: 03_voice_clone/noi_dung_giong_mau.txt).",
    )
    parser.add_argument(
        "--output-audio",
        default=str(DEFAULT_OUT_WAV),
        help="File âm thanh đầu ra (mặc định: 04_workspace/ready_for_openreel/02_giong_doc_ai.wav).",
    )
    parser.add_argument(
        "--output-srt",
        default=str(DEFAULT_OUT_SRT),
        help="File phụ đề .srt đầu ra (mặc định: 04_workspace/ready_for_openreel/03_phu_de.srt).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Tốc độ đọc (mặc định: 1.0; gợi ý TikTok: 1.0 - 1.15).",
    )
    parser.add_argument(
        "--nfe-step",
        type=int,
        default=48,
        help="Số bước diffusion của F5-TTS (32 nhanh, 48-64 giống giọng thật nhất). Mặc định: 48.",
    )
    parser.add_argument(
        "--cfg-strength",
        type=float,
        default=2.2,
        help="Độ bám sát âm sắc giọng mẫu (1.8 - 2.5). Mặc định: 2.2.",
    )
    parser.add_argument(
        "--sway-coef",
        type=float,
        default=-1.0,
        help="Sway sampling coefficient của F5-TTS. Mặc định: -1.0.",
    )
    parser.add_argument(
        "--model-ckpt",
        default=str(DEFAULT_MODEL_CKPT),
        help="Đường dẫn checkpoint model_last.pt.",
    )
    parser.add_argument(
        "--vocab-file",
        default=str(DEFAULT_VOCAB_FILE),
        help="Đường dẫn file vocab.txt.",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        help="Model Faster-Whisper để tạo phụ đề SRT (mặc định: small).",
    )
    parser.add_argument(
        "--target-duration",
        type=float,
        default=0.0,
        help="Thời lượng mục tiêu (giây); 0 = tự đọc từ 04_workspace/brand_brief.json.",
    )
    parser.add_argument(
        "--no-srt",
        action="store_true",
        help="Chỉ xuất file giọng đọc WAV, bỏ qua bước tạo phụ đề SRT.",
    )
    args = parser.parse_args()
    active_root = get_project_root()
    import style_dna as _sd
    _sd.refresh_project_paths(active_root)

    # 1. Đọc kịch bản đầu vào
    if args.text is not None:
        raw_script = args.text.strip()
    else:
        script_path = Path(args.script)
        if not script_path.is_absolute():
            script_path = (active_root / script_path).resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file kịch bản: {script_path}")
        raw_script = script_path.read_text(encoding="utf-8-sig").strip()

    if not raw_script:
        raise ValueError("Nội dung kịch bản đầu vào đang rỗng.")

    # 2. Tìm và chuẩn hóa giọng mẫu về Mono 24000Hz
    ref_src = find_ref_audio(args.ref_audio)
    norm_ref_wav = active_root / "04_workspace" / "ref_audio_normalized.wav"
    print(f"[1/4] Chuẩn hóa giọng mẫu: {ref_src.name} -> Mono 24000Hz...")
    ref_wav_path, was_clipped = normalize_reference_audio(ref_src, norm_ref_wav)

    ref_text_path = Path(args.ref_text)
    if not ref_text_path.is_absolute():
        ref_text_path = (PROJECT_ROOT / ref_text_path).resolve()

    if not ref_text_path.exists() and ref_text_path == DEFAULT_REF_TEXT_FILE and FALLBACK_REF_TEXT_FILE.exists():
        ref_text_path = FALLBACK_REF_TEXT_FILE

    ref_text = ""
    if ref_text_path.exists() and not was_clipped:
        ref_text = ref_text_path.read_text(encoding="utf-8-sig").strip()

    if not ref_text:
        print("[1b/4] Đang tự nhận diện nội dung file giọng mẫu bằng Faster-Whisper...")
        ref_text = transcribe_audio_text(ref_wav_path, model_size=args.whisper_model)
        if not ref_text_path.exists() or not ref_text_path.read_text(encoding="utf-8-sig").strip():
            ref_text_path.write_text(ref_text + "\n", encoding="utf-8")

    ref_text_norm = ref_text.strip().lower()
    if ref_text_norm and ref_text_norm[-1] not in ".!?":
        ref_text_norm += "."

    gen_text_norm = normalize_vietnamese_script(raw_script)
    print(f"  -> Giọng mẫu ref_text: \"{ref_text_norm}\"")
    print(f"  -> Kịch bản TTS đã chuẩn hóa: \"{gen_text_norm}\"")

    # 3. Nạp F5-TTS và tổng hợp giọng đọc
    patch_torchaudio_load()
    import soundfile as sf
    import torch
    from f5_tts.api import F5TTS

    device = select_device()
    ckpt_path = Path(args.model_ckpt)
    vocab_path = Path(args.vocab_file)
    if not ckpt_path.exists() or not vocab_path.exists():
        raise FileNotFoundError(
            f"Thiếu model tiếng Việt tại {ckpt_path} hoặc {vocab_path}."
        )

    print(f"[2/4] Đang nạp F5-TTS-Vietnamese trên thiết bị: {device.upper()}...")
    f5tts = F5TTS(
        model="F5TTS_Base",
        ckpt_file=str(ckpt_path),
        vocab_file=str(vocab_path),
        device=device,
    )

    out_wav_path = Path(args.output_audio)
    if not out_wav_path.is_absolute():
        out_wav_path = (active_root / out_wav_path).resolve()
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"[3/4] Đang nhân bản giọng nói (tốc độ {args.speed}x, nfe_step={args.nfe_step}, cfg={args.cfg_strength})..."
    )
    import tempfile
    import numpy as np

    def _time_stretch_pcm_ffmpeg(samples: Any, sample_rate: int, atempo: float) -> Any:
        ratio = max(0.5, min(2.0, float(atempo)))
        if abs(ratio - 1.0) <= 0.02:
            return samples
        ffmpeg_exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffmpeg_exe:
            return samples
        with tempfile.TemporaryDirectory() as tmpd:
            in_w = Path(tmpd) / "in.wav"
            out_w = Path(tmpd) / "out.wav"
            sf.write(str(in_w), samples, sample_rate)
            subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(in_w),
                    "-filter:a",
                    f"atempo={ratio:.4f}",
                    "-ar",
                    str(sample_rate),
                    "-ac",
                    "1",
                    str(out_w),
                ],
                check=True,
                timeout=60,
            )
            stretched, _ = sf.read(str(out_w), dtype="float32")
            return np.asarray(stretched, dtype=np.float32).reshape(-1)

    def _split_long_clause(sent: str, max_words: int = 22) -> list[str]:
        words_s = sent.split()
        if len(words_s) <= max_words:
            return [sent]
        # Prefer natural comma pauses, dashes, or Vietnamese conjunctions
        parts_out: list[str] = []
        norm_s = re.sub(r"\s+[-–—]\s+", ", ", sent)
        norm_s = re.sub(r"\s+(vừa|nên|nhưng|giúp|để|vì|rồi|cũng|hoặc|mà)\s+", r", \1 ", norm_s, flags=re.IGNORECASE)
        raw_clauses = [c.strip() for c in re.split(r",\s+", norm_s) if c.strip()]
        # Further split any oversized single clause near its midpoint so F5-TTS stays <= max_words
        bounded_clauses: list[str] = []
        for rc in raw_clauses:
            rc_words = rc.split()
            if len(rc_words) <= max_words:
                bounded_clauses.append(rc)
            else:
                mid = max(8, min(max_words - 2, len(rc_words) // 2))
                bounded_clauses.append(" ".join(rc_words[:mid]))
                bounded_clauses.append(" ".join(rc_words[mid:]))
        cur = ""
        for cl in bounded_clauses:
            cand = f"{cur}, {cl}" if cur else cl
            if cur and len(cand.split()) > max_words and len(cur.split()) >= 7:
                parts_out.append(cur.rstrip(", ") + ",")
                cur = cl
            else:
                cur = cand
        if cur:
            if parts_out and len(cur.split()) < 6:
                parts_out[-1] = parts_out[-1].rstrip(", ") + ", " + cur
            else:
                parts_out.append(cur)
        return parts_out or [sent]

    def _group_natural_breath_sentences(sents: list[str]) -> list[str]:
        """Split overly long sentences (>22 words) and merge overly short fragments (<7 words) for natural F5-TTS breath groups."""
        expanded: list[str] = []
        for s in sents:
            s_c = s.strip()
            if s_c:
                expanded.extend(_split_long_clause(s_c, max_words=22))
        if len(expanded) <= 1:
            return expanded or sents
        grouped: list[str] = []
        buf = ""
        for idx, s in enumerate(expanded):
            s_clean = s.strip()
            if not s_clean:
                continue
            is_last = idx == len(expanded) - 1
            if not buf:
                buf = s_clean
            elif len(buf.split()) < 7 and not is_last:
                buf = buf.rstrip(".!?, ") + ", " + (s_clean[0].lower() + s_clean[1:] if len(s_clean) > 1 else s_clean)
            else:
                grouped.append(buf)
                buf = s_clean
            if len(buf.split()) >= 18 and not is_last:
                grouped.append(buf)
                buf = ""
        if buf:
            if grouped and len(buf.split()) < 5:
                prev = grouped[-1].rstrip(".!?, ")
                grouped[-1] = f"{prev}, {buf[0].lower() + buf[1:] if len(buf) > 1 else buf}"
            else:
                grouped.append(buf)
        return grouped or expanded

    def _trim_pcm_edges(wav_arr: Any, sample_rate: int, keep_lead_ms: float = 30.0, keep_tail_ms: float = 50.0) -> Any:
        """Trim dead F5-TTS leading/trailing silence while keeping natural breath & 20ms smooth fades."""
        arr = np.asarray(wav_arr, dtype=np.float32).reshape(-1)
        if len(arr) < int(sample_rate * 0.25):
            return arr
        win = max(1, int(sample_rate * 0.015))
        rms_vals = [
            float(np.sqrt(np.mean(arr[i : i + win] ** 2)))
            for i in range(0, len(arr), win)
        ]
        peak = max(rms_vals) if rms_vals else 0.0
        if peak < 1e-4:
            return arr
        thresh = max(peak * 0.06, 0.004)
        active = [idx for idx, val in enumerate(rms_vals) if val >= thresh]
        if not active:
            return arr
        lead_samp = int(sample_rate * (keep_lead_ms / 1000.0))
        tail_samp = int(sample_rate * (keep_tail_ms / 1000.0))
        s_idx = max(0, active[0] * win - lead_samp)
        e_idx = min(len(arr), (active[-1] + 1) * win + tail_samp)
        trimmed = arr[s_idx:e_idx].copy()
        fade_len = min(len(trimmed) // 4, int(sample_rate * 0.02))
        if fade_len > 1:
            trimmed[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
            trimmed[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
        return trimmed

    raw_sentences = _group_natural_breath_sentences(
        [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_script) if s.strip()] or [raw_script]
    )
    sentences_norm = [normalize_vietnamese_script(s) for s in raw_sentences]

    brief_cfg = load_brand_brief()
    target_dur = float(args.target_duration or 0.0)
    if target_dur <= 0.0:
        target_dur = float(brief_cfg.get("target_duration_sec") or 0.0)

    sr = 24000
    raw_beats: list[tuple[Any, int, str, str]] = []
    for ci, ch in enumerate(sentences_norm, start=1):
        print(f"  -> Tổng hợp Beat {ci}/{len(sentences_norm)}: \"{ch[:70]}\"")
        part_wav, part_sr, _ = f5tts.infer(
            ref_file=str(ref_wav_path),
            ref_text=ref_text_norm,
            gen_text=ch,
            speed=args.speed,
            nfe_step=args.nfe_step,
            cfg_strength=args.cfg_strength,
            sway_sampling_coef=args.sway_coef,
            seed=42,
            remove_silence=False,
        )
        sr = int(part_sr or sr)
        if part_wav is not None and len(part_wav) > 0:
            cleaned_wav = _trim_pcm_edges(part_wav, sr)
            raw_s = raw_sentences[ci - 1]
            disp_s = restore_display_text(raw_s, brief_cfg)
            raw_beats.append((cleaned_wav, sr, raw_s, disp_s))

    raw_speech_dur = sum(len(w) / float(s_rate) for w, s_rate, _, _ in raw_beats)
    n_gaps = max(0, len(raw_beats) - 1)
    pause_sec = 0.16 if n_gaps else 0.0
    tail_sec = 0.14
    tempo_ratio = 1.0

    if target_dur >= 8.0 and raw_beats and raw_speech_dur > 1.0:
        gap_delta = target_dur - raw_speech_dur
        if -0.4 <= gap_delta <= 2.2 and n_gaps > 0:
            pause_sec = min(0.24, max(0.14, (gap_delta - 0.18) / n_gaps))
            tail_sec = max(0.08, min(0.35, target_dur - raw_speech_dur - pause_sec * n_gaps))
        elif abs(gap_delta) > 0.4:
            pause_sec = 0.20 if gap_delta > 0 else 0.12
            tail_sec = 0.22 if gap_delta > 0 else 0.10
            desired_speech = max(4.0, target_dur - (pause_sec * n_gaps + tail_sec))
            tempo_ratio = max(0.94, min(1.06, raw_speech_dur / desired_speech))
            print(
                f"  -> Căn chuẩn thời lượng mục tiêu {target_dur:.1f}s: "
                f"raw={raw_speech_dur:.2f}s, atempo={tempo_ratio:.3f}, pause={pause_sec:.2f}s"
            )

    voice_beats_list: list[dict[str, Any]] = []
    combined_parts: list[Any] = []
    cursor_sec = 0.0

    for ci, (part_wav, p_sr, raw_s, disp_s) in enumerate(raw_beats, start=1):
        adj_wav = _time_stretch_pcm_ffmpeg(part_wav, p_sr, tempo_ratio)
        if combined_parts and pause_sec > 0.0:
            pause = np.zeros(int(p_sr * pause_sec), dtype=adj_wav.dtype)
            combined_parts.append(pause)
            cursor_sec += pause_sec
        beat_dur = len(adj_wav) / float(p_sr)
        voice_beats_list.append(
            {
                "index": ci,
                "start": round(cursor_sec, 3),
                "end": round(cursor_sec + beat_dur, 3),
                "duration": round(beat_dur, 3),
                "tts_text": raw_s,
                "display_text": disp_s,
            }
        )
        combined_parts.append(adj_wav)
        cursor_sec += beat_dur

    if target_dur >= 8.0 and cursor_sec < target_dur - 0.15:
        extra_tail = min(1.2, max(tail_sec, target_dur - cursor_sec))
        if extra_tail > 0.05 and combined_parts:
            combined_parts.append(np.zeros(int(sr * extra_tail), dtype=combined_parts[-1].dtype))
            cursor_sec += extra_tail

    wav = np.concatenate(combined_parts) if combined_parts else np.zeros(sr, dtype=np.float32)
    sf.write(str(out_wav_path), wav, sr)

    # Mastering giọng đọc AI qua FFmpeg (lọc ấm giọng + compressor đều âm lượng + limiter chống clip, giữ nguyên độ dài)
    ffmpeg_exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if ffmpeg_exe and out_wav_path.exists():
        master_tmp = out_wav_path.with_name(f"{out_wav_path.stem}_master_tmp.wav")
        try:
            subprocess.run(
                [
                    ffmpeg_exe,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(out_wav_path),
                    "-af",
                    "highpass=f=75,lowpass=f=11500,equalizer=f=3200:t=q:w=1.2:g=-1.5,acompressor=threshold=-18dB:ratio=2.5:attack=12:release=140:makeup=2dB,alimiter=limit=0.95",
                    "-ar",
                    str(sr),
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(master_tmp),
                ],
                check=True,
                timeout=60,
            )
            if master_tmp.exists() and master_tmp.stat().st_size > 1000:
                os.replace(str(master_tmp), str(out_wav_path))
        except Exception as exc:
            print(f"  [WARN] Bỏ qua FFmpeg mastering: {exc}")
            if master_tmp.exists():
                try:
                    master_tmp.unlink()
                except Exception:
                    pass

    duration_sec = round(len(wav) / float(sr), 3) if wav is not None else 0.0
    print(f"  -> Đã xuất file lồng tiếng: {out_wav_path} ({duration_sec}s @ {sr}Hz)")

    voice_beats_file = active_root / "04_workspace" / "voice_beats.json"
    voice_beats_file.parent.mkdir(parents=True, exist_ok=True)
    voice_beats_file.write_text(
        json.dumps(
            {"total_duration_sec": duration_sec, "beats": voice_beats_list},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  -> Đã lưu timing từng câu: {voice_beats_file} ({len(voice_beats_list)} beats)")

    # Giải phóng VRAM trước khi nạp Faster-Whisper
    del f5tts
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 4. Tạo phụ đề SRT chuẩn từng mili-giây bằng Faster-Whisper
    if not args.no_srt:
        out_srt_path = Path(args.output_srt)
        if not out_srt_path.is_absolute():
            out_srt_path = (active_root / out_srt_path).resolve()
        print(f"[4/4] Đang tạo phụ đề SRT bằng Faster-Whisper ({args.whisper_model})...")
        line_count = generate_srt_from_audio(
            wav_path=out_wav_path,
            srt_path=out_srt_path,
            whisper_model_size=args.whisper_model,
            prompt_hint=raw_script,
            voice_beats_file=voice_beats_file,
        )
        print(f"  -> Đã xuất {line_count} dòng phụ đề: {out_srt_path}")

    print("\n[HOÀN TẤT] Voice Engine xử lý thành công.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
