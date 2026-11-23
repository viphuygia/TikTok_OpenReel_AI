#!/usr/bin/env python3
"""Style DNA Auto-Extraction and Word-Level Timing Utilities."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from project_manager import get_project_root

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT_DIR = get_project_root()
DIR_WORKSPACE = PROJECT_ROOT_DIR / "04_workspace"
DIR_VIDEO_THO = PROJECT_ROOT_DIR / "02_video_tho"
# Shared channel-level style assets live at repo root across all projects
DIR_FRAMES_MAU = ROOT_DIR / "04_workspace" / "frames" / "01_video_mau"
DIR_READY = DIR_WORKSPACE / "ready_for_openreel"
FILE_STYLE_GUIDE = ROOT_DIR / "phong_cach_kenh.md"
FILE_STYLE_DNA = ROOT_DIR / "style_dna.json"
FILE_GLOBAL_BANNED_WORDS = ROOT_DIR / "global_banned_words.json"
DIR_ASSETS_EMOJIS = ROOT_DIR / "assets" / "emojis"
DIR_ASSETS_ANIMATED_STICKERS = ROOT_DIR / "assets" / "animated_stickers"
DIR_ASSETS_CUSTOM_STICKERS = ROOT_DIR / "assets" / "stickers"

_SLOP_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?")


def strip_slop_emojis(text: str) -> str:
    """Remove flat Unicode emojis from UI/overlay text to avoid generic AI-slop look."""
    cleaned = _SLOP_EMOJI_RE.sub(" ", str(text or ""))
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def resolve_animated_sticker_asset(emoji: str, index: int = 0) -> str:
    """Return relative asset path (e.g. 'assets/animated_stickers/1f525.webp') or custom user sticker."""
    if DIR_ASSETS_CUSTOM_STICKERS.exists():
        custom = sorted(
            p
            for p in DIR_ASSETS_CUSTOM_STICKERS.iterdir()
            if p.is_file() and p.suffix.lower() in {".webp", ".gif", ".png"}
        )
        if custom and index < len(custom):
            return f"assets/stickers/{custom[index].name}"

    hx = emoji_to_twemoji_hex(emoji)
    if hx and (DIR_ASSETS_ANIMATED_STICKERS / f"{hx}.webp").exists():
        return f"assets/animated_stickers/{hx}.webp"

    if DIR_ASSETS_ANIMATED_STICKERS.exists():
        pool = sorted(DIR_ASSETS_ANIMATED_STICKERS.glob("*.webp"))
        if pool:
            return f"assets/animated_stickers/{pool[index % len(pool)].name}"
    return ""


def emoji_to_twemoji_hex(emoji: str) -> str:
    cps = [f"{ord(ch):x}" for ch in (emoji or "").strip() if ord(ch) != 0xFE0F]
    return "-".join(cps)


def ensure_twemoji_svg(emoji: str) -> Path | None:
    """Return local cached Twemoji SVG path for an emoji, fetching once from CDN if missing."""
    hx = emoji_to_twemoji_hex(emoji)
    if not hx:
        return None
    DIR_ASSETS_EMOJIS.mkdir(parents=True, exist_ok=True)
    dst = DIR_ASSETS_EMOJIS / f"{hx}.svg"
    if dst.exists() and dst.stat().st_size > 80:
        return dst
    try:
        import urllib.request
        url = f"https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/{hx}.svg"
        with urllib.request.urlopen(url, timeout=6) as resp:
            raw = resp.read()
            if raw and b"<svg" in raw:
                dst.write_bytes(raw)
                return dst
    except Exception:
        pass
    return None

DEFAULT_GLOBAL_BANNED_WORDS: list[str] = [
    # Đánh giá / Cam kết tuyệt đối / Phóng đại (vi phạm chính sách TikTok Shop)
    "5.0",
    "5 sao",
    "★★★★★",
    "100%",
    "chính hãng 100%",
    "đảm bảo 100%",
    "hoàn tiền 100%",
    "số 1",
    "số một",
    "tốt nhất",
    "nhất thị trường",
    "duy nhất",
    "tuyệt đối",
    "vĩnh viễn",
    "mãi mãi",
    "cam kết",
    "hiệu quả tức thì",
    "thần thánh",
    "siêu cấp",
    "vô địch",
    "bá đạo",
    "cực phẩm",
    "rẻ vô địch",
    "giá rẻ nhất",
    "miễn phí hoàn toàn",
    # Y tế / Trị liệu / Khẳng định công dụng như thuốc
    "chữa bệnh",
    "điều trị",
    "trị dứt điểm",
    "dứt điểm",
    "khỏi bệnh",
    "khỏi hẳn",
    "chữa khỏi",
    "thuốc",
    "đặc trị",
    "trị mụn",
    "trị thâm",
    "trị nám",
    "trị gàu",
    "trị rụng tóc",
    "kháng viêm",
    "kháng khuẩn",
    "diệt khuẩn",
    "sát khuẩn",
    "ngăn ngừa ung thư",
    "giảm cân cấp tốc",
    "tan mỡ",
    "tăng cân nhanh",
    "bác sĩ khuyên dùng",
    "y khoa chứng nhận",
    # Điều hướng nền tảng ngoài & từ nhạy cảm
    "shopee",
    "lazada",
    "tiki",
    "zalo",
    "facebook",
    "inbox",
    "nhắn tin riêng",
    "chuyển khoản",
    "đặt cọc",
    "hàng nhái",
    "hàng fake",
    "super fake",
    "rep 1:1",
    "xách tay",
    "lừa đảo",
    "bóc phốt",
]


def _parse_banned_word_items(raw: Any) -> list[str]:
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw]
    else:
        txt = re.sub(r"^\s*\[|\]\s*$", "", str(raw or "").strip())
        items = re.split(r"[,;\n\|]+", txt)
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        clean = re.sub(r"^[\'\"\-\*\s]+|[\'\"\s]+$", "", it).strip()
        if not clean:
            continue
        low = clean.lower()
        if low not in seen:
            seen.add(low)
            out.append(clean)
    return out


def load_global_banned_words() -> list[str]:
    if not FILE_GLOBAL_BANNED_WORDS.exists():
        save_global_banned_words(DEFAULT_GLOBAL_BANNED_WORDS)
        return list(DEFAULT_GLOBAL_BANNED_WORDS)
    try:
        data = json.loads(FILE_GLOBAL_BANNED_WORDS.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and isinstance(data.get("words"), list):
            parsed = _parse_banned_word_items(data["words"])
            return parsed
        if isinstance(data, list):
            return _parse_banned_word_items(data)
    except Exception:
        pass
    return list(DEFAULT_GLOBAL_BANNED_WORDS)


def save_global_banned_words(words: Any, reset_default: bool = False) -> list[str]:
    cleaned = list(DEFAULT_GLOBAL_BANNED_WORDS) if reset_default else _parse_banned_word_items(words)
    FILE_GLOBAL_BANNED_WORDS.parent.mkdir(parents=True, exist_ok=True)
    FILE_GLOBAL_BANNED_WORDS.write_text(
        json.dumps({"words": cleaned}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cleaned


def get_effective_banned_words(brief: dict[str, Any] | None = None) -> list[str]:
    b = brief or load_brand_brief()
    merged = load_global_banned_words() + _parse_banned_word_items(b.get("banned_words"))
    out: list[str] = []
    seen: set[str] = set()
    for w in merged:
        low = w.lower()
        if low not in seen:
            seen.add(low)
            out.append(w)
    # Longest phrases first so "trị dứt điểm" matches before "dứt điểm"
    out.sort(key=len, reverse=True)
    return out


def sanitize_banned_text(
    text: str,
    banned_words: list[str] | None = None,
    brief: dict[str, Any] | None = None,
) -> str:
    """Remove any global or brand-specific banned words cleanly without breaking valid words."""
    out = str(text or "")
    if not out.strip():
        return out
    words = banned_words if banned_words is not None else get_effective_banned_words(brief)
    for bw in words:
        term = str(bw or "").strip()
        if not term:
            continue
        esc = re.escape(term)
        left_b = r"(?<!\w)" if re.match(r"^\w", term) else ""
        right_b = r"(?!\w)" if re.search(r"\w$", term) else ""
        pattern = f"{left_b}{esc}{right_b}"
        out = re.sub(pattern, " ", out, flags=re.I)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"([·•])\s*([·•])+", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"^[\s·•\-:|,]+|[\s·•\-:|,]+$", "", out).strip()
    return out
FILE_BRAND_BRIEF = DIR_WORKSPACE / "brand_brief.json"
FILE_VOICE_BEATS = DIR_WORKSPACE / "voice_beats.json"
FILE_SCRIPT = DIR_WORKSPACE / "kich_ban.txt"
FILE_SCRIPT_DISPLAY = DIR_WORKSPACE / "kich_ban_hien_thi.md"
FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
FILE_SCRIPT_OPTIONS = DIR_WORKSPACE / "script_options.json"
FILE_CRITIC_REPORT = DIR_WORKSPACE / "ai_critic_report.md"
FILE_REF_HOOK = ROOT_DIR / "04_workspace" / "style_ref_hook.jpg"
FILE_REF_MID = ROOT_DIR / "04_workspace" / "style_ref_Mid.jpg"
FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
FILE_SRT = DIR_READY / "03_phu_de.srt"
FILE_WORDS_JSON = DIR_READY / "03_words.json"


def refresh_project_paths(project_root: Path | None = None) -> Path:
    global PROJECT_ROOT_DIR, DIR_WORKSPACE, DIR_VIDEO_THO, DIR_READY
    global FILE_BRAND_BRIEF, FILE_VOICE_BEATS
    global FILE_SCRIPT, FILE_SCRIPT_DISPLAY, FILE_DIRECTOR_PLAN, FILE_EDIT_PLAN
    global FILE_SCRIPT_OPTIONS, FILE_CRITIC_REPORT
    global FILE_TTS_WAV, FILE_SRT, FILE_WORDS_JSON
    PROJECT_ROOT_DIR = project_root or get_project_root()
    DIR_WORKSPACE = PROJECT_ROOT_DIR / "04_workspace"
    DIR_VIDEO_THO = PROJECT_ROOT_DIR / "02_video_tho"
    DIR_READY = DIR_WORKSPACE / "ready_for_openreel"
    FILE_BRAND_BRIEF = DIR_WORKSPACE / "brand_brief.json"
    FILE_VOICE_BEATS = DIR_WORKSPACE / "voice_beats.json"
    FILE_SCRIPT = DIR_WORKSPACE / "kich_ban.txt"
    FILE_SCRIPT_DISPLAY = DIR_WORKSPACE / "kich_ban_hien_thi.md"
    FILE_DIRECTOR_PLAN = DIR_WORKSPACE / "director_plan.json"
    FILE_EDIT_PLAN = DIR_WORKSPACE / "edit_plan.json"
    FILE_SCRIPT_OPTIONS = DIR_WORKSPACE / "script_options.json"
    FILE_CRITIC_REPORT = DIR_WORKSPACE / "ai_critic_report.md"
    FILE_TTS_WAV = DIR_READY / "02_giong_doc_ai.wav"
    FILE_SRT = DIR_READY / "03_phu_de.srt"
    FILE_WORDS_JSON = DIR_READY / "03_words.json"
    return PROJECT_ROOT_DIR

EMPTY_BRAND_BRIEF: dict[str, Any] = {
    "target_duration_sec": 25.0,
    "raw_brief": "",
    "brand": "",
    "product_line": "",
    "category": "",
    "usps": "",
    "offer_cta": "",
    "banned_words": "",
    "brief_ai_extracted": False,
    "phonetic_map": {
        "Freeship": "phờ ri síp",
    },
}

DEFAULT_BRAND_BRIEF: dict[str, Any] = {
    "target_duration_sec": 25.0,
    "raw_brief": "",
    "brand": "HEAD & SHOULDERS",
    "product_line": "5in1 Tonic",
    "category": "xịt dưỡng da đầu",
    "usps": "Chai 50ml nhỏ gọn, vòi xịt dài đưa dưỡng chất thẳng vào chân tóc, 2.8% Niacinamide và Menthol mát lạnh, làm sạch gàu dịu ngứa tức thì, không cần xả lại",
    "offer_cta": "Đang có deal hời kèm Freeship, bấm giỏ hàng góc trái chốt liền",
    "banned_words": "",
    "phonetic_map": {
        "Head & Shoulders": "Hét en Sâu đơ",
        "Niacinamide": "Ni a xi na mai",
        "Menthol": "Men thô",
        "Freeship": "phờ ri síp",
        "50ml": "năm mươi mi li lít",
        "2.8%": "hai phẩy tám phần trăm",
        "5 in 1": "năm trong một",
    },
}

DEFAULT_PHONETIC_TO_DISPLAY: list[tuple[str, str]] = [
    (r"\bh[eéêế]t\s+en\s+s[aâ]u\s+[đd][ơo]\b", "Head & Shoulders"),
    (r"\bn[ăa]m\s+trong\s+m[oộ]t\b", "5 in 1"),
    (r"\bn[ăa]m\s+m[uư][ơo]i\s+mi\s+li\s+l[ií]t\b", "50ml"),
    (r"\b(\d+)\s+mi\s+li\s+l[ií]t\b", r"\1ml"),
    (r"\bhai\s+ph[aẩ]y\s+t[aá]m\s+ph[aầ]n\s+tr[ăa]m\b", "2.8%"),
    (r"\bni\s+a\s+xi\s+na\s+mai\b", "Niacinamide"),
    (r"\bmen\s+th[oô]\b", "Menthol"),
    (r"\bph[ờo]\s+ri\s+s[ií]p\s+[ií]ch\s+tra\b", "Freeship Xtra"),
    (r"\bph[ờo]\s+ri\s+s[ií]p\b", "Freeship"),
    (r"\bph[ờo]\s+l[aá]t\s+s[eê]u\b", "Flash Sale"),
    (r"\bb[eé]t\s+seo\s+l[ơo]\b", "Best Seller"),
    (r"\bt[ií]ch\s+t[oó]c\s+s[oó]p\b", "TikTok Shop"),
    (r"\bt[ií]ch\s+t[oó]c\b", "TikTok"),
    (r"\bvao\s+ch[ờo]\b", "voucher"),
    (r"\bri\s+viu\b", "review"),
    (r"\b[ăa]n\s+b[oó]c\b", "unbox"),
    (r"\bcom\s+bo\b", "combo"),
    (r"\b[đd]iu\b", "deal"),
    (r"\bs[eê]u\b", "sale"),
    (r"\bs[oó]p\b", "shop"),
]

HALLUCINATION_RE = re.compile(
    r"(?is)(?:hãy\s+subscribe.*|ghiền\s+mì\s+gõ.*|la\s+la\s+school.*|đăng\s+ký\s+kênh.*|cảm\s+ơn\s+các\s+bạn.*|hãy\s+like\s+và\s+share.*)"
)

DEFAULT_STYLE_DNA: dict[str, Any] = {
    "channel_name": "TikTok Shop Review",
    "badge_style": "floral_plus_callouts",
    "hook_y": 0.16,
    "subtitle_y": 0.72,
    "font_heading": "Baloo 2",
    "font_brand": "Montserrat Black",
    "font_script": "Dancing Script",
    "palette": ["#FFF380", "#FFFFFF", "#FF4D6D", "#FF9F1C", "#A8DADC", "#95D5B2"],
    "stroke_color": "#000000",
    "stroke_width": 9,
    "subtitle_active_color": "#FFE500",
    "bgm_volume": 0.24,
    "bgm_track": "bgm_upbeat_tiktok.wav",
    "sfx_volume": 0.55,
    "asl_seconds": 2.2,
    "creative_mode": "breakthrough_ai",
    "camera_intensity": "dynamic_ai",
    "transition_level": "balanced",
    "icon_density": "balanced",
    "sticker_density": "normal",
    "visual_theme": "auto",
    "layout_style": "full",
    "color_preset": "natural",
    "reference_frames": [],
}

CONTENT_VIBE_PRESETS: dict[str, dict[str, Any]] = {
    "learned_dna": {
        "id": "learned_dna",
        "label": "✨ Theo Style DNA đã học (Mặc định · Không ghi đè)",
        "is_vlog": False,
        "cta_default": "Bấm giỏ hàng góc trái chốt liền nha.",
        "prompt_hint": "",
    },
    "outdoor_picnic": {
        "id": "outdoor_picnic",
        "label": "🏕️ Dã ngoại / Camping / Picnic (Thiên nhiên & Nhật ký)",
        "is_vlog": True,
        "cta_default": "Lưu lại cuối tuần rủ hội bạn đi chill ngay nha.",
        "prompt_hint": "Phong cách vlog dã ngoại, camping, picnic ngoài trời: giọng kể tự nhiên, thư giãn, tả cảm giác nắng gió, cây cỏ, khoảnh khắc chill cùng bạn bè. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng, chốt đơn hay freeship.",
    },
    "travel_vlog": {
        "id": "travel_vlog",
        "label": "✈️ Du lịch / Travel Vlog (Cinematic & Khám phá)",
        "is_vlog": True,
        "cta_default": "Theo dõi để cùng khám phá thêm nhiều điểm đẹp nữa nha.",
        "prompt_hint": "Phong cách travel vlog trên mạng: mở đầu bằng cảm xúc đặt chân tới địa điểm, review góc chụp đẹp, kinh nghiệm đi lại và khoảnh khắc đáng nhớ. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng, chốt đơn hay bán hàng.",
    },
    "food_cafe": {
        "id": "food_cafe",
        "label": "🍜 Ẩm thực / Cafe / Chill (Review không gian & hương vị)",
        "is_vlog": True,
        "cta_default": "Lưu lại địa điểm này cho cuối tuần hẹn hò nhé.",
        "prompt_hint": "Phong cách food/cafe vlog: tả không gian quán, ánh sáng, âm thanh, hương vị đồ ăn thức uống chân thật như chia sẻ với bạn thân. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay chốt đơn.",
    },
    "daily_story": {
        "id": "daily_story",
        "label": "📖 Daily Vlog / Storytelling (Tâm sự & Đời sống)",
        "is_vlog": True,
        "cta_default": "Còn bạn, cuối tuần này bạn dự định làm gì nè.",
        "prompt_hint": "Phong cách daily vlog storytelling nhẹ nhàng kiểu phim ngắn đời sống, kể chuyện gần gũi, nhịp câu có khoảng thở tự nhiên. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay bán hàng.",
    },
    "creative_internet": {
        "id": "creative_internet",
        "label": "🌐 Tự do Sáng tạo (Style Vlog/Trend trên mạng)",
        "is_vlog": True,
        "cta_default": "Thấy hay thì thả tim và lưu video lại nha.",
        "prompt_hint": "Phong cách sáng tạo tự do theo trend mạng xã hội: câu hook tò mò, góc nhìn mới mẻ, năng lượng tích cực, không rập khuôn bán hàng hay giỏ hàng.",
    },
    "detective_mystery": {
        "id": "detective_mystery",
        "label": "🕵️ Thám tử điều tra (Soi manh mối, bí ẩn)",
        "is_vlog": True,
        "cta_default": "Bạn có phát hiện manh mối nào khác không, bình luận bên dưới nhé.",
        "prompt_hint": "Nhập vai Thám tử điều tra / Phá án: soi từng chi tiết nhỏ trong khung hình như tìm manh mối, đặt câu hỏi bí ẩn kích thích tò mò, giọng điệu trinh thám lôi cuốn. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay bán hàng.",
    },
    "pov_comedy": {
        "id": "pov_comedy",
        "label": "😂 POV Hài hước dí dỏm (Bình luận duyên dáng)",
        "is_vlog": True,
        "cta_default": "Tag ngay đứa bạn thân vào xem đoạn này đi nha.",
        "prompt_hint": "Phong cách POV hài hước, tự thoại dí dỏm, phản ứng bất ngờ hoặc châm biếm nhẹ nhàng đầy duyên dáng trước các tình huống trong khung hình. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay bán hàng.",
    },
    "field_report": {
        "id": "field_report",
        "label": "🎙️ Phóng sự hiện trường (Kịch tính, dứt khoát)",
        "is_vlog": True,
        "cta_default": "Theo dõi để cập nhật những thước phim hiện trường tiếp theo.",
        "prompt_hint": "Phong cách phóng viên hiện trường / phim tài liệu kịch tính: câu văn ngắn gọn, dứt khoát, mở đầu gây tò mò mạnh và dẫn dắt mạch lạc. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay bán hàng.",
    },
    "cinematic_deep": {
        "id": "cinematic_deep",
        "label": "🎬 Điện ảnh sâu lắng (Tự sự giàu cảm xúc)",
        "is_vlog": True,
        "cta_default": "Lưu lại khoảnh khắc bình yên này nhé.",
        "prompt_hint": "Phong cách điện ảnh tự sự sâu lắng, giàu chất thơ và cảm xúc, câu văn tinh tế như lời dẫn phim. TUYỆT ĐỐI KHÔNG nhắc giỏ hàng hay bán hàng.",
    },
}


def get_content_vibe_meta(vibe_id: str | None) -> dict[str, Any]:
    key = (vibe_id or "learned_dna").strip()
    return dict(CONTENT_VIBE_PRESETS.get(key) or CONTENT_VIBE_PRESETS["learned_dna"])


def is_vlog_vibe(vibe_id: str | None) -> bool:
    return bool(get_content_vibe_meta(vibe_id).get("is_vlog"))


def _srt_ts_to_sec(ts: str) -> float:
    m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", ts.strip())
    if not m:
        return 0.0
    h, m_, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return round(h * 3600 + m_ * 60 + s + ms / 1000.0, 3)


def _gtx_translate_vi_to_en(text: str, timeout: int = 12) -> str:
    """Translate a string (or newline-joined lines) from Vietnamese to English via Google Translate GTX."""
    import urllib.parse
    import urllib.request

    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=vi&tl=en&dt=t&q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        return ""
    return "".join(str(seg[0]) for seg in data[0] if isinstance(seg, list) and seg and seg[0]).strip()


def translate_srt_lines_to_english(
    lines: list[str],
    cache_dir: Path | None = None,
    gemini_api_key: str = "",
) -> list[str]:
    """Translate Vietnamese SRT subtitle lines to concise English 1-to-1 with per-project caching."""
    cleaned_inputs = [re.sub(r"\s+", " ", str(ln or "")).strip() for ln in lines]
    if not cleaned_inputs:
        return []

    ws_dir = Path(cache_dir) if cache_dir else DIR_WORKSPACE
    cache_path = ws_dir / "en_subs_cache.json"
    cache: dict[str, str] = {}
    if cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                cache = {str(k): str(v) for k, v in loaded.items() if str(k).strip() and str(v).strip()}
        except Exception:
            cache = {}

    missing: list[str] = []
    seen_missing: set[str] = set()
    for txt in cleaned_inputs:
        if txt and txt not in cache and txt not in seen_missing:
            seen_missing.add(txt)
            missing.append(txt)

    if missing:
        eff_key = str(gemini_api_key or "").strip()
        if not eff_key:
            cfg_p = ws_dir / "webapp_config.json"
            if cfg_p.exists():
                try:
                    eff_key = str(json.loads(cfg_p.read_text(encoding="utf-8-sig")).get("gemini_api_key") or "").strip()
                except Exception:
                    eff_key = ""

        # Strategy 1: Batch JSON translation via Gemini Flash (natural concise spoken English)
        if eff_key:
            import urllib.request

            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={eff_key}"
            for i in range(0, len(missing), 45):
                batch = missing[i : i + 45]
                prompt = (
                    "Translate each Vietnamese video subtitle line below into concise, natural conversational English "
                    "(aim for 4-10 words per line so it reads comfortably as a video subtitle). "
                    f"Return ONLY a JSON array of strings of exact length {len(batch)} matching order 1-to-1.\n\n"
                    f"Input lines:\n{json.dumps(batch, ensure_ascii=False)}"
                )
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                }
                try:
                    req = urllib.request.Request(
                        endpoint,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        rdata = json.loads(resp.read().decode("utf-8"))
                    txt_out = (
                        rdata.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    arr = json.loads(txt_out) if txt_out else []
                    if isinstance(arr, list) and len(arr) == len(batch):
                        for src_t, tr_t in zip(batch, arr):
                            en_clean = re.sub(r"\s+", " ", str(tr_t or "")).strip()
                            if en_clean:
                                cache[src_t] = en_clean
                except Exception:
                    pass

        # Strategy 2: Free Google Translate GTX endpoint for any still-missing lines
        still_missing = [txt for txt in missing if txt not in cache]
        if still_missing:
            for i in range(0, len(still_missing), 25):
                chunk = still_missing[i : i + 25]
                try:
                    joined = "\n".join(chunk)
                    tr_joined = _gtx_translate_vi_to_en(joined)
                    parts = [re.sub(r"\s+", " ", p).strip() for p in tr_joined.splitlines()]
                    if len(parts) == len(chunk) and all(parts):
                        for src_t, tr_t in zip(chunk, parts):
                            cache[src_t] = tr_t
                        continue
                except Exception:
                    pass
                # Safe line-by-line fallback within chunk if newline count mismatched
                for src_t in chunk:
                    if src_t in cache:
                        continue
                    try:
                        en_one = re.sub(r"\s+", " ", _gtx_translate_vi_to_en(src_t)).strip()
                        if en_one:
                            cache[src_t] = en_one
                    except Exception:
                        pass

        if cache:
            try:
                ws_dir.mkdir(parents=True, exist_ok=True)
                tmp_c = cache_path.with_suffix(".tmp.json")
                tmp_c.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp_c, cache_path)
            except Exception:
                pass

    return [cache.get(txt, txt) if txt else "" for txt in cleaned_inputs]


def ensure_words_json_from_srt(
    srt_path: Path | None = None,
    words_json_path: Path | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Build or load word-level timestamps for Remotion Karaoke subtitles."""
    srt_path = srt_path or FILE_SRT
    words_json_path = words_json_path or FILE_WORDS_JSON
    if not force and words_json_path.exists():
        try:
            existing = json.loads(words_json_path.read_text(encoding="utf-8-sig"))
            if isinstance(existing, list) and len(existing) > 0:
                return existing
        except Exception:
            pass

    if not srt_path.exists():
        return []

    raw = srt_path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\r?\n\s*\r?\n", raw)
    words_out: list[dict[str, Any]] = []

    for blk in blocks:
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        ts_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else -1)
        if ts_idx < 0:
            continue
        parts = lines[ts_idx].split("-->")
        if len(parts) != 2:
            continue
        start_s = _srt_ts_to_sec(parts[0])
        end_s = _srt_ts_to_sec(parts[1])
        text = " ".join(lines[ts_idx + 1 :]).strip()
        tokens = text.split()
        if not tokens:
            continue
        dur = max(0.15, end_s - start_s)
        total_chars = sum(len(t) for t in tokens) or 1
        cur = start_s
        for idx, tok in enumerate(tokens):
            share = dur * (len(tok) / total_chars)
            nxt = end_s if idx == len(tokens) - 1 else round(cur + max(0.06, share), 3)
            words_out.append({"word": tok, "start": round(cur, 3), "end": round(nxt, 3)})
            cur = nxt

    words_json_path.parent.mkdir(parents=True, exist_ok=True)
    words_json_path.write_text(json.dumps(words_out, ensure_ascii=False, indent=2), encoding="utf-8")
    return words_out


def extract_reference_frames() -> list[str]:
    """Copy representative Hook and Mid frames from 04_workspace/frames/01_video_mau."""
    DIR_WORKSPACE.mkdir(parents=True, exist_ok=True)
    refs: list[str] = []
    if not DIR_FRAMES_MAU.exists():
        return refs

    subdirs = sorted([p for p in DIR_FRAMES_MAU.iterdir() if p.is_dir()])
    if not subdirs:
        return refs

    first_dir = subdirs[0]
    first_frames = sorted(first_dir.glob("frame_*.jpg"))
    if first_frames:
        shutil.copyfile(first_frames[0], FILE_REF_HOOK)
        refs.append("04_workspace/style_ref_hook.jpg")

    mid_candidate: Path | None = None
    # Prefer another sample video's mid frame if available, else middle of first video
    mid_dir = subdirs[-1] if len(subdirs) > 1 else first_dir
    mid_frames = sorted(mid_dir.glob("frame_*.jpg"))
    if mid_frames:
        mid_candidate = mid_dir / "frame_0010.jpg"
        if not mid_candidate.exists():
            mid_candidate = mid_frames[min(len(mid_frames) - 1, max(1, len(mid_frames) // 3))]
        shutil.copyfile(mid_candidate, FILE_REF_MID)
        refs.append("04_workspace/style_ref_Mid.jpg")

    return refs


def load_style_dna() -> dict[str, Any]:
    dna = dict(DEFAULT_STYLE_DNA)
    if FILE_STYLE_DNA.exists():
        try:
            loaded = json.loads(FILE_STYLE_DNA.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                dna.update(loaded)
        except Exception:
            pass
    return dna


def update_style_dna(
    overrides: dict[str, Any] | None = None,
    force_reset: bool = False,
) -> dict[str, Any]:
    """Ensure style_dna.json and reference frames are extracted and persisted."""
    dna = dict(DEFAULT_STYLE_DNA) if force_reset else load_style_dna()
    refs = extract_reference_frames()
    if refs:
        dna["reference_frames"] = refs

    # Infer ASL or highlight colors from phong_cach_kenh.md if present
    if FILE_REF_HOOK.parent != DIR_WORKSPACE:
        FILE_REF_HOOK.parent.mkdir(parents=True, exist_ok=True)
    if not FILE_STYLE_GUIDE.exists() and (DIR_WORKSPACE / "phong_cach_kenh.md").exists():
        try:
            shutil.copy2(DIR_WORKSPACE / "phong_cach_kenh.md", FILE_STYLE_GUIDE)
        except Exception:
            pass
    if FILE_STYLE_GUIDE.exists():
        guide_txt = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig")
        asl_match = re.search(r"(\d+(?:\.\d+)?)\s*[sS]\s*[–-]\s*(\d+(?:\.\d+)?)\s*[sS]\s*/\s*cảnh", guide_txt)
        if asl_match and "asl_seconds" not in (overrides or {}):
            lo, hi = float(asl_match.group(1)), float(asl_match.group(2))
            dna["asl_seconds"] = round((lo + hi) / 2.0, 2)

    if overrides:
        for k, v in overrides.items():
            if v is not None:
                dna[k] = v

    FILE_STYLE_DNA.parent.mkdir(parents=True, exist_ok=True)
    FILE_STYLE_DNA.write_text(json.dumps(dna, ensure_ascii=False, indent=2), encoding="utf-8")
    return dna


def _trim_wav_beat_silence(wav_path: Path, b_start: float, b_end: float) -> tuple[float, float]:
    """Detect actual voiced [start, end] inside a WAV beat window to remove TTS leading/trailing silence."""
    if b_end - b_start < 0.25 or not wav_path.exists() or wav_path.suffix.lower() != ".wav":
        return (b_start, b_end)
    try:
        import array
        import math

        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate() or 24000
            n_ch = wf.getnchannels() or 1
            sw = wf.getsampwidth()
            if sw != 2:
                return (b_start, b_end)
            f_start = max(0, int(b_start * sr))
            f_end = min(wf.getnframes(), int(b_end * sr))
            if f_end - f_start < int(0.15 * sr):
                return (b_start, b_end)
            wf.setpos(f_start)
            raw = wf.readframes(f_end - f_start)
        samples = array.array("h")
        samples.frombytes(raw)
        if n_ch > 1:
            samples = array.array("h", samples[::n_ch])
        win = max(1, int(0.015 * sr))  # 15ms frames
        rms_list: list[float] = []
        for i in range(0, len(samples), win):
            chunk = samples[i : i + win]
            if not chunk:
                continue
            mean_sq = sum(s * s for s in chunk) / float(len(chunk))
            rms_list.append(math.sqrt(mean_sq))
        if not rms_list:
            return (b_start, b_end)
        peak = max(rms_list)
        if peak < 180.0:
            return (b_start, b_end)
        thresh = max(120.0, peak * 0.08)
        active_idx = [idx for idx, val in enumerate(rms_list) if val >= thresh]
        if not active_idx:
            return (b_start, b_end)
        lead_s = max(0.0, (active_idx[0] * win) / float(sr) - 0.025)
        tail_e = min(b_end - b_start, ((active_idx[-1] + 1) * win) / float(sr) + 0.035)
        new_s = round(b_start + lead_s, 3)
        new_e = round(b_start + tail_e, 3)
        if new_e - new_s >= 0.25:
            return (new_s, new_e)
    except Exception:
        pass
    return (b_start, b_end)


def _align_tokens_to_beat_window(
    tokens: list[str],
    s_start: float,
    s_end: float,
    beat_whisper_words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Anchor exact display_text tokens to matching Whisper words via SequenceMatcher, interpolating only local gaps."""
    import difflib

    if not tokens:
        return []
    n_tok = len(tokens)
    dur = max(0.15, s_end - s_start)
    weights = [
        max(1, len(re.sub(r"[^\wÀ-ỹà-ỹ0-9]", "", t))) + (1.2 if t.endswith((",", ";", ":")) else 0.0)
        for t in tokens
    ]
    w_total = sum(weights) or 1.0

    def _norm_tok(t: str) -> str:
        return re.sub(r"[^\wÀ-ỹà-ỹ0-9]", "", (t or "").lower())

    if len(beat_whisper_words) >= 2:
        w_sorted = sorted(beat_whisper_words, key=lambda x: float(x.get("start") or 0.0))
        a_start = max(s_start - 0.05, float(w_sorted[0].get("start") or s_start))
        a_end = min(s_end + 0.05, float(w_sorted[-1].get("end") or s_end))
        if a_end - a_start >= dur * 0.45:
            disp_norm = [_norm_tok(t) for t in tokens]
            whisp_norm = [_norm_tok(str(w.get("word") or "")) for w in w_sorted]
            sm = difflib.SequenceMatcher(None, disp_norm, whisp_norm, autojunk=False)

            anchored_s: list[float | None] = [None] * n_tok
            anchored_e: list[float | None] = [None] * n_tok
            matched_cnt = 0
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    for k in range(i2 - i1):
                        ws = float(w_sorted[j1 + k].get("start") or a_start)
                        we = float(w_sorted[j1 + k].get("end") or (ws + 0.08))
                        anchored_s[i1 + k] = round(ws, 3)
                        anchored_e[i1 + k] = round(max(ws + 0.04, we), 3)
                        matched_cnt += 1

            if matched_cnt >= 2:
                out: list[dict[str, Any]] = [{"word": t, "start": 0.0, "end": 0.0} for t in tokens]
                idx = 0
                while idx < n_tok:
                    if anchored_s[idx] is not None:
                        out[idx]["start"] = float(anchored_s[idx])  # type: ignore[arg-type]
                        out[idx]["end"] = float(anchored_e[idx])  # type: ignore[arg-type]
                        idx += 1
                        continue
                    # Fill unmatched span [idx..j-1] tightly between prev_end and next_start
                    j = idx
                    while j < n_tok and anchored_s[j] is None:
                        j += 1
                    gap_start = out[idx - 1]["end"] if idx > 0 else a_start
                    gap_end = float(anchored_s[j]) if j < n_tok else a_end  # type: ignore[arg-type]
                    if gap_end <= gap_start + 0.03 * (j - idx):
                        gap_end = gap_start + 0.05 * (j - idx)
                    span_w = sum(weights[idx:j]) or 1.0
                    cur = gap_start
                    for k in range(idx, j):
                        nxt = gap_end if k == j - 1 else round(cur + (gap_end - gap_start) * (weights[k] / span_w), 3)
                        out[k]["start"] = round(cur, 3)
                        out[k]["end"] = round(max(cur + 0.04, nxt), 3)
                        cur = out[k]["end"]
                    idx = j

                # Guarantee strictly non-decreasing monotonic word boundaries
                for k in range(1, n_tok):
                    if out[k]["start"] < out[k - 1]["end"]:
                        out[k]["start"] = out[k - 1]["end"]
                    if out[k]["end"] <= out[k]["start"]:
                        out[k]["end"] = round(out[k]["start"] + 0.04, 3)
                return out

            # Fallback to cumulative Whisper boundary interpolation if very few exact matches
            m = len(w_sorted)
            cum_w = [0.0]
            for wt in weights:
                cum_w.append(cum_w[-1] + wt / w_total)

            def _interp_whisper(frac: float) -> float:
                pos = max(0.0, min(float(m), frac * m))
                i_m = int(pos)
                rem = pos - i_m
                if i_m >= m:
                    return float(w_sorted[-1].get("end") or a_end)
                ws = float(w_sorted[i_m].get("start") or a_start)
                we = float(w_sorted[i_m].get("end") or ws + 0.1)
                return round(ws + (we - ws) * rem, 3)

            out = []
            prev_t = round(a_start, 3)
            for wi, tok in enumerate(tokens):
                t0 = prev_t
                t1 = round(a_end, 3) if wi == n_tok - 1 else max(t0 + 0.05, _interp_whisper(cum_w[wi + 1]))
                if t1 > a_end and wi < n_tok - 1:
                    t1 = round(a_end - 0.04 * (n_tok - 1 - wi), 3)
                t1 = max(t0 + 0.04, t1)
                out.append({"word": tok, "start": round(t0, 3), "end": round(t1, 3)})
                prev_t = t1
            return out

    out = []
    cur = s_start
    for wi, tok in enumerate(tokens):
        share = dur * (weights[wi] / w_total)
        nxt = s_end if wi == n_tok - 1 else round(cur + max(0.05, share), 3)
        out.append({"word": tok, "start": round(cur, 3), "end": round(nxt, 3)})
        cur = nxt
    return out


def load_channel_script_dna_context(
    max_guide_chars: int = 3600,
    max_transcript_chars: int = 2400,
) -> dict[str, str]:
    """Load shared channel style guide + sample video transcripts so new scripts inherit channel DNA."""
    guide_txt = FILE_STYLE_GUIDE.read_text(encoding="utf-8-sig").strip() if FILE_STYLE_GUIDE.exists() else ""
    loi_thoai_file = DIR_FRAMES_MAU / "loi_thoai_goc.md"
    transcripts_txt = loi_thoai_file.read_text(encoding="utf-8-sig").strip() if loi_thoai_file.exists() else ""

    combined = f"{guide_txt}\n{transcripts_txt}".lower()
    pronoun = "mấy bà"
    for cand in ("mấy bà", "mọi người", "các bạn", "mấy bạn", "anh chị em", "cả nhà"):
        if cand in combined:
            pronoun = cand
            break

    return {
        "style_guide": guide_txt[:max_guide_chars],
        "sample_transcripts": transcripts_txt[:max_transcript_chars],
        "pronoun": pronoun,
    }


def _sec_to_srt_ts(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _probe_duration_sec(media_path: Path) -> float:
    if not media_path.exists():
        return 0.0
    if media_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(media_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 24000
                return round(frames / float(rate), 3)
        except Exception:
            pass
    ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffprobe and os.name == "nt":
        winget_root = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
        if winget_root.exists():
            for cand in winget_root.rglob("ffprobe.exe"):
                ffprobe = str(cand)
                break
    if ffprobe:
        try:
            res = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(media_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if res.returncode == 0 and res.stdout.strip():
                return round(float(res.stdout.strip()), 3)
        except Exception:
            pass
    return 0.0


def load_brand_brief() -> dict[str, Any]:
    """Load 04_workspace/brand_brief.json for the active project."""
    base = EMPTY_BRAND_BRIEF
    brief: dict[str, Any] = {
        **base,
        "phonetic_map": dict(base["phonetic_map"]),
    }
    if FILE_BRAND_BRIEF.exists():
        try:
            loaded = json.loads(FILE_BRAND_BRIEF.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                pm = loaded.pop("phonetic_map", None)
                brief.update(loaded)
                if isinstance(pm, dict):
                    merged_pm = dict(base["phonetic_map"])
                    merged_pm.update({str(k): str(v) for k, v in pm.items() if str(k).strip() and str(v).strip()})
                    brief["phonetic_map"] = merged_pm
        except Exception:
            pass
    return brief


def _normalize_brief_text_field(val: Any) -> str:
    """Convert Python/JSON list or stringified list like \"['a', 'b']\" into clean comma-separated text."""
    if isinstance(val, list):
        return ", ".join(str(x).strip(" '\"") for x in val if str(x).strip())
    s = str(val or "").strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            import ast
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return ", ".join(str(x).strip() for x in parsed if str(x).strip())
        except Exception:
            pass
    return s


def save_brand_brief(patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist brand_brief.json after merging any updates (auto-heuristic if only raw_brief provided)."""
    brief = load_brand_brief()
    if patch:
        for k, v in patch.items():
            if k == "phonetic_map" and isinstance(v, dict):
                merged = dict(brief.get("phonetic_map") or {})
                merged.update({str(pk): str(pv) for pk, pv in v.items() if str(pk).strip() and str(pv).strip()})
                brief["phonetic_map"] = merged
            elif k == "target_duration_sec" and v is not None:
                try:
                    brief["target_duration_sec"] = round(max(8.0, min(90.0, float(v))), 1)
                except Exception:
                    pass
            elif k in ("usps", "banned_words") and v is not None:
                brief[k] = _normalize_brief_text_field(v)
            elif v is not None:
                brief[k] = v
    raw_b = str(brief.get("raw_brief") or "").strip()
    if len(raw_b) >= 12 and not str(brief.get("brand") or "").strip():
        heur = parse_raw_brand_brief_heuristic(raw_b, target_duration_sec=float(brief.get("target_duration_sec") or 25.0))
        for hk in ("brand", "product_line", "category", "usps", "offer_cta"):
            if not str(brief.get(hk) or "").strip() and heur.get(hk):
                brief[hk] = _normalize_brief_text_field(heur[hk])
    FILE_BRAND_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    FILE_BRAND_BRIEF.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    return brief


def is_brand_brief_ready(brief: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Gatekeeper verifying Brand Brief is configured before automated planning or 1-Click render."""
    if brief is None and not FILE_BRAND_BRIEF.exists():
        return (
            False,
            "Chưa lưu Brief Nhãn Hàng (Bước 1). Vui lòng điền Thương hiệu, Sản phẩm/USP và bấm Lưu Brief trước.",
        )
    data = brief if brief is not None else load_brand_brief()
    brand = str(data.get("brand") or "").strip()
    usps = str(data.get("usps") or "").strip()
    raw_brief = str(data.get("raw_brief") or "").strip()
    prod = str(data.get("product_line") or "").strip()
    try:
        dur = float(data.get("target_duration_sec") or 0.0)
    except Exception:
        dur = 0.0

    if len(raw_brief) >= 12 and dur >= 8.0:
        return True, "OK"

    if not brand or brand.lower() in ("chưa thiết lập", "chưa có"):
        return (
            False,
            "Vui lòng điền Brief Nhãn Hàng (Thương hiệu, Sản phẩm/USP & Thời lượng) ở Bước 1 trước khi chạy tự động.",
        )
    if max(len(usps), len(raw_brief), len(prod)) < 5:
        return (
            False,
            "Brief Nhãn Hàng đang thiếu thông tin sản phẩm / USP (cần ít nhất 5 ký tự) ở Bước 1.",
        )
    if dur < 8.0:
        return (False, "Thời lượng mục tiêu phải từ 8 giây trở lên ở Bước 1.")
    return (True, f"Đã đủ điều kiện ({brand} · {dur:.0f}s)")


def parse_raw_brand_brief_heuristic(
    raw_brief: str,
    target_duration_sec: float = 25.0,
) -> dict[str, Any]:
    """Extract brand brief fields & phonetic hints cleanly without requiring an LLM."""
    text = (raw_brief or "").strip()
    cur = load_brand_brief()
    out: dict[str, Any] = {
        **cur,
        "raw_brief": text,
        "target_duration_sec": round(max(8.0, min(90.0, float(target_duration_sec or 25.0))), 1),
        "phonetic_map": dict(cur.get("phonetic_map") or EMPTY_BRAND_BRIEF["phonetic_map"]),
    }
    if not text:
        return out

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if any(p in low for p in ("thương hiệu:", "brand:", "hãng:")):
            out["brand"] = ln.split(":", 1)[1].strip().upper()
        elif any(p in low for p in ("dòng sản phẩm:", "dòng sp:", "product:", "tên sp:", "sản phẩm:")):
            out["product_line"] = ln.split(":", 1)[1].strip()
        elif any(p in low for p in ("danh mục:", "loại:", "category:")):
            out["category"] = ln.split(":", 1)[1].strip().lower()
        elif any(p in low for p in ("ưu đãi:", "cta:", "deal:", "khuyến mãi:", "voucher:")):
            out["offer_cta"] = ln.split(":", 1)[1].strip()
        elif any(p in low for p in ("cấm:", "tránh:", "không nhắc:", "lưu ý:", "banned:")):
            out["banned_words"] = ln.split(":", 1)[1].strip()

    # Auto-detect known/common brands or English words if explicit label missing
    low_full = text.lower()
    if "colgate" in low_full:
        out["brand"] = "COLGATE"
        if "maxfresh" in low_full or "max fresh" in low_full:
            out["product_line"] = "MaxFresh"
    elif "head" in low_full and "shoulder" in low_full:
        out["brand"] = "HEAD & SHOULDERS"

    # Extract USPs from full text if no specific override was provided
    usp_lines = [
        ln for ln in lines
        if not any(ln.lower().startswith(k) for k in ("thương hiệu:", "brand:", "cấm:", "tránh:", "banned:", "không nhắc:"))
    ]
    if usp_lines:
        out["usps"] = "; ".join(usp_lines)[:600]

    # Auto-add common phonetic hints for detected percentages/ml/English tokens
    for m in re.finditer(r"(\d+)\s*ml\b", text, flags=re.I):
        tok = f"{m.group(1)}ml"
        out["phonetic_map"].setdefault(tok, f"{m.group(1)} mi li lít")
    return out


def restore_display_text(text: str, brand_brief: dict[str, Any] | None = None) -> str:
    """Clean hallucinated phrases and convert TTS phonetic tokens back to proper brand/display spellings."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = HALLUCINATION_RE.sub("", cleaned).strip()

    brief = brand_brief or load_brand_brief()
    pm = brief.get("phonetic_map") or {}
    # Apply longest custom phonetic phrases first
    for display_tok, spoken_tok in sorted(pm.items(), key=lambda kv: -len(str(kv[1]))):
        st = str(spoken_tok).strip()
        dt = str(display_tok).strip()
        if st and dt and st.lower() != dt.lower():
            cleaned = re.sub(rf"(?<!\w){re.escape(st)}(?!\w)", dt, cleaned, flags=re.IGNORECASE)

    for pattern, repl in DEFAULT_PHONETIC_TO_DISPLAY:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned:
        # Capitalize first character of each sentence
        parts = re.split(r"([.!?]\s+)", cleaned)
        out_parts = []
        for idx, p in enumerate(parts):
            if idx % 2 == 0 and p:
                out_parts.append(p[0].upper() + p[1:])
            else:
                out_parts.append(p)
        cleaned = "".join(out_parts)
    return cleaned


def _split_sentences(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return []
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    return sents or [clean]


def _group_words_to_srt_entries(
    words_out: list[dict[str, Any]],
    max_words: int = 4,
    max_chars: int = 22,
) -> list[tuple[float, float, str]]:
    if not words_out:
        return []
    entries: list[tuple[float, float, str]] = []
    buf: list[dict[str, Any]] = []

    def flush_buf() -> None:
        if not buf:
            return
        line = " ".join(str(x["word"]) for x in buf)
        line = re.sub(r"\s+([.,!?;:])", r"\1", line).strip()
        if line:
            entries.append((float(buf[0]["start"]), float(buf[-1]["end"]), line))
        buf.clear()

    for item in words_out:
        tok = str(item["word"])
        if buf:
            cur_len = sum(len(str(x["word"])) + 1 for x in buf) + len(tok)
            gap = float(item["start"]) - float(buf[-1]["end"])
            if len(buf) >= max_words or cur_len > max_chars or gap > 0.35:
                flush_buf()
        buf.append(item)
        if tok.endswith((".", "!", "?", ";")) and len(buf) >= 2:
            flush_buf()
        elif tok.endswith(",") and len(buf) >= 4:
            flush_buf()
    flush_buf()
    return entries


def repair_subtitles_and_beats(
    total_duration_override: float | None = None,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Ensure voice_beats.json, 03_words.json, and 03_phu_de.srt cover the full clean script without hallucinations."""
    brief = load_brand_brief()
    wav_dur = float(total_duration_override or _probe_duration_sec(FILE_TTS_WAV) or 0.0)
    if wav_dur <= 0.1:
        wav_dur = float(brief.get("target_duration_sec") or 15.27)

    raw_tts = FILE_SCRIPT.read_text(encoding="utf-8-sig").strip() if FILE_SCRIPT.exists() else ""
    disp_mtime = FILE_SCRIPT_DISPLAY.stat().st_mtime if FILE_SCRIPT_DISPLAY.exists() else 0.0
    tts_mtime = FILE_SCRIPT.stat().st_mtime if FILE_SCRIPT.exists() else 0.0
    if FILE_SCRIPT_DISPLAY.exists() and (tts_mtime - disp_mtime <= 1.0):
        raw_disp = FILE_SCRIPT_DISPLAY.read_text(encoding="utf-8-sig").strip()
        display_full = restore_display_text(raw_disp or raw_tts, brief)
    else:
        display_full = restore_display_text(raw_tts, brief)
        if display_full:
            FILE_SCRIPT_DISPLAY.parent.mkdir(parents=True, exist_ok=True)
            FILE_SCRIPT_DISPLAY.write_text(display_full + "\n", encoding="utf-8")

    disp_sents = _split_sentences(display_full)
    tts_sents = _split_sentences(raw_tts)

    existing_beats: dict[str, Any] = {}
    wav_mtime = FILE_TTS_WAV.stat().st_mtime if FILE_TTS_WAV.exists() else 0.0
    beats_mtime = FILE_VOICE_BEATS.stat().st_mtime if FILE_VOICE_BEATS.exists() else 0.0
    if not force_rebuild and FILE_VOICE_BEATS.exists() and beats_mtime >= (wav_mtime - 0.5):
        try:
            loaded_vb = json.loads(FILE_VOICE_BEATS.read_text(encoding="utf-8-sig"))
            if (
                isinstance(loaded_vb, dict)
                and isinstance(loaded_vb.get("beats"), list)
                and len(loaded_vb["beats"]) >= 1
                and abs(float(loaded_vb.get("total_duration_sec") or 0.0) - wav_dur) <= 0.6
                and all(float(b.get("end") or 0.0) > float(b.get("start") or 0.0) for b in loaded_vb["beats"])
            ):
                changed_disp = False
                for vb_item in loaded_vb["beats"]:
                    raw_dt = str(vb_item.get("display_text") or vb_item.get("tts_text") or "").strip()
                    clean_dt = restore_display_text(raw_dt, brief) if raw_dt else ""
                    if clean_dt and clean_dt != vb_item.get("display_text"):
                        vb_item["display_text"] = clean_dt
                        changed_disp = True
                if changed_disp:
                    FILE_VOICE_BEATS.write_text(json.dumps(loaded_vb, ensure_ascii=False, indent=2), encoding="utf-8")
                existing_beats = loaded_vb
        except Exception:
            existing_beats = {}

    if existing_beats:
        beats_data = existing_beats
    else:
        beats: list[dict[str, Any]] = []
        if disp_sents:
            pause_gap = 0.08 if len(disp_sents) > 1 else 0.0
            total_pause = pause_gap * max(0, len(disp_sents) - 1)
            usable_dur = max(1.0, wav_dur - total_pause)
            weights = [max(4, len(re.sub(r"[^\w]", "", s))) for s in disp_sents]
            w_sum = sum(weights) or 1
            cur_t = 0.0
            for idx, ds in enumerate(disp_sents):
                ts = tts_sents[idx] if idx < len(tts_sents) else ds
                share = (usable_dur * (weights[idx] / w_sum))
                end_t = wav_dur if idx == len(disp_sents) - 1 else round(cur_t + share, 3)
                beats.append(
                    {
                        "index": idx + 1,
                        "start": round(cur_t, 3),
                        "end": round(end_t, 3),
                        "duration": round(max(0.2, end_t - cur_t), 3),
                        "tts_text": ts,
                        "display_text": ds,
                    }
                )
                cur_t = round(end_t + pause_gap, 3)
        beats_data = {"total_duration_sec": round(wav_dur, 3), "beats": beats}
        FILE_VOICE_BEATS.parent.mkdir(parents=True, exist_ok=True)
        FILE_VOICE_BEATS.write_text(json.dumps(beats_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Validate current 03_words.json / 03_phu_de.srt against corruption or Whisper prefix-drop bug
    expected_word_cnt = len(display_full.split())
    existing_words: list[dict[str, Any]] = []
    if FILE_WORDS_JSON.exists() and not force_rebuild:
        try:
            loaded_w = json.loads(FILE_WORDS_JSON.read_text(encoding="utf-8-sig"))
            if isinstance(loaded_w, list):
                existing_words = loaded_w
        except Exception:
            existing_words = []

    joined_existing = " ".join(str(x.get("word") or "") for x in existing_words).lower()
    has_hallucination = bool(HALLUCINATION_RE.search(joined_existing)) or any(
        bad in joined_existing for bad in ("ghiền", "subscribe", "la la school")
    )
    missing_start = bool(existing_words) and float(existing_words[0].get("start") or 0.0) > 1.5
    too_few_words = len(existing_words) < max(6, int(expected_word_cnt * 0.7))

    if force_rebuild or not existing_words or has_hallucination or missing_start or too_few_words:
        whisper_raw_file = FILE_WORDS_JSON.parent / "03_whisper_raw.json"
        whisper_words: list[dict[str, Any]] = []
        if whisper_raw_file.exists():
            try:
                loaded_ww = json.loads(whisper_raw_file.read_text(encoding="utf-8-sig"))
                if isinstance(loaded_ww, list):
                    whisper_words = loaded_ww
            except Exception:
                whisper_words = []

        rebuilt_words: list[dict[str, Any]] = []
        for beat in beats_data.get("beats", []):
            tokens = str(beat.get("display_text") or "").split()
            if not tokens:
                continue
            b_start = float(beat["start"])
            b_end = float(beat["end"])
            s_start, s_end = _trim_wav_beat_silence(FILE_TTS_WAV, b_start, b_end)
            beat_ww = [
                w
                for w in whisper_words
                if isinstance(w, dict)
                and (b_start - 0.12) <= ((float(w.get("start") or 0.0) + float(w.get("end") or 0.0)) * 0.5) <= (b_end + 0.12)
            ]
            rebuilt_words.extend(_align_tokens_to_beat_window(tokens, s_start, s_end, beat_ww))

        if rebuilt_words:
            FILE_WORDS_JSON.parent.mkdir(parents=True, exist_ok=True)
            FILE_WORDS_JSON.write_text(json.dumps(rebuilt_words, ensure_ascii=False, indent=2), encoding="utf-8")
            srt_entries = _group_words_to_srt_entries(rebuilt_words)
            srt_blocks = [
                f"{si}\n{_sec_to_srt_ts(s_t)} --> {_sec_to_srt_ts(e_t)}\n{txt}\n"
                for si, (s_t, e_t, txt) in enumerate(srt_entries, start=1)
            ]
            FILE_SRT.write_text("\n".join(srt_blocks), encoding="utf-8")
            return {
                "repaired": True,
                "words_count": len(rebuilt_words),
                "srt_lines": len(srt_entries),
                "voice_beats": beats_data,
            }

    return {
        "repaired": False,
        "words_count": len(existing_words),
        "voice_beats": beats_data,
    }


COMMON_TTS_FALLBACK_RULES: list[tuple[str, str]] = [
    (r"\bhead\s*(?:&|and)\s*shoulders\b", "Hét en Sâu đơ"),
    (r"\bniacinamide\b", "Ni a xi na mai"),
    (r"\bmenthol\b", "Men thô"),
    (r"\b5\s*in\s*1\b", "năm trong một"),
    (r"\b5in1\b", "năm trong một"),
    (r"\b72\s*h\b", "bảy mươi hai giờ"),
    (r"\b72\s*giờ\b", "bảy mươi hai giờ"),
    (r"\btonic\b", "tô ních"),
    (r"\bleave[- ]on\b", "líp on"),
    (r"\bfree\s*ship\s*xtra\b", "miễn phí vận chuyển"),
    (r"\bfree\s*ship\b", "miễn phí vận chuyển"),
    (r"\bflash\s*sale\b", "giảm giá sốc"),
    (r"\bbest\s*seller\b", "bán chạy hàng đầu"),
    (r"\btik\s*tok\s*shop\b", "tích tóc sóp"),
    (r"\btik\s*tok\b", "tích tóc"),
    (r"\bvoucher\b", "mã giảm giá"),
    (r"\bunbox\b", "ăn bóc"),
    (r"\breview\b", "ri viu"),
    (r"\bcombo\b", "com bo"),
    (r"\bdeal\s+hời\b", "giá hời"),
    (r"\bsăn\s+deal\b", "săn ưu đãi"),
    (r"\bchốt\s+deal\b", "chốt đơn"),
    (r"\bdeal\b", "ưu đãi"),
    (r"\bsale\b", "giảm giá"),
    (r"\blive\b", "lai"),
    (r"\bshop\b", "sóp"),
]


def _vn_small_number(num_str: str) -> str:
    try:
        n = int(num_str)
    except Exception:
        return num_str
    units = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    if 0 <= n < 10:
        return units[n]
    if n < 20:
        if n == 10:
            return "mười"
        if n == 15:
            return "mười lăm"
        return f"mười {units[n % 10]}"
    if n < 100:
        tens, ones = divmod(n, 10)
        base = f"{units[tens]} mươi"
        if ones == 0:
            return base
        if ones == 1:
            return f"{base} mốt"
        if ones == 4:
            return f"{base} tư"
        if ones == 5:
            return f"{base} lăm"
        return f"{base} {units[ones]}"
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        base = f"{units[hundreds]} trăm"
        if rem == 0:
            return base
        if rem < 10:
            return f"{base} linh {units[rem]}"
        return f"{base} {_vn_small_number(str(rem))}"
    return num_str


def compute_target_word_budget(target_duration_sec: float) -> tuple[int, int, int]:
    """Return (target_words, min_words, target_sentences) calibrated for natural breathing room (~3.85 syl/s)."""
    dur = max(8.0, min(90.0, float(target_duration_sec or 30.0)))
    target_words = max(36, int(round(dur * 3.85)))
    min_words = max(30, int(round(dur * 3.35)))
    target_sentences = max(4, min(8, int(round(dur / 4.2))))
    return target_words, min_words, target_sentences


def convert_display_to_tts_script(display_text: str, brand_brief: dict[str, Any] | None = None) -> str:
    """Convert display Vietnamese script (with English brands/units) into clean F5-TTS phonetic text sentence-by-sentence."""
    brief = brand_brief or load_brand_brief()
    pm = brief.get("phonetic_map") or {}
    raw_sents = _split_sentences(display_text)
    if not raw_sents:
        return ""

    out_sents: list[str] = []
    for sent in raw_sents:
        s = re.sub(r"[*_`~\"()\[\]{}<>•👇🔥✨🚀🔒⚙️🎙️💡⚡✅❌⚠️📌🛒💬👉🎯]+", " ", sent)
        for display_tok, spoken_tok in sorted(pm.items(), key=lambda kv: -len(str(kv[0]))):
            dt = str(display_tok).strip()
            st = str(spoken_tok).strip()
            if dt and st:
                s = re.sub(rf"(?<!\w){re.escape(dt)}(?!\w)", st, s, flags=re.IGNORECASE)
        for pat, repl in COMMON_TTS_FALLBACK_RULES:
            s = re.sub(pat, repl, s, flags=re.IGNORECASE)
        s = re.sub(r"\s*&\s*", " và ", s)
        s = re.sub(r"(\d+)\s*[.,]\s*(\d+)\s*%", lambda m: f"{_vn_small_number(m.group(1))} phẩy {_vn_small_number(m.group(2))} phần trăm", s)
        s = re.sub(r"(\d+)\s*%", lambda m: f"{_vn_small_number(m.group(1))} phần trăm", s)
        s = re.sub(r"(\d+)\s*ml\b", lambda m: f"{_vn_small_number(m.group(1))} mi li lít", s, flags=re.IGNORECASE)
        s = re.sub(r"(\d+)\s*g\b", lambda m: f"{_vn_small_number(m.group(1))} gam", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(\d{1,3})\b", lambda m: _vn_small_number(m.group(1)), s)
        s = re.sub(r"[!?]+", ".", s)
        s = re.sub(r"[;:—–/]+", ", ", s)
        s = re.sub(r"\s*[.,]+\s*[.,]+\s*", ". ", s)
        s = re.sub(r"\s+([.,])", r"\1", s)
        s = re.sub(r",\s*,+", ",", s)
        s = re.sub(r"\s+", " ", s).strip(" .,")
        if s:
            out_sents.append(s[0].upper() + s[1:] + ".")
    return " ".join(out_sents)


def _trim_phrase_words(text: str, max_words: int = 14) -> str:
    raw = str(text or "")
    raw = re.sub(r"\[[^\]]+\]", " ", raw)
    raw = re.sub(r"[\[\]'\"]+", " ", raw)
    raw = re.sub(r"\s*[-–—/|]+\s*", ", ", raw)
    clean = re.sub(r"\s+", " ", raw).strip(" .,-:;")
    words = clean.split()
    if len(words) <= max_words:
        return clean
    sub = " ".join(words[:max_words]).rstrip(",.")
    # Prefer cutting cleanly at last comma if >= 5 words
    if "," in sub:
        before_comma = sub.rsplit(",", 1)[0].strip()
        if len(before_comma.split()) >= 5:
            sub = before_comma
    # Avoid leaving a dangling preposition/negation at the end (e.g. "Kissport Không")
    dangling = {"không", "và", "với", "cho", "của", "tại", "trong", "đến", "từ", "về", "như", "hoặc"}
    sub_words = sub.split()
    while len(sub_words) > 4 and sub_words[-1].rstrip(",.").lower() in dangling:
        sub_words.pop()
    return " ".join(sub_words).rstrip(",.")


def sanitize_cta_text(raw: str, max_chars: int = 34) -> str:
    """Shorten CTA text cleanly at word boundaries without ever cutting a word in half."""
    clean = re.sub(r"\s+", " ", (raw or "").strip()).strip(" .,-:;")
    if not clean:
        return "CHỐT ĐƠN NGAY GIỎ HÀNG 👇"
    if len(clean) <= max_chars:
        return clean
    words = clean.split()
    acc: list[str] = []
    for w in words:
        candidate = " ".join(acc + [w])
        if len(candidate) > max_chars:
            break
        acc.append(w)
    if len(acc) >= 3:
        trimmed = " ".join(acc).rstrip(",.;:!?")
        trimmed = re.sub(r",?\s*\b(?:bấm|nhấn|xem|vào|tại|kèm)\b$", "", trimmed, flags=re.IGNORECASE).strip(",.;:!? ")
        return (trimmed or "CHỐT DEAL HỜI GIỎ HÀNG") + " 👇"
    return "CHỐT DEAL HỜI GIỎ HÀNG 👇"


def _extract_brief_product_angles(brand_brief: dict[str, Any]) -> dict[str, str]:
    brand = str(brand_brief.get("brand") or "Sản phẩm").strip()
    prod = str(brand_brief.get("product_line") or "").strip()
    cat = str(brand_brief.get("category") or "sản phẩm chăm sóc").strip()
    usps = re.sub(r"[.,]+$", "", str(brand_brief.get("usps") or "").strip())
    cta = str(brand_brief.get("offer_cta") or "Đang có giá hời kèm miễn phí vận chuyển, mấy bà bấm giỏ hàng góc trái chốt liền nha.").strip()
    raw_brief = str(brand_brief.get("raw_brief") or "").strip()

    extra_lines = [ln.strip() for ln in raw_brief.splitlines() if ln.strip()]
    second_product = ""
    if len(extra_lines) >= 2:
        second_product = re.sub(r"^\[[^\]]+\]\s*", "", extra_lines[1]).strip(" .,-")
    first_product = re.sub(r"^\[[^\]]+\]\s*", "", extra_lines[0]).strip(" .,-") if extra_lines else f"{brand} {prod}".strip()

    return {
        "brand": brand,
        "product_line": prod,
        "category": cat,
        "usps": usps,
        "usps_short": _trim_phrase_words(usps, 16) if usps else f"{brand} {prod}".strip(),
        "cta": cta if cta.endswith((".", "!", "?")) else f"{cta}.",
        "first_product": first_product,
        "first_product_short": _trim_phrase_words(first_product, 12),
        "second_product": second_product,
        "second_product_short": _trim_phrase_words(second_product, 12) if second_product else "",
        "raw_brief": raw_brief,
    }


def ensure_script_meets_duration(
    script_display: str,
    script_text: str = "",
    target_duration_sec: float = 30.0,
    brand_brief: dict[str, Any] | None = None,
    option_index: int = 1,
) -> tuple[str, str, int]:
    """Ensure a script hits the target spoken syllable budget so TTS does not come out too short."""
    brief = brand_brief or load_brand_brief()
    info = _extract_brief_product_angles(brief)
    target_words, min_words, _ = compute_target_word_budget(target_duration_sec)
    max_words = max(min_words + 16, int(round(target_words * 1.18)))

    disp_clean = restore_display_text(script_display or script_text, brief)
    disp_clean = re.sub(r"[.,]+(?=[.,])", "", disp_clean)
    disp_sents = _split_sentences(disp_clean)
    if not disp_sents:
        disp_sents = [
            f"Bà nào đang gặp tình trạng liên quan tới {info['category']} thì xem hết clip này nha.",
            f"Đây là {info['brand']} {info['product_line']} với điểm mạnh {info['usps_short'] or 'rất tiện lợi mỗi ngày'}.",
            info["cta"],
        ]

    tts_full = convert_display_to_tts_script(" ".join(disp_sents), brief)
    if script_text and len(_split_sentences(script_text)) == len(disp_sents):
        candidate_tts = convert_display_to_tts_script(script_text, brief)
        if len(candidate_tts.split()) >= len(tts_full.split()) - 4:
            tts_full = candidate_tts

    cur_spoken = len(tts_full.split())
    if cur_spoken < min_words:
        combo_note = ""
        joined_low = " ".join(disp_sents).lower()
        sp_short = info["second_product_short"] or info["second_product"]
        if sp_short and not any(k in joined_low for k in ("480g", "72 giờ", "72h", "dầu gội") if k in sp_short.lower()):
            combo_note = (
                f"Để đạt hiệu quả tối ưu nhất, mấy bà nên kết hợp cùng {sp_short} dùng hằng ngày ở nhà nhé."
            )

        usp_snip = _trim_phrase_words(info["usps_short"], 12) or f"trải nghiệm thực tế với {info['product_line']}"
        pool_by_opt: dict[int, list[str]] = {
            1: [
                combo_note,
                f"Mình ưng nhất ở {info['brand']} {info['product_line']} là {usp_snip}, dùng hằng ngày rất gọn nhẹ.",
                f"Chỉ cần vài giây thao tác là cảm nhận rõ {usp_snip}, mang theo đi làm hay đi chơi đều tiện.",
                f"Thử dùng đều mỗi ngày mới thấy {info['category'] or 'dòng này'} hợp nhu cầu thực tế tới mức nào.",
            ],
            2: [
                combo_note,
                f"Điểm đáng chú ý của {info['brand']} {info['product_line']} nằm ở {usp_snip}.",
                f"Cảm giác sử dụng thực tế rất nhẹ nhàng và dễ chịu, phù hợp cho nhu cầu {info['category'] or 'hằng ngày'}.",
                "So với mức giá hiện tại trên giỏ hàng thì chất lượng thực tế mang lại rất đáng để trải nghiệm thử.",
            ],
            3: [
                combo_note,
                f"Thay vì mua lẻ từng món, chọn đúng {info['brand']} {info['product_line']} trong phiên hôm nay sẽ hời hơn hẳn.",
                f"Vừa có {usp_snip}, vừa được ưu đãi tốt ngay tại giỏ hàng góc trái màn hình.",
                "Bấm vào giỏ hàng góc trái xem chi tiết ưu đãi đang áp dụng hôm nay trước khi hết lượt nhé.",
            ],
        }
        candidates = [c for c in pool_by_opt.get(((option_index - 1) % 3) + 1, pool_by_opt[1]) if c]
        insert_pos = max(1, len(disp_sents) - 1)
        for add_sent in candidates:
            if len(tts_full.split()) >= target_words - 4:
                break
            if add_sent.lower()[:28] in " ".join(disp_sents).lower():
                continue
            disp_sents.insert(insert_pos, add_sent)
            insert_pos += 1
            tts_full = convert_display_to_tts_script(" ".join(disp_sents), brief)

    # Trim middle filler sentences when draft exceeds max_words (prevents 50s bloat on a 30s brief)
    while len(tts_full.split()) > max_words and len(disp_sents) > 4:
        mid_indices = list(range(2, len(disp_sents) - 1))
        if not mid_indices:
            mid_indices = list(range(1, len(disp_sents) - 1))
        drop_idx = max(mid_indices, key=lambda idx: len(disp_sents[idx].split()))
        disp_sents.pop(drop_idx)
        tts_full = convert_display_to_tts_script(" ".join(disp_sents), brief)

    final_disp = re.sub(r"[.,]+(?=[.,])", "", " ".join(disp_sents).strip())
    effective_banned = get_effective_banned_words(brief)
    final_disp = sanitize_banned_text(final_disp, banned_words=effective_banned)
    final_tts = convert_display_to_tts_script(final_disp, brief)
    final_tts = sanitize_banned_text(final_tts, banned_words=effective_banned)
    return final_disp, final_tts, len(final_tts.split())


def load_script_options() -> dict[str, Any]:
    if FILE_SCRIPT_OPTIONS.exists():
        try:
            loaded = json.loads(FILE_SCRIPT_OPTIONS.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict) and isinstance(loaded.get("options"), list):
                return loaded
        except Exception:
            pass
    return {}


def save_script_options(payload: dict[str, Any]) -> dict[str, Any]:
    FILE_SCRIPT_OPTIONS.parent.mkdir(parents=True, exist_ok=True)
    FILE_SCRIPT_OPTIONS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_auto_critic_report_md(
    target_duration_sec: float,
    options: list[dict[str, Any]],
    auto_fixes: list[str],
    preserve_clips: bool,
    clip_count: int,
) -> str:
    fix_lines = "\n".join(f"- ✅ {item}" for item in auto_fixes)
    opt_lines = "\n".join(
        f"- **{o.get('title', o.get('id'))}**: `{o.get('spoken_words', o.get('word_count', 0))} âm tiết` · Ước lượng `~{o.get('estimated_duration_sec', target_duration_sec)}s` · Hook: *{o.get('hook_badge', '')}*"
        for o in options
    )
    return (
        "# Báo Cáo AI Tiền Kỳ & Đề Xuất Đã Tự Động Áp Dụng (`04_workspace/ai_critic_report.md`)\n\n"
        f"> Đề xuất của AI Critic đã được kiểm tra và **tự động áp dụng ngay trước bước Tạo Giọng & Cắt Clip** (Mục tiêu `{target_duration_sec:.0f}s`).\n\n"
        "### 1. Các tối ưu AI Critic đã tự động áp dụng\n"
        f"{fix_lines}\n\n"
        "### 2. Bộ 3 Kịch bản đã cân chỉnh thời lượng\n"
        f"{opt_lines}\n\n"
        "### 3. Trạng thái bảo vệ danh sách Clips\n"
        f"- **Chế độ Clips**: {'🔒 Giữ nguyên ' + str(clip_count) + ' cảnh cắt hiện có (Không ghi đè)' if preserve_clips else '🔄 AI chọn lọc ' + str(clip_count) + ' cảnh mới từ video thô (tránh start=0.0s tĩnh)'}\n"
    )


def generate_three_script_options_fallback(
    brand_brief: dict[str, Any] | None = None,
    target_duration_sec: float | None = None,
    product_note: str = "",
    content_vibe: str = "learned_dna",
) -> dict[str, Any]:
    """Generate 3 complete, Critic-hardened Vietnamese script options matching target_duration_sec and content_vibe."""
    brief = brand_brief or load_brand_brief()
    target_dur = float(target_duration_sec or brief.get("target_duration_sec") or 30.0)
    info = _extract_brief_product_angles(brief)
    ch_ctx = load_channel_script_dna_context()
    pronoun = ch_ctx["pronoun"] or "mọi người"
    target_words, min_words, _ = compute_target_word_budget(target_dur)
    vibe_meta = get_content_vibe_meta(content_vibe)

    brand = info["brand"]
    prod = info["product_line"]
    cat = info["category"]
    clean_note = re.sub(r"\[Nhịp dựng[^\]]*\]", "", product_note or "").strip()
    usps = _trim_phrase_words(clean_note, 18) if clean_note else info["usps_short"]
    second_p = info["second_product_short"] or f"phiên bản {brand} {prod}".strip()
    cta = vibe_meta["cta_default"] if vibe_meta["is_vlog"] else info["cta"]
    prod_full = f"{brand} {prod}".strip()
    topic_label = clean_note[:40] if clean_note else (prod_full if prod_full and "chưa" not in prod_full.lower() else "CHUYẾN ĐI HÔM NAY")

    if vibe_meta["is_vlog"]:
        draft_specs = [
            {
                "id": "opt1",
                "title": f"Góc 1: Nhật ký Trải nghiệm ({vibe_meta['id'].replace('_', ' ').title()})",
                "angle": "Nhật ký Chill",
                "hook_badge": f"CUỐI TUẦN CHILL CÙNG {topic_label.upper()}"[:44],
                "sentences": [
                    f"Cuối tuần này tụi mình quyết định tạm gác lại bộn bề để ra ngoài hít thở không khí trong lành.",
                    f"Điểm thú vị nhất của chuyến đi là {usps}, cảm giác vừa bước tới đã thấy nhẹ cả người.",
                    "Không gian thoáng đãng, ánh nắng nhẹ và tiếng gió làm mọi khung hình trở nên cực kỳ thư giãn.",
                    "Chỉ cần chuẩn bị vài món đơn giản là đã có nguyên một buổi chiều thật đáng nhớ bên nhau.",
                    cta,
                ],
            },
            {
                "id": "opt2",
                "title": "Góc 2: Kể chuyện Góc nhìn Đời sống (Storytelling)",
                "angle": "Storytelling",
                "hook_badge": f"MỘT NGÀY ĐÁNG NHỚ · {topic_label.upper()}"[:44],
                "sentences": [
                    f"Có những ngày mình chỉ muốn xách balo lên và đi đâu đó thật yên bình để nạp lại năng lượng.",
                    f"Khoảnh khắc ấn tượng nhất chính là {usps}, nhìn ngoài đời còn đẹp hơn trong video nhiều.",
                    "Nhịp sống chậm lại một chút giúp mình để ý được nhiều chi tiết nhỏ mà bình thường hay bỏ lỡ.",
                    "Đây chắc chắn là một trong những kỷ niệm nhẹ nhàng và dễ chịu nhất trong tháng này.",
                    cta,
                ],
            },
            {
                "id": "opt3",
                "title": "Góc 3: Chia sẻ Tips & Góc Quay Đẹp (Style Mạng)",
                "angle": "Chia sẻ Tips",
                "hook_badge": f"GÓC CHILL XỊN · {topic_label.upper()}"[:44],
                "sentences": [
                    f"Ai đang tìm một chỗ vừa đẹp vừa thoải mái để đổi gió thì xem hết video này nha.",
                    f"Điểm cộng lớn nhất ở đây là {usps}, lên hình góc nào cũng rất tự nhiên và có chiều sâu.",
                    "Đi tầm buổi sáng hoặc xế chiều ánh sáng dịu sẽ quay được nhiều thước phim cực kỳ mượt.",
                    "Vừa thư giãn vừa có thêm nhiều khoảnh khắc xịn để lưu giữ làm kỷ niệm.",
                    cta,
                ],
            },
        ]
    else:
        draft_specs = [
        {
            "id": "opt1",
            "title": "Góc 1: Đánh vào Nỗi đau & Giải pháp tức thì",
            "angle": "Nỗi đau",
            "hook_badge": f"CHÂN ÁI {prod_full.upper()}"[:44],
            "sentences": [
                f"{pronoun.capitalize()} ơi, đang tìm {cat} tiện lợi thì dừng lại ba giây xem ngay em {prod_full} này nha.",
                f"Điểm sáng là {usps}, dùng nhanh gọn trong vài giây mà không tốn nhiều công sức.",
                "Thiết kế nhỏ gọn dễ bỏ túi, mang đi làm hay đi chơi đều rất tiện.",
                "Dùng xong cảm giác dễ chịu, tự tin hẳn khi ra ngoài gặp gỡ bạn bè.",
                f"Kết hợp thêm cùng {second_p} nữa là hiệu quả bền lâu hơn hẳn.",
                cta,
            ],
        },
        {
            "id": "opt2",
            "title": "Góc 2: Review Thành phần & Trải nghiệm thực tế",
            "angle": "Review Trải nghiệm",
            "hook_badge": f"REVIEW THẬT {prod_full.upper()}"[:44],
            "sentences": [
                f"Hôm nay mình review nhanh em {prod_full} đang được nhiều người tìm mua nha.",
                f"Điểm ăn tiền đầu tiên là {usps}, mang lại cảm giác thoải mái ngay lần đầu dùng.",
                "Đóng gói chỉn chu chắc tay, cực kỳ gọn để mang theo trong túi mỗi ngày.",
                "Dùng đều mỗi ngày giúp mình nhẹ nhàng và tự tin giao tiếp suốt cả ngày.",
                cta,
            ],
        },
        {
            "id": "opt3",
            "title": "Góc 3: Combo Chăm sóc Toàn diện & Săn Deal",
            "angle": "Combo & Săn Deal",
            "hook_badge": f"DEAL HỜI {brand.upper()} ĐANG SALE"[:44],
            "sentences": [
                f"Muốn chọn {cat} vừa chất lượng vừa tiết kiệm thì đừng bỏ qua em {prod_full} hôm nay nha.",
                f"Ưu điểm lớn nhất là {usps}, bỏ túi mang theo dùng mọi lúc mọi nơi.",
                f"Chọn kèm {second_p} trong hôm nay sẽ có mức giá hời hơn mua lẻ rất nhiều.",
                "Hàng chính hãng đóng gói cẩn thận, kèm miễn phí vận chuyển đang còn giới hạn.",
                cta,
            ],
        },
    ]

    options: list[dict[str, Any]] = []
    for i, spec in enumerate(draft_specs, start=1):
        raw_disp = " ".join(spec["sentences"])
        final_disp, final_tts, spoken_cnt = ensure_script_meets_duration(
            raw_disp,
            "",
            target_duration_sec=target_dur,
            brand_brief=brief,
            option_index=i,
        )
        est_sec = round(spoken_cnt / 3.85, 1)
        options.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "angle": spec["angle"],
                "hook_badge": spec["hook_badge"][:48],
                "script_display": final_disp,
                "script_text": final_tts,
                "spoken_words": spoken_cnt,
                "sentence_count": len(_split_sentences(final_disp)),
                "estimated_duration_sec": est_sec,
            }
        )

    auto_fixes = [
        f"Đã cân chỉnh định mức độ dài lên ~{target_words} âm tiết/từ (tối thiểu {min_words} từ, 7-8 Beat) để khớp chuẩn {target_dur:.0f}s thay vì bị hụt 19s.",
        f"Đã tích hợp đầy đủ USP & sản phẩm trong Brief Nhãn hàng ({brand} · {prod}).",
        "Đã tự động chuyển đổi tên tiếng Anh, % và dung tích (ml/g) sang phiên âm tiếng Việt sạch cho F5-TTS và giữ chữ đẹp có dấu cho Phụ đề.",
        "Đã lọc loại bỏ từ thừa/hallucination và đồng bộ sẵn Hook Badge không vượt quá 32-45 ký tự.",
    ]

    return {
        "target_duration_sec": target_dur,
        "recommended_id": "opt1",
        "auto_critic_applied": True,
        "auto_critic_fixes": auto_fixes,
        "options": options,
    }


_LEGACY_SHAMPOO_PILL_TERMS = (
    "chân tóc",
    "xả lại",
    "sạch gàu",
    "dịu ngứa",
    "dầu gội",
    "vòi xịt",
    "niacinamide",
    "menthol",
)


def _brief_mentions_haircare(brief: dict[str, Any]) -> bool:
    combined = " ".join(
        str(brief.get(k) or "") for k in ("brand", "product_line", "category", "usps", "raw_brief")
    ).lower()
    return any(
        kw in combined
        for kw in ("head", "shoulder", "gàu", "dầu gội", "da đầu", "chân tóc", "niacinamide", "menthol")
    )


def _is_legacy_shampoo_pill(pill: str, brief: dict[str, Any]) -> bool:
    low = (pill or "").strip().lower()
    if not low or _brief_mentions_haircare(brief):
        return False
    return any(term in low for term in _LEGACY_SHAMPOO_PILL_TERMS)


def _extract_brief_usp_pills(brief: dict[str, Any]) -> list[str]:
    raw_usps = str(brief.get("usps") or "").strip()
    prod = str(brief.get("product_line") or "").strip()
    cat = str(brief.get("category") or "").strip()
    offer = str(brief.get("offer_cta") or "").strip()
    brand = str(brief.get("brand") or "").strip()

    cleaned_usps = re.sub(r"^\s*\[|\]\s*$", "", raw_usps)
    raw_chunks = re.split(r"[,;\n\|•]+", cleaned_usps) if cleaned_usps else []

    pills: list[str] = []
    icons = ["✨", "🌿", "⚡", "💧", "🎯", "🔥"]
    seen_low: set[str] = set()

    def _add_pill(icon: str, phrase: str) -> None:
        clean = re.sub(r"^[\'\"\-\*\s]+|[\'\"\s\.!]+$", "", phrase or "").strip()
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) < 3:
            return
        words = clean.split()
        lead_fillers = {"và", "với", "hợp", "đến", "lên", "tới", "giữa", "từ", "của", "cho", "bằng"}
        if len(words) > 4:
            num_idx = next((i for i, w in enumerate(words) if re.search(r"\d", w)), -1)
            if num_idx >= 0:
                start_i = max(0, num_idx - 1) if (num_idx > 0 and words[num_idx - 1].lower() not in lead_fillers) else num_idx
                clean = " ".join(words[start_i : start_i + 4])
            else:
                clean = " ".join(words[:4])
        while True:
            parts = clean.split()
            if len(parts) > 2 and parts[0].lower() in lead_fillers:
                clean = " ".join(parts[1:])
            else:
                break
        if len(clean) > 26:
            clean = clean[:26].rsplit(" ", 1)[0].strip() or clean[:26]
        if clean:
            clean = clean[0].upper() + clean[1:]
        low = clean.lower()
        if low in seen_low or len(clean) < 3:
            return
        seen_low.add(low)
        pills.append(f"{icon} {clean}")

    if prod and prod.lower() != "chưa thiết lập":
        _add_pill("🔥", prod)

    for chunk in raw_chunks:
        part = re.sub(r"^[\'\"\-\*\s]+|[\'\"\s\.!]+$", "", chunk).strip()
        if not part:
            continue
        if ":" in part:
            right = part.split(":", 1)[1].strip()
            part = right if len(right) >= 4 else part
        part = re.sub(
            r"^(?:công thức(?:\s+kết hợp độc đáo)?(?:\s+giữa)?|tác động kép|điểm mạnh|ưu điểm|phiên bản)\s+",
            "",
            part,
            flags=re.I,
        ).strip()
        icon = icons[len(pills) % len(icons)]
        _add_pill(icon, part)
        if len(pills) >= 6:
            break

    if cat and cat.lower() != "chưa thiết lập":
        _add_pill("🏷️", cat.capitalize())

    if offer:
        low_off = offer.lower()
        if "freeship" in low_off:
            pills.append("🛒 Freeship Giỏ Hàng")
        elif any(k in low_off for k in ("quà", "hời", "giảm", "voucher", "deal", "giá")):
            pills.append("🎁 Deal Hời Hôm Nay")
        else:
            _add_pill("🛒", offer)

    if not pills:
        pills = [
            f"🔥 {brand[:22]}" if brand and brand.lower() != "chưa thiết lập" else "🔥 Chuẩn TikTok Shop",
            "✨ Điểm Nổi Bật",
            "💯 Review Thực Tế",
            "🛒 Giỏ Hàng Góc Trái",
        ]
    return pills


def _extract_feature_pill_from_text(text: str, brief: dict[str, Any], idx: int) -> str:
    low = (text or "").lower()
    pool = _extract_brief_usp_pills(brief)
    if "giỏ hàng" in low or "freeship" in low or "chốt" in low or "deal" in low or "săn" in low:
        for cand in pool:
            if any(k in cand.lower() for k in ("giỏ hàng", "freeship", "deal", "quà")):
                return cand
        return "🛒 Giỏ Hàng Góc Trái"
    if low:
        best_cand = ""
        best_score = 0
        text_tokens = {w for w in re.findall(r"[\wÀ-ỹà-ỹ0-9]+", low) if len(w) >= 2}
        for cand in pool:
            cand_tokens = {w for w in re.findall(r"[\wÀ-ỹà-ỹ0-9]+", cand.lower()) if len(w) >= 2}
            score = len(text_tokens & cand_tokens)
            if score > best_score:
                best_score = score
                best_cand = cand
        if best_cand and best_score > 0:
            return best_cand
    return pool[idx % len(pool)]


def _assign_camera_motion(idx: int, total_clips: int, spoken_text: str) -> dict[str, Any]:
    """Assign varied Zoom-in, Zoom-out, Punch-in, In-Out, or Ken Burns motion per clip."""
    if idx == 0:
        return {"zoom_mode": "punch_in", "zoom_from": 1.0, "zoom_to": 1.20, "pan_x": 0, "pan_y": 0, "transition_type": "hard"}
    if idx == 1:
        return {"zoom_mode": "zoom_out", "zoom_from": 1.20, "zoom_to": 1.02, "pan_x": 0, "pan_y": 0, "transition_type": "flash"}
    if idx == total_clips - 1:
        return {"zoom_mode": "punch_in", "zoom_from": 1.0, "zoom_to": 1.22, "pan_x": 0, "pan_y": 0, "transition_type": "zoom"}
    slot = idx % 4
    if slot == 2:
        return {
            "zoom_mode": "ken_burns",
            "zoom_from": 1.04,
            "zoom_to": 1.17,
            "pan_x": -18 if idx % 2 == 0 else 18,
            "pan_y": -10,
            "transition_type": "slide",
        }
    if slot == 3:
        return {"zoom_mode": "in_out", "zoom_from": 1.02, "zoom_to": 1.18, "pan_x": 0, "pan_y": 0, "transition_type": "zoom"}
    if slot == 0:
        return {"zoom_mode": "zoom_out", "zoom_from": 1.18, "zoom_to": 1.02, "pan_x": 10, "pan_y": 0, "transition_type": "flash"}
    return {"zoom_mode": "push_in", "zoom_from": 1.0, "zoom_to": 1.18, "pan_x": 12, "pan_y": 0, "transition_type": "flash"}


def _sanitize_ai_svg(raw_svg: str) -> str:
    """Allow only safe decorative SVG markup (no scripts, foreignObject, or event handlers)."""
    txt = (raw_svg or "").strip()
    if not txt or "<svg" not in txt.lower() or "</svg>" not in txt.lower():
        return ""
    m = re.search(r"(<svg\b[^>]*>.*?</svg>)", txt, flags=re.I | re.S)
    if not m:
        return ""
    svg = m.group(1)
    if re.search(r"<\s*(script|foreignObject|iframe|object|embed|style)\b", svg, flags=re.I):
        return ""
    svg = re.sub(r"\bon[a-z]+\s*=\s*(['\"]).*?\1", "", svg, flags=re.I | re.S)
    svg = re.sub(r"javascript\s*:", "", svg, flags=re.I)
    if len(svg) > 8500:
        return ""
    return svg


def _infer_motif_from_brief(brief: dict[str, Any], rng: Any) -> str:
    combined = " ".join(
        str(brief.get(k) or "") for k in ("brand", "product_line", "category", "usps")
    ).lower()
    if any(k in combined for k in ("mát lạnh", "menthol", "băng", "nước", "serum", "dầu gội", "sữa rửa")):
        return rng.choice(["bubbles_ice", "wave_ribbon"])
    if any(k in combined for k in ("thảo dược", "thiên nhiên", "lá", "trà", "lợi khuẩn", "thơm miệng", "kissport")):
        return rng.choice(["botanical_leaf", "sparkle_burst"])
    if any(k in combined for k in ("công nghệ", "laptop", "chuột", "điện", "máy", "led")):
        return rng.choice(["cyber_grid", "geometric_orbit"])
    return rng.choice(["bubbles_ice", "botanical_leaf", "cyber_grid", "sparkle_burst", "wave_ribbon", "geometric_orbit"])


def _build_default_sticker_events(
    brief: dict[str, Any],
    pop_palette: list[str],
    rng: Any,
    sticker_density: str = "normal",
) -> list[dict[str, Any]]:
    """Build expressive animated Lottie stickers + Messenger bubbles scaled by sticker_density."""
    if sticker_density == "off":
        return []
    dur = max(12.0, float(brief.get("target_duration_sec") or 25.0))
    combined = " ".join(
        str(brief.get(k) or "") for k in ("brand", "product_line", "category", "usps", "offer_cta")
    ).lower()

    pool: list[tuple[str, str]] = []
    if any(k in combined for k in ("mát", "menthol", "băng", "36", "thơm")):
        pool.extend([("❄️", "MÁT LẠNH!"), ("🍃", "THƠM MÁT"), ("✨", "SẢNG KHOÁI")])
    if any(k in combined for k in ("gàu", "tóc", "xịt", "da đầu", "5in1", "5 trong 1")):
        pool.extend([("🧴", "5IN1 TIỆN LỢI"), ("🛡️", "SẠCH GÀU"), ("💧", "THẨM THẤU")])
    if any(k in combined for k in ("trái cây", "hương", "vị", "kẹo", "ngậm", "lợi khuẩn")):
        pool.extend([("🍓", "4 HƯƠNG VỊ"), ("🌿", "12 THẢO DƯỢC"), ("😋", "KHÔNG ĐƯỜNG")])
    if any(k in combined for k in ("công nghệ", "chuột", "laptop", "led", "pin")):
        pool.extend([("⚡", "SIÊU MƯỢT"), ("🔋", "PIN TRÂU"), ("🎯", "CHUẨN PRO")])
    general_pool: list[tuple[str, str]] = [
        ("🔥", "SIÊU HOT!"),
        ("✨", "REVIEW THẬT"),
        ("💎", "CHẤT LƯỢNG"),
        ("🎁", "QUÀ TẶNG"),
        ("🛒", "DEAL HỜI!"),
        ("🤩", "QUÁ ĐÃ!"),
        ("🥳", "SĂN NGAY!"),
        ("💖", "CỰC ƯNG!"),
        ("⚡", "SIÊU NHANH"),
        ("🌟", "ĐÁNG THỬ!"),
        ("🎉", "GIÁ TỐT!"),
        ("💯", "CHUẨN XỊN"),
        ("👑", "BEST CHOICE"),
        ("🛍️", "CHỐT ĐƠN!"),
        ("🚀", "GIAO NHANH"),
        ("🍀", "TIẾT KIỆM"),
        ("👍", "RẤT ĐÁNG!"),
        ("😍", "MÊ MẨN!"),
    ]
    rng.shuffle(general_pool)
    pool.extend(general_pool)
    # Deduplicate while preserving order
    dedup: list[tuple[str, str]] = []
    seen_lbl: set[str] = set()
    for em, lb in pool:
        if lb not in seen_lbl:
            seen_lbl.add(lb)
            dedup.append((em, lb))

    # Safe edge/corner slots avoiding Hook badge & central subtitle band (y 0.66..0.82)
    edge_slots = [
        (0.06, 0.42, -6),
        (0.70, 0.44, 6),
        (0.05, 0.50, -5),
        (0.68, 0.54, 5),
        (0.06, 0.58, -6),
        (0.66, 0.38, 7),
        (0.08, 0.36, -4),
    ]
    events: list[dict[str, Any]] = []
    n_events = 7 if sticker_density == "rich" else 4
    step = max(2.2, (dur - 3.0) / float(n_events))
    for i in range(n_events):
        em, lb = dedup[i % len(dedup)]
        xp, yp, rot = edge_slots[i % len(edge_slots)]
        asset_rel = resolve_animated_sticker_asset(em, i + rng.randint(0, 299))
        style_kind = "animated_sticker" if (asset_rel and (i % 2 == 0 or sticker_density == "rich")) else "messenger_bubble"
        events.append(
            {
                "emoji": "",
                "label": strip_slop_emojis(lb),
                "stickerAsset": asset_rel,
                "styleKind": style_kind,
                "start": round(1.8 + i * step, 2),
                "duration": round(min(3.4, max(2.2, step * 0.8)), 2),
                "xPct": xp,
                "yPct": yp,
                "bg": pop_palette[i % len(pop_palette)],
                "rotateDeg": rot + rng.randint(-2, 2),
            }
        )
    if sticker_density == "rich":
        cta_asset = resolve_animated_sticker_asset("🛒", 0) or resolve_animated_sticker_asset("🔥", 0)
        if cta_asset:
            events.append(
                {
                    "emoji": "",
                    "label": "BẤM GIỎ HÀNG!",
                    "stickerAsset": cta_asset,
                    "styleKind": "animated_sticker",
                    "start": round(max(3.5, dur - 3.8), 2),
                    "duration": 3.5,
                    "xPct": 0.68,
                    "yPct": 0.78,
                    "bg": pop_palette[0],
                    "rotateDeg": 5,
                }
            )
    return events


def generate_ai_wildcard_style_spec(
    brand_brief: dict[str, Any] | None = None,
    gemini_api_key: str = "",
    sticker_density: str = "normal",
    icon_density: str = "balanced",
    exclude_archetypes: list[str] | None = None,
    exclude_palettes: list[str] | None = None,
    exclude_hook_layouts: list[str] | None = None,
    exclude_sub_variants: list[str] | None = None,
    content_vibe: str = "learned_dna",
    aspect_ratio: str = "9:16",
) -> dict[str, Any]:
    """Generate a bold, out-of-the-box WildcardStyleSpec with structural layout archetypes & AI-drawn SVG motifs."""
    import random
    import urllib.request

    brief = brand_brief or load_brand_brief()
    rng = random.Random()

    palettes = [
        ("linear-gradient(135deg, #0F172A, #1E1B4B, #312E81)", "#38BDF8", "#FFFFFF", "#38BDF8"),
        ("linear-gradient(135deg, #18181B, #3F3F46, #09090B)", "#FACC15", "#FEF9C3", "#FACC15"),
        ("linear-gradient(135deg, #064E3B, #022C22, #0F172A)", "#34D399", "#ECFDF5", "#6EE7B7"),
        ("linear-gradient(135deg, #4C0519, #881337, #1F2937)", "#FB7185", "#FFF1F2", "#FDA4AF"),
        ("linear-gradient(135deg, #1E293B, #0F766E, #090D16)", "#2DD4BF", "#F0FDFA", "#5EEAD4"),
        ("linear-gradient(135deg, #2E1065, #581C87, #090D16)", "#E879F9", "#FAF5FF", "#F0ABFC"),
        ("linear-gradient(135deg, #431407, #7C2D12, #18181B)", "#FB923C", "#FFF7ED", "#FDBA74"),
    ]
    ex_pal = set(exclude_palettes or [])
    avail_palettes = [p for p in palettes if p[0] not in ex_pal] or palettes
    bg_grad, accent, text_col, border_col = rng.choice(avail_palettes)
    archetypes = [
        "polaroid_scrapbook",
        "bento_split",
        "kinetic_poster",
        "tech_hud",
        "editorial_zine",
        "cinema_spotlight",
    ]
    ex_arch = set(exclude_archetypes or [])
    avail_archetypes = [a for a in archetypes if a not in ex_arch] or archetypes
    chosen_arch = rng.choice(avail_archetypes)
    if chosen_arch == "polaroid_scrapbook":
        f_scale, f_rad, f_tilt, lbox = 0.84, 18, round(rng.choice([-2.6, -1.9, 1.9, 2.6]), 2), 0
    elif chosen_arch == "bento_split":
        f_scale, f_rad, f_tilt, lbox = 0.88, 26, 0.0, 0
    elif chosen_arch == "kinetic_poster":
        f_scale, f_rad, f_tilt, lbox = 0.85, 22, round(rng.uniform(-1.8, 1.8), 2), 0
    elif chosen_arch == "tech_hud":
        f_scale, f_rad, f_tilt, lbox = 0.90, 14, 0.0, 0
    elif chosen_arch == "editorial_zine":
        f_scale, f_rad, f_tilt, lbox = 0.86, 8, 0.0, 0
    else:
        f_scale, f_rad, f_tilt, lbox = 0.96, 0, 0.0, rng.choice([140, 175])

    hook_layouts = ["top_left_editorial", "center_bold", "quote_5star", "breaking_ticker", "glass_floating"]
    sub_variants = ["clean_stroke", "glass_pill", "accent_band"]
    vlog_mode = is_vlog_vibe(content_vibe)
    if vlog_mode:
        cta_labels = [
            "✨ Lưu Lại Cuối Tuần Đi Chill",
            "📌 Follow Xem Thêm Hành Trình",
            "🌿 Kỷ Niệm Đáng Nhớ Hôm Nay",
            "💬 Comment Góc Bạn Thích Nhất",
        ]
    else:
        cta_labels = [
            "🛒 Chốt Deal Ngay Góc Trái",
            "⚡ Săn Giá Hời Hôm Nay",
            "🔥 Giỏ Hàng Đang Trợ Giá",
            "🎁 Bấm Giỏ Hàng Xem Chi Tiết",
        ]
    brand_up = str(brief.get("brand") or ("VLOG DIARY" if vlog_mode else "TIKTOK SHOP")).strip().upper()
    prod_str = str(brief.get("product_line") or brief.get("category") or ("HÀNH TRÌNH MỚI" if vlog_mode else "SIÊU DEAL HOT")).strip()
    effective_banned = get_effective_banned_words(brief)
    raw_ticker = (
        f"✨ {brand_up} · {prod_str.upper()} · NHẬT KÝ TRẢI NGHIỆM"
        if vlog_mode
        else f"🔥 {brand_up} · {prod_str.upper()} · ƯU ĐÃI GIỎ HÀNG GÓC TRÁI"
    )
    ticker_default = sanitize_banned_text(
        strip_slop_emojis(raw_ticker) if icon_density == "minimal" else raw_ticker,
        banned_words=effective_banned,
    )

    pop_palettes = [
        ["#FF4D6D", "#FFE500", "#00F5D4", "#38BDF8", "#A855F7"],
        ["#F97316", "#FACC15", "#10B981", "#06B6D4", "#EC4899"],
        ["#E11D48", "#FB923C", "#FDE047", "#34D399", "#60A5FA"],
        ["#8B5CF6", "#EC4899", "#F59E0B", "#2DD4BF", "#3B82F6"],
    ]
    pop_palette = rng.choice(pop_palettes)
    sticker_events = _build_default_sticker_events(brief, pop_palette, rng, sticker_density=sticker_density)
    for st in sticker_events:
        if vlog_mode and any(k in str(st.get("label") or "").lower() for k in ("giỏ", "deal", "sale", "freeship")):
            st["label"] = "CHILL VIBE"
        st["label"] = sanitize_banned_text(st["label"], banned_words=effective_banned) or ("CHILL" if vlog_mode else "DEAL HOT")
        ensure_twemoji_svg(st.get("emoji") or "")

    spec: dict[str, Any] = {
        "styleName": f"AI Wildcard · {chosen_arch.replace('_', ' ').title()} #{rng.randint(100, 999)}",
        "layoutArchetype": chosen_arch,
        "motifKind": _infer_motif_from_brief(brief, rng),
        "tickerText": ticker_default[:110],
        "customSvgOverlay": "",
        "popPalette": pop_palette,
        "stickerEvents": sticker_events,
        "frameScale": f_scale,
        "frameRadius": f_rad,
        "frameTiltDeg": f_tilt,
        "frameBorderColor": border_col,
        "letterboxPx": (0 if aspect_ratio == "16:9" else lbox),
        "bgGradient": bg_grad,
        "accentColor": accent,
        "textColor": text_col,
        "hookLayout": rng.choice([h for h in hook_layouts if h not in set(exclude_hook_layouts or [])] or hook_layouts),
        "subtitleVariant": rng.choice([s for s in sub_variants if s not in set(exclude_sub_variants or [])] or sub_variants),
        "subtitleY": (round(rng.uniform(0.80, 0.86), 2) if aspect_ratio == "16:9" else round(rng.uniform(0.69, 0.77), 2)),
        "showRatingBadge": False,
        "ctaLabel": sanitize_banned_text(rng.choice(cta_labels), banned_words=effective_banned) or ("✨ Lưu Lại Xem Sau" if vlog_mode else "🛒 Giỏ Hàng Góc Trái"),
    }

    api_key = str(gemini_api_key or "").strip()
    if api_key:
        try:
            prompt = (
                f"Design a bold, creative, out-of-the-box TikTok 1080x1920 vertical video visual style JSON for product: "
                f"{brief.get('brand')} {brief.get('product_line')} ({brief.get('category')}). "
                "Return ONLY valid JSON with keys: styleName (short string), "
                "layoutArchetype (one of polaroid_scrapbook,bento_split,kinetic_poster,tech_hud,editorial_zine,cinema_spotlight), "
                "motifKind (one of bubbles_ice,botanical_leaf,cyber_grid,sparkle_burst,wave_ribbon,geometric_orbit), "
                "tickerText (short uppercase Vietnamese promo ticker string <= 95 chars), "
                "frameScale (0.83..0.98), frameRadius (0..32), frameTiltDeg (-2.8..2.8), frameBorderColor (hex), letterboxPx (0 or 140..185), "
                "bgGradient (CSS linear-gradient), accentColor (bright hex), textColor (light hex), "
                "hookLayout (one of top_left_editorial,center_bold,quote_5star,breaking_ticker,glass_floating), "
                "subtitleVariant (one of clean_stroke,glass_pill,accent_band), subtitleY (0.68..0.77), "
                "showRatingBadge (boolean), ctaLabel (short Vietnamese CTA with emoji), "
                "popPalette (array of 5 vibrant contrasting hex colors like [\"#FF4D6D\",\"#FFE500\",\"#00F5D4\",\"#38BDF8\",\"#A855F7\"]), "
                "stickerEvents (array of 6 objects {emoji, label (short 1-3 Vietnamese uppercase words), start (sec), duration (2.0..3.2), xPct (0.05..0.72), yPct (0.24..0.60), bg (hex from popPalette), rotateDeg (-10..10)}), "
                "customSvgOverlay (a rich, colorful, artistic SVG `<svg viewBox=\"0 0 1080 1920\" width=\"1080\" height=\"1920\">...</svg>` with 8-14 multi-color vector elements using 3-4 colors from popPalette: radial sunburst rays, diagonal ribbons, starbursts, product-themed doodles/botanicals/sparkles around corners and edges with opacity 0.45..0.78 while keeping the center clear for video & subtitles, NO script tags)."
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            body = json.dumps(
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 1.15, "responseMimeType": "application/json"},
                }
            ).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=14) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                raw_txt = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_txt)
                if isinstance(parsed, dict) and parsed.get("accentColor"):
                    arch_val = str(parsed.get("layoutArchetype") or chosen_arch)
                    if arch_val not in archetypes or (arch_val in ex_arch and avail_archetypes):
                        arch_val = chosen_arch
                    hook_val = str(parsed.get("hookLayout") or spec["hookLayout"])
                    if hook_val not in hook_layouts or (hook_val in set(exclude_hook_layouts or []) and len(hook_layouts) > len(exclude_hook_layouts or [])):
                        hook_val = spec["hookLayout"]
                    sub_val = str(parsed.get("subtitleVariant") or spec["subtitleVariant"])
                    if sub_val not in sub_variants or (sub_val in set(exclude_sub_variants or []) and len(sub_variants) > len(exclude_sub_variants or [])):
                        sub_val = spec["subtitleVariant"]
                    motif_val = str(parsed.get("motifKind") or spec["motifKind"])
                    if motif_val not in ("bubbles_ice", "botanical_leaf", "cyber_grid", "sparkle_burst", "wave_ribbon", "geometric_orbit"):
                        motif_val = spec["motifKind"]
                    raw_pal = parsed.get("popPalette")
                    if isinstance(raw_pal, list) and len(raw_pal) >= 3:
                        clean_pal = [str(c).strip() for c in raw_pal[:6] if str(c).strip().startswith("#")]
                        if len(clean_pal) >= 3:
                            spec["popPalette"] = clean_pal
                    raw_stickers = parsed.get("stickerEvents")
                    if isinstance(raw_stickers, list) and len(raw_stickers) >= 3:
                        clean_st: list[dict[str, Any]] = []
                        pal_ref = spec["popPalette"]
                        for si, st in enumerate(raw_stickers[:8]):
                            if not isinstance(st, dict) or not st.get("label"):
                                continue
                            yp = float(st.get("yPct") or 0.32)
                            if 0.64 <= yp <= 0.82:
                                yp = 0.56
                            em_raw = str(st.get("emoji") or "✨")[:4]
                            asset_rel = resolve_animated_sticker_asset(em_raw, si)
                            clean_lbl = strip_slop_emojis(str(st.get("label") or "HOT DEAL"))[:18].upper() or "HOT DEAL"
                            st_start = max(1.8, float(st.get("start") or (1.8 + si * 2.8)))
                            if st_start < 4.0 and yp < 0.40:
                                yp = 0.42
                            clean_st.append(
                                {
                                    "emoji": "",
                                    "label": clean_lbl,
                                    "stickerAsset": asset_rel,
                                    "styleKind": "animated_sticker" if (asset_rel and si % 2 == 0) else "messenger_bubble",
                                    "start": st_start,
                                    "duration": max(1.6, min(3.8, float(st.get("duration") or 2.5))),
                                    "xPct": max(0.04, min(0.74, float(st.get("xPct") or (0.06 if si % 2 == 0 else 0.68)))),
                                    "yPct": max(0.22, min(0.86, yp)),
                                    "bg": str(st.get("bg") or pal_ref[si % len(pal_ref)]),
                                    "rotateDeg": max(-14, min(14, int(float(st.get("rotateDeg") or (-7 if si % 2 == 0 else 7))))),
                                }
                            )
                        if clean_st:
                            spec["stickerEvents"] = clean_st
                    spec.update(
                        {
                            "styleName": str(parsed.get("styleName") or spec["styleName"])[:48],
                            "layoutArchetype": arch_val,
                            "motifKind": motif_val,
                            "tickerText": str(parsed.get("tickerText") or spec["tickerText"])[:110],
                            "customSvgOverlay": _sanitize_ai_svg(str(parsed.get("customSvgOverlay") or "")),
                            "frameScale": max(0.83, min(1.0, float(parsed.get("frameScale") or spec["frameScale"]))),
                            "frameRadius": max(0, min(36, int(parsed.get("frameRadius") or 0))),
                            "frameTiltDeg": max(-3.0, min(3.0, float(parsed.get("frameTiltDeg") or 0.0))),
                            "frameBorderColor": str(parsed.get("frameBorderColor") or spec["frameBorderColor"]),
                            "letterboxPx": max(0, min(200, int(parsed.get("letterboxPx") or 0))),
                            "bgGradient": str(parsed.get("bgGradient") or spec["bgGradient"]),
                            "accentColor": str(parsed.get("accentColor") or spec["accentColor"]),
                            "textColor": str(parsed.get("textColor") or spec["textColor"]),
                            "hookLayout": hook_val,
                            "subtitleVariant": sub_val,
                            "subtitleY": max(0.65, min(0.80, float(parsed.get("subtitleY") or spec["subtitleY"]))),
                            "showRatingBadge": bool(parsed.get("showRatingBadge", spec["showRatingBadge"])),
                            "ctaLabel": str(parsed.get("ctaLabel") or spec["ctaLabel"])[:36],
                        }
                    )
        except Exception:
            pass
    return spec


def generate_random_batch_mix_profiles(
    count: int = 3,
    base_engine: str = "remotion_classic",
    mix_engines: bool = False,
) -> list[dict[str, Any]]:
    """Generate `count` truly randomized, mutually distinct mix profiles for multi-channel A/B export."""
    import random

    rng = random.Random()
    themes = ["fresh_mint", "floral_rose", "flash_gold", "luxury_dark", "ribbon_sticker"]
    inno_presets = ["kinetic_pop", "magazine_split", "neon_pulse"]
    layouts = ["full", "card_blur", "top_banner"]
    colors = ["natural", "warm_film", "cool_vivid"]
    sub_colors = ["#FFE500", "#00F2FE", "#FB7185", "#34D399"]
    badge_styles = ["floral_plus_callouts", "multicolor_pill", "floral_badge"]
    font_headings = [
        "Baloo 2",
        "Montserrat Black",
        "Be Vietnam Pro",
        "Anton",
        "Oswald",
        "Nunito",
        "Bricolage Grotesque",
        "Paytone One",
    ]
    overlay_effects = [
        "light_leak_warm.mp4",
        "light_leak_prism.mp4",
        "light_leak_cool.mp4",
        "bokeh_sparkle.mp4",
        "film_grain_soft.mp4",
        "paper_texture_warm.png",
        "grid_hud_overlay.png",
    ]
    creative_modes = ["breakthrough_ai", "flash_checklist", "classic_dna"]
    order_pool = ["original", "reverse_hook", "rotate_2", "rotate_4_swap", "shuffle_mid"]

    bgm_dir = ROOT_DIR / "06_assets_audio" / "bgm"
    bgm_files = [p.name for p in sorted(bgm_dir.glob("*.wav"))] if bgm_dir.exists() else []
    if not bgm_files:
        bgm_files = ["bgm_upbeat_tiktok.wav", "bgm_chill_lofi.wav", "bgm_flash_sale.wav"]

    rng.shuffle(themes)
    rng.shuffle(inno_presets)
    rng.shuffle(layouts)
    rng.shuffle(colors)
    rng.shuffle(sub_colors)
    rng.shuffle(badge_styles)
    rng.shuffle(font_headings)
    rng.shuffle(overlay_effects)
    rng.shuffle(creative_modes)
    rng.shuffle(bgm_files)
    non_orig_orders = [m for m in order_pool if m != "original"]
    rng.shuffle(non_orig_orders)
    engines = ["remotion_classic", "remotion_innovation", "hyperframes"]
    if mix_engines:
        rng.shuffle(engines)

    out: list[dict[str, Any]] = []
    for i in range(max(1, count)):
        eng = engines[i % len(engines)] if mix_engines else base_engine
        th = themes[i % len(themes)]
        lay = layouts[i % len(layouts)]
        col = colors[i % len(colors)]
        inno = inno_presets[i % len(inno_presets)]
        bgm = bgm_files[i % len(bgm_files)]
        ord_mode = "original" if i == 0 else non_orig_orders[(i - 1) % len(non_orig_orders)]
        offset = 0.0 if i == 0 else round(rng.uniform(4.5 + i * 3.0, 8.5 + i * 4.0), 1)
        out.append(
            {
                "name": f"Random Mix {i + 1}: {th} · {lay} · {inno}",
                "render_engine": eng,
                "innovation_preset": inno,
                "badge_style": badge_styles[i % len(badge_styles)],
                "visual_theme": th,
                "creative_mode": creative_modes[i % len(creative_modes)],
                "camera_intensity": rng.choice(["subtle", "dynamic_ai", "energetic"]),
                "layout_style": lay,
                "color_preset": col,
                "font_heading": font_headings[i % len(font_headings)],
                "overlay_effect": overlay_effects[i % len(overlay_effects)],
                "hook_y": round(rng.uniform(0.13, 0.19), 2),
                "subtitle_y": round(rng.uniform(0.70, 0.76), 2),
                "bgm_track": bgm,
                "subtitle_active_color": sub_colors[i % len(sub_colors)],
                "tts_speed": round(rng.uniform(1.01, 1.06), 2),
                "clip_order_mode": ord_mode,
                "offset_sec": offset,
            }
        )
    return out


def build_batch_mix_profile(variant_index: int) -> dict[str, Any]:
    """Return distinct visual, audio, layout, color, camera & clip-offset mix profiles for multi-channel export."""
    profiles = [
        {
            "name": "Mix 1: Full Screen · Bạc Hà (Upbeat)",
            "badge_style": "floral_plus_callouts",
            "visual_theme": "fresh_mint",
            "creative_mode": "breakthrough_ai",
            "camera_intensity": "dynamic_ai",
            "layout_style": "full",
            "color_preset": "natural",
            "bgm_track": "bgm_upbeat_tiktok.wav",
            "subtitle_active_color": "#00F2FE",
            "tts_speed": 1.08,
            "clip_order_mode": "original",
            "offset_sec": 0.0,
        },
        {
            "name": "Mix 2: Thẻ Bo Góc · Sang Trọng (Warm Film)",
            "badge_style": "floral_plus_callouts",
            "visual_theme": "luxury_dark",
            "creative_mode": "breakthrough_ai",
            "camera_intensity": "subtle",
            "layout_style": "card_blur",
            "color_preset": "warm_film",
            "bgm_track": "bgm_chill_lofi.wav",
            "subtitle_active_color": "#FFE500",
            "tts_speed": 1.04,
            "clip_order_mode": "rotate_2",
            "offset_sec": 8.5,
        },
        {
            "name": "Mix 3: Top Banner · Flash Sale (Cool Vivid)",
            "badge_style": "floral_plus_callouts",
            "visual_theme": "flash_gold",
            "creative_mode": "flash_checklist",
            "camera_intensity": "energetic",
            "layout_style": "top_banner",
            "color_preset": "cool_vivid",
            "bgm_track": "bgm_flash_sale.wav",
            "subtitle_active_color": "#FB7185",
            "tts_speed": 1.12,
            "clip_order_mode": "rotate_4_swap",
            "offset_sec": 16.5,
        },
    ]
    return dict(profiles[variant_index % len(profiles)])


def reorder_clips_for_variant(
    clips: list[dict[str, Any]],
    order_mode: str = "original",
    dur_map: dict[str, float] | None = None,
    offset_sec: float = 0.0,
) -> list[dict[str, Any]]:
    """Reorder & smart-offset curated clips on long raw videos so each channel variant uses distinct frames."""
    if not clips or (order_mode == "original" and offset_sec <= 0.1) or len(clips) < 2:
        return [dict(c) for c in clips]

    cloned = [dict(c) for c in clips]
    n = len(cloned)
    if order_mode == "rotate_2" and n >= 3:
        shift = min(2, n - 1)
        reordered = cloned[shift:] + cloned[:shift]
        flip_zoom = {"push_in": "zoom_out", "zoom_out": "push_in", "punch_in": "zoom_out", "in_out": "ken_burns", "ken_burns": "in_out"}
        flip_trans = {"flash": "slide", "slide": "flash", "hard": "zoom", "zoom": "hard"}
    elif order_mode == "rotate_4_swap" and n >= 3:
        shift = min(4, n - 1)
        head = cloned[shift:shift + 2]
        rest = cloned[:shift] + cloned[shift + 2:]
        reordered = head + list(reversed(rest))
        flip_zoom = {"push_in": "punch_in", "zoom_out": "ken_burns", "punch_in": "in_out", "in_out": "zoom_out", "ken_burns": "punch_in"}
        flip_trans = {"flash": "zoom", "slide": "flash", "hard": "slide", "zoom": "flash"}
    elif order_mode == "reverse_hook" and n >= 2:
        reordered = list(reversed(cloned))
        flip_zoom = {"push_in": "zoom_out", "zoom_out": "punch_in", "punch_in": "zoom_out", "in_out": "push_in", "ken_burns": "zoom_out"}
        flip_trans = {"flash": "zoom", "slide": "hard", "hard": "flash", "zoom": "slide"}
    elif order_mode == "shuffle_mid" and n >= 3:
        import random
        head_idx = max(1, n // 2)
        rest = cloned[:head_idx] + cloned[head_idx + 1 :]
        random.shuffle(rest)
        reordered = [cloned[head_idx]] + rest
        if reordered == cloned:
            reordered = cloned[1:] + cloned[:1]
        flip_zoom = {"push_in": "in_out", "zoom_out": "punch_in", "punch_in": "ken_burns", "in_out": "zoom_out", "ken_burns": "push_in"}
        flip_trans = {"flash": "slide", "slide": "zoom", "hard": "flash", "zoom": "hard"}
    else:
        reordered = cloned
        flip_zoom = {}
        flip_trans = {}

    for idx, item in enumerate(reordered):
        if offset_sec > 0.5 and dur_map:
            src = str(item.get("source") or "").replace("\\", "/").strip()
            max_d = float(dur_map.get(src) or 0.0)
            st = float(item.get("start") or 0.0)
            en = float(item.get("end") or (st + 2.5))
            span = max(0.8, en - st)
            if max_d > span + 18.0:
                usable_hi = max(1.0, max_d - 0.8 - span)
                new_st = 0.8 + ((st - 0.8 + offset_sec) % max(1.0, usable_hi - 0.8))
                item["start"] = round(new_st, 3)
                item["end"] = round(min(max_d - 0.5, new_st + span), 3)

        cur_zm = str(item.get("zoom_mode") or "push_in")
        item["zoom_mode"] = flip_zoom.get(cur_zm, cur_zm if not flip_zoom else ("punch_in" if idx == 0 else "zoom_out"))
        cur_tr = str(item.get("transition_type") or "hard")
        item["transition_type"] = flip_trans.get(cur_tr, cur_tr if not flip_trans else "flash")
        item.pop("feature_pill", None)
    return reordered


def align_edit_plan_to_voice_beats(
    raw_videos: list[dict[str, Any]] | None = None,
    preserve_clips: bool = True,
    target_duration_override: float | None = None,
    transition_level: str | None = None,
) -> dict[str, Any]:
    """Sync edit_plan.json clips to voice_beats.json exact durations, preserving user clips when preserve_clips=True."""
    beats_res = repair_subtitles_and_beats()
    voice_beats = beats_res.get("voice_beats") or {}
    beats = voice_beats.get("beats") or []
    brief = load_brand_brief()
    target_total = float(
        target_duration_override
        or voice_beats.get("total_duration_sec")
        or brief.get("target_duration_sec")
        or 30.0
    )

    # Discover raw video durations cleanly
    dur_map: dict[str, float] = {}
    if raw_videos:
        for v in raw_videos:
            rel = str(v.get("rel_path") or "").strip()
            if rel:
                dur_map[rel] = float(v.get("duration_sec") or 10.0)
    elif DIR_VIDEO_THO.exists():
        for p in sorted(DIR_VIDEO_THO.iterdir()):
            if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"):
                dur_map[f"02_video_tho/{p.name}"] = _probe_duration_sec(p) or 10.0

    director_plan: dict[str, Any] = {}
    if FILE_DIRECTOR_PLAN.exists():
        try:
            director_plan = json.loads(FILE_DIRECTOR_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    edit_plan: dict[str, Any] = {}
    if FILE_EDIT_PLAN.exists():
        try:
            edit_plan = json.loads(FILE_EDIT_PLAN.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    existing_clips = edit_plan.get("clips") if isinstance(edit_plan.get("clips"), list) else []
    director_clips = director_plan.get("refined_clips") if isinstance(director_plan.get("refined_clips"), list) else []
    if preserve_clips and existing_clips:
        source_clips = existing_clips
    else:
        source_clips = director_clips if director_clips else existing_clips

    if len(dur_map) > 1 and source_clips:
        by_name = {Path(k).name: k for k in dur_map}
        valid_srcs: set[str] = set()
        for c in source_clips:
            if not isinstance(c, dict):
                continue
            s = str(c.get("source") or "").replace("\\", "/").strip()
            resolved = s if s in dur_map else by_name.get(Path(s).name, "")
            if resolved:
                valid_srcs.add(resolved)
        if len(valid_srcs) <= 1:
            source_clips = []

    if not source_clips and dur_map:
        dna_cur = load_style_dna()
        t_level = str(transition_level or dna_cur.get("transition_level") or "balanced")
        raw_items = list(dur_map.items())
        if t_level == "gentle":
            n_clips = max(4, min(6, len(beats) if beats else 5))
        elif t_level == "energetic":
            n_clips = max(9, min(12, len(beats) * 2 if beats else max(9, len(raw_items) * 2)))
        else:
            n_clips = max(6, min(8, (len(beats) + 2) if beats else 7))
        n_clips = max(n_clips, min(len(raw_items), 8))
        per_d = round(target_total / n_clips, 2)
        cursor_map = {src: (1.5 if d > 8.0 else 0.0) for src, d in raw_items}
        for ci in range(n_clips):
            src, src_d = raw_items[ci % len(raw_items)]
            cur_s = cursor_map.get(src, 0.0)
            safe_end = max(1.0, src_d - (0.6 if src_d > 6.0 else 0.0))
            end_s = min(safe_end, cur_s + per_d)
            if end_s - cur_s < 0.8:
                cur_s = 1.0 if src_d > 6.0 else 0.0
                end_s = min(src_d, cur_s + per_d)
            source_clips.append(
                {
                    "source": src,
                    "start": round(cur_s, 2),
                    "end": round(end_s, 2),
                    "speed": 1.0,
                    "mute": True,
                    "crop_mode": "center",
                    "note": f"Cảnh #{ci + 1}",
                }
            )
            cursor_map[src] = end_s + 0.8

    if not source_clips:
        return edit_plan

    # First pass: sanitize timestamps and avoid camera-shake start/end edges on long raw files
    sanitized: list[dict[str, Any]] = []
    for idx, c in enumerate(source_clips, start=1):
        if not isinstance(c, dict):
            continue
        src = str(c.get("source") or "").replace("\\", "/").strip()
        if src not in dur_map and dur_map:
            by_name = {Path(k).name: k for k in dur_map}
            src = by_name.get(Path(src).name, next(iter(dur_map.keys())))
        max_d = float(dur_map.get(src) or 120.0)
        eff_max_d = max_d - 0.8 if (max_d > 6.0 and not preserve_clips) else max_d
        speed = round(max(0.5, min(2.0, float(c.get("speed") or 1.0))), 2)
        st = max(0.0, float(c.get("start") or 0.0))
        en = max(st + 0.6, float(c.get("end") or (st + 2.0)))
        span = en - st
        if not preserve_clips and st < 0.8 and max_d > span + 2.5:
            st = 0.8
            en = st + span
        if en > eff_max_d:
            en = max(0.8, eff_max_d)
            st = max(0.0, en - span)

        sanitized.append(
            {
                "source": src,
                "start": round(st, 3),
                "end": round(en, 3),
                "speed": speed,
                "mute": True,
                "crop_mode": c.get("crop_mode") if c.get("crop_mode") in ("center", "blur_bg") else "center",
                "zoom_mode": c.get("zoom_mode"),
                "zoom_from": c.get("zoom_from"),
                "zoom_to": c.get("zoom_to"),
                "pan_x": c.get("pan_x"),
                "pan_y": c.get("pan_y"),
                "transition_type": c.get("transition_type"),
                "feature_pill": c.get("feature_pill"),
                "note": str(c.get("note") or ""),
            }
        )

    if not sanitized:
        return edit_plan

    # Second pass: scale durations proportionally so sum matches voice duration + bind dynamic camera motion & feature pills
    raw_sum = sum(max(0.3, (c["end"] - c["start"]) / c["speed"]) for c in sanitized) or 1.0
    scale_factor = target_total / raw_sum if raw_sum > 0 else 1.0
    timeline_cursor = 0.0
    callouts = director_plan.get("callouts") if isinstance(director_plan.get("callouts"), list) else []

    for ci, c in enumerate(sanitized):
        src_max = float(dur_map.get(c["source"]) or 120.0)
        eff_max = src_max - 0.8 if (src_max > 6.0 and not preserve_clips) else src_max
        base_dur = (c["end"] - c["start"]) / c["speed"]
        if ci == len(sanitized) - 1:
            desired_dur = max(0.8, round(target_total - timeline_cursor, 3))
        else:
            desired_dur = max(0.9, round(base_dur * scale_factor, 3))

        needed_span = desired_dur * c["speed"]
        st = c["start"]
        en = st + needed_span
        if en > eff_max:
            en = max(0.8, eff_max)
            st = max(0.0, en - needed_span)
        c["start"] = round(st, 3)
        c["end"] = round(en, 3)
        actual_dur = (c["end"] - c["start"]) / c["speed"]
        mid_t = timeline_cursor + actual_dur * 0.5
        timeline_cursor += actual_dur

        matched_beat = beats[-1] if beats else None
        for b in beats:
            if float(b["start"]) <= mid_t <= float(b["end"]) + 0.15:
                matched_beat = b
                break
        if matched_beat:
            c["beat_index"] = int(matched_beat["index"])
            c["spoken_text"] = str(matched_beat["display_text"])

        for co in callouts:
            if isinstance(co, dict):
                cs = float(co.get("startTime") if co.get("startTime") is not None else (co.get("start") or 0.0))
                cd = float(co.get("duration") or 2.2)
                ce = float(co.get("end") if co.get("end") is not None else (cs + cd))
                if cs <= mid_t <= ce:
                    c["callout_text"] = str(co.get("text") or "")
                    break

        cam_default = _assign_camera_motion(ci, len(sanitized), str(c.get("spoken_text") or ""))
        if not c.get("zoom_mode"):
            c["zoom_mode"] = cam_default["zoom_mode"]
            c["zoom_from"] = cam_default["zoom_from"]
            c["zoom_to"] = cam_default["zoom_to"]
            c["pan_x"] = cam_default["pan_x"]
            c["pan_y"] = cam_default["pan_y"]
        else:
            c["zoom_from"] = float(c.get("zoom_from") or cam_default["zoom_from"])
            c["zoom_to"] = float(c.get("zoom_to") or cam_default["zoom_to"])
            c["pan_x"] = int(c.get("pan_x") or 0)
            c["pan_y"] = int(c.get("pan_y") or 0)
        if not c.get("transition_type"):
            c["transition_type"] = cam_default["transition_type"]
        if not c.get("feature_pill") or _is_legacy_shampoo_pill(str(c.get("feature_pill") or ""), brief):
            c["feature_pill"] = _extract_feature_pill_from_text(
                str(c.get("spoken_text") or c.get("callout_text") or c.get("note") or ""),
                brief,
                ci,
            )

    if timeline_cursor < target_total - 0.4 and sanitized:
        base_snapshots = [dict(x) for x in sanitized]
        pad_idx = 0
        while timeline_cursor < target_total - 0.25 and pad_idx < 12:
            src_clip = dict(base_snapshots[pad_idx % len(base_snapshots)])
            c_dur = max(0.3, (src_clip["end"] - src_clip["start"]) / src_clip["speed"])
            rem = target_total - timeline_cursor
            if c_dur > rem + 0.15 and rem >= 0.8:
                src_clip["end"] = round(src_clip["start"] + rem * src_clip["speed"], 3)
                c_dur = rem
            src_clip["transition_type"] = "flash" if len(sanitized) % 2 == 1 else "hard"
            sanitized.append(src_clip)
            timeline_cursor += c_dur
            pad_idx += 1

    aligned_plan = {
        "title": str(edit_plan.get("title") or brief.get("brand") or "San pham TikTok Shop"),
        "target_resolution": [1080, 1920],
        "target_fps": 30,
        "concat_draft": True,
        "keep_clip_audio": False,
        "beat_locked": True,
        "clips_locked": bool(preserve_clips),
        "voice_duration_sec": round(target_total, 3),
        "clips": sanitized,
    }
    FILE_EDIT_PLAN.parent.mkdir(parents=True, exist_ok=True)
    FILE_EDIT_PLAN.write_text(json.dumps(aligned_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return aligned_plan


if __name__ == "__main__":
    dna = update_style_dna()
    brief = save_brand_brief()
    rep = repair_subtitles_and_beats()
    words = ensure_words_json_from_srt()
    print(
        json.dumps(
            {
                "ok": True,
                "words_count": len(words),
                "repair": rep,
                "brand_brief": brief,
                "words_file": str(FILE_WORDS_JSON),
                "style_dna_file": str(FILE_STYLE_DNA),
                "style_dna": dna,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
