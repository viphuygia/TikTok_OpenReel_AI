#!/usr/bin/env python3
"""HyperFrames HTML5/GSAP Editorial Bento + Beat-Synced Video Renderer."""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import remotion_renderer as _remotion_mod
from remotion_renderer import (
    DIR_REMOTION_PUBLIC,
    DIR_WORKSPACE,
    FILE_DEFAULT_OUTPUT,
    FILE_REMOTION_PROPS,
    ROOT_DIR,
    build_remotion_props,
    find_ffmpeg,
    resolve_script_named_output_path,
)

DIR_HYPERFRAMES_STUDIO = ROOT_DIR / "hyperframes_studio"
DIR_HYPERFRAMES_BUILD = DIR_WORKSPACE / "hyperframes_build"
LOCAL_GSAP_MIN = DIR_HYPERFRAMES_STUDIO / "node_modules" / "gsap" / "dist" / "gsap.min.js"


def refresh_project_paths(project_root: Path | None = None) -> Path:
    global DIR_WORKSPACE, FILE_DEFAULT_OUTPUT, FILE_REMOTION_PROPS, DIR_HYPERFRAMES_BUILD
    proj_root = _remotion_mod.refresh_project_paths(project_root)
    DIR_WORKSPACE = _remotion_mod.DIR_WORKSPACE
    FILE_DEFAULT_OUTPUT = _remotion_mod.FILE_DEFAULT_OUTPUT
    FILE_REMOTION_PROPS = _remotion_mod.FILE_REMOTION_PROPS
    DIR_HYPERFRAMES_BUILD = DIR_WORKSPACE / "hyperframes_build"
    return proj_root


def find_hyperframes_cli() -> Path | None:
    """Locate local hyperframes CLI binary."""
    candidates = [
        DIR_HYPERFRAMES_STUDIO / "node_modules" / ".bin" / "hyperframes.cmd",
        DIR_HYPERFRAMES_STUDIO / "node_modules" / ".bin" / "hyperframes",
        DIR_HYPERFRAMES_STUDIO / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    found = shutil.which("hyperframes")
    return Path(found) if found else None


def get_hyperframes_status() -> dict[str, Any]:
    cli = find_hyperframes_cli()
    return {
        "available": cli is not None,
        "cli_path": str(cli) if cli else "",
        "studio_dir": str(DIR_HYPERFRAMES_STUDIO),
        "gsap_local": LOCAL_GSAP_MIN.exists(),
    }


def _extract_bgm_beats(cli: Path, build_dir: Path, bgm_file: Path, total_duration: float) -> list[float]:
    """Use `hyperframes beats` to extract real musical beat timestamps, with safe fallback."""
    try:
        proc = subprocess.run(
            [str(cli), "beats", str(bgm_file.name)],
            cwd=str(build_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        beats_dir = build_dir / "beats"
        if proc.returncode == 0 and beats_dir.exists():
            for jf in beats_dir.glob("*.json"):
                data = json.loads(jf.read_text(encoding="utf-8-sig"))
                raw_beats = data.get("beats") or data.get("onsets") or []
                parsed = [round(float(b), 3) for b in raw_beats if isinstance(b, (int, float)) and 0 <= float(b) <= total_duration]
                if parsed:
                    return parsed[:60]
    except Exception:
        pass
    # Fallback steady 110 BPM beat grid
    step = 0.545
    t = 0.5
    out = []
    while t < total_duration and len(out) < 60:
        out.append(round(t, 3))
        t += step
    return out


def _detect_hw_h264_encoder(ffmpeg: str) -> tuple[str, list[str]]:
    """Return fastest working hardware H.264 encoder on this machine, or libx264 fallback."""
    for enc, extra in (
        ("h264_qsv", ["-global_quality", "20"]),
        ("h264_nvenc", ["-cq", "20"]),
    ):
        try:
            r = subprocess.run(
                [ffmpeg, "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=640x480:d=0.1,format=yuv420p", "-c:v", enc, "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                return enc, extra
        except Exception:
            pass
    return "libx264", ["-preset", "veryfast", "-crf", "20"]


def _concat_clips_to_bg_mp4(
    clips: list[dict[str, Any]],
    out_mp4: Path,
    total_duration: float,
    frame_w: int = 1080,
    frame_h: int = 1920,
) -> None:
    """Normalize clips to target resolution@30fps."""
    ffmpeg = find_ffmpeg()
    vcodec, vcodec_args = _detect_hw_h264_encoder(ffmpeg)
    seg_dir = out_mp4.parent / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    seg_files: list[Path] = []
    for idx, clip in enumerate(clips):
        src_rel = str(clip.get("src") or "").lstrip("/")
        src_path = DIR_REMOTION_PUBLIC / src_rel
        if not src_path.exists():
            continue
        dur = max(0.4, float(clip.get("duration") or 2.0))
        seg_path = seg_dir / f"seg_{idx:03d}.mp4"
        # Preserve real 30fps video motion (never use zoompan on video streams, which freezes frame 0)
        vf = f"scale={frame_w}:{frame_h}:force_original_aspect_ratio=increase,crop={frame_w}:{frame_h},fps=30,format=yuv420p"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src_path),
            "-t",
            f"{dur:.3f}",
            "-an",
            "-vf",
            vf,
            "-c:v",
            vcodec,
            *vcodec_args,
            "-bf",
            "0",
            "-g",
            "15",
            str(seg_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if proc.returncode == 0 and seg_path.exists():
            seg_files.append(seg_path)

    if not seg_files:
        raise RuntimeError("Không thể chuẩn hóa clip nền cho HyperFrames.")

    concat_list = seg_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in seg_files),
        encoding="utf-8",
    )
    cmd_concat = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-t",
        f"{max(1.5, total_duration):.3f}",
        "-c",
        "copy",
        str(out_mp4),
    ]
    proc2 = subprocess.run(cmd_concat, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if proc2.returncode != 0 or not out_mp4.exists():
        raise RuntimeError(f"FFmpeg concat lỗi: {proc2.stderr}")


HYPERFRAMES_THEMES: dict[str, dict[str, str]] = {
    "floral_rose": {
        "card_bg": "rgba(76, 5, 45, 0.72)",
        "card_border": "2px solid rgba(251, 113, 133, 0.75)",
        "brand_bg": "linear-gradient(90deg, #EC4899, #BE185D)",
        "product_color": "#FFFFFF",
        "cat_color": "#FFF380",
        "progress_gradient": "linear-gradient(90deg, #FB7185, #FDE047, #38BDF8)",
        "pill_active": "#BE185D",
        "cta_bg": "linear-gradient(90deg, #F59E0B, #EF4444)",
        "cta_border": "2px solid #FEF08A",
        "particle": "rgba(251, 113, 133, 0.22)",
    },
    "fresh_mint": {
        "card_bg": "rgba(8, 51, 68, 0.76)",
        "card_border": "2px solid rgba(103, 232, 249, 0.85)",
        "brand_bg": "linear-gradient(90deg, #06B6D4, #10B981)",
        "product_color": "#ECFEFF",
        "cat_color": "#67E8F9",
        "progress_gradient": "linear-gradient(90deg, #22D3EE, #34D399, #A7F3D0)",
        "pill_active": "#0E7490",
        "cta_bg": "linear-gradient(90deg, #0891B2, #10B981)",
        "cta_border": "2px solid #A5F3FC",
        "particle": "rgba(103, 232, 249, 0.22)",
    },
    "flash_gold": {
        "card_bg": "rgba(127, 29, 29, 0.82)",
        "card_border": "3px solid #FDE047",
        "brand_bg": "linear-gradient(90deg, #FACC15, #F97316)",
        "product_color": "#FFE500",
        "cat_color": "#FFFFFF",
        "progress_gradient": "linear-gradient(90deg, #FACC15, #F97316, #EF4444)",
        "pill_active": "#DC2626",
        "cta_bg": "linear-gradient(90deg, #DC2626, #EA580C)",
        "cta_border": "2px solid #FDE047",
        "particle": "rgba(250, 204, 21, 0.22)",
    },
    "luxury_dark": {
        "card_bg": "rgba(12, 12, 16, 0.84)",
        "card_border": "2px solid rgba(251, 191, 36, 0.8)",
        "brand_bg": "linear-gradient(90deg, #D97706, #FBBF24)",
        "product_color": "#FEF3C7",
        "cat_color": "#FBBF24",
        "progress_gradient": "linear-gradient(90deg, #FBBF24, #F59E0B, #FEF3C7)",
        "pill_active": "#B45309",
        "cta_bg": "linear-gradient(90deg, #92400E, #D97706)",
        "cta_border": "2px solid #FCD34D",
        "particle": "rgba(251, 191, 36, 0.2)",
    },
    "ribbon_sticker": {
        "card_bg": "rgba(24, 24, 27, 0.8)",
        "card_border": "3px solid #FFFFFF",
        "brand_bg": "#FF4D6D",
        "product_color": "#FFFFFF",
        "cat_color": "#FFE500",
        "progress_gradient": "linear-gradient(90deg, #FF4D6D, #FFE500, #38BDF8)",
        "pill_active": "#2563EB",
        "cta_bg": "linear-gradient(90deg, #E11D48, #2563EB)",
        "cta_border": "2px solid #FFFFFF",
        "particle": "rgba(56, 189, 248, 0.22)",
    },
}

HF_COLOR_FILTERS: dict[str, str] = {
    "natural": "contrast(1.03) saturate(1.06)",
    "warm_film": "contrast(1.06) saturate(1.12) sepia(0.09)",
    "cool_vivid": "contrast(1.08) saturate(1.15) hue-rotate(-4deg)",
}


def _build_semantic_word_chunks(words: list[dict[str, Any]], max_words: int = 5, max_chars: int = 28) -> list[dict[str, Any]]:
    """Group words into natural 4-6 word Vietnamese phrases using punctuation and speech gaps."""
    chunks: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def _flush() -> None:
        if not buf:
            return
        chunks.append(
            {
                "start": float(buf[0].get("start") or 0.0),
                "end": float(buf[-1].get("end") or 0.0),
                "words": [
                    {
                        "word": str(item.get("word") or ""),
                        "start": float(item.get("start") or 0.0),
                        "end": float(item.get("end") or 0.0),
                    }
                    for item in buf
                ],
            }
        )
        buf.clear()

    for w in words:
        w_txt = str(w.get("word") or "").strip()
        if not w_txt:
            continue
        w_start = float(w.get("start") or 0.0)
        if buf:
            prev_end = float(buf[-1].get("end") or 0.0)
            cur_chars = sum(len(str(x.get("word") or "")) + 1 for x in buf) + len(w_txt)
            gap = w_start - prev_end
            if len(buf) >= max_words or cur_chars > max_chars or gap > 0.28:
                _flush()
        buf.append({"word": w_txt, "start": w_start, "end": float(w.get("end") or w_start)})
        if w_txt[-1:] in (".", "!", "?", ";", ",") and len(buf) >= 2:
            _flush()
    _flush()
    return chunks


def _clean_sticker_text(raw_text: str) -> str:
    from style_dna import strip_slop_emojis
    return html.escape(strip_slop_emojis(raw_text))


def _twemoji_inline_svg_html(raw_text: str, size_px: int = 32) -> str:
    """Escape text safely and inline crisp Twemoji SVG elements (zero <img> tag mismatch)."""
    import re
    from style_dna import ensure_twemoji_svg

    emoji_re = re.compile(r"([\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?)")
    parts = emoji_re.split(str(raw_text or ""))
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if emoji_re.fullmatch(part):
            svg_p = ensure_twemoji_svg(part)
            if svg_p is not None and svg_p.exists():
                svg_txt = svg_p.read_text(encoding="utf-8-sig").strip()
                svg_txt = re.sub(
                    r"<svg\b([^>]*)>",
                    f'<svg\\1 width="{size_px}" height="{size_px}" style="display:inline-block;vertical-align:-0.18em;margin:0 4px;">',
                    svg_txt,
                    count=1,
                )
                out.append(svg_txt)
                continue
        out.append(html.escape(part))
    return "".join(out)


def _build_hyperframes_html(
    props: dict[str, Any],
    has_voice: bool,
    has_bgm: bool,
    has_local_gsap: bool,
    beats: list[float],
) -> str:
    duration = max(1.5, float(props.get("durationSec") or 25.0))
    title = html.escape(str(props.get("title") or "TikTok Shop Review"))
    badge = props.get("floralBadge") or {}
    brand = html.escape(str(badge.get("brand") or "REVIEW CHÂN THẬT"))
    product = html.escape(str(badge.get("productLine") or title))
    category = html.escape(str(badge.get("category") or ""))
    badge_start = float(badge.get("start") or 0.0)
    badge_end = float(badge.get("end") or 3.8)
    bgm_vol = float(props.get("bgmVolume") or 0.14)
    active_color = str(props.get("subtitleActiveColor") or "#FFE500")
    theme_id = str(props.get("visualTheme") or "fresh_mint")
    theme = HYPERFRAMES_THEMES.get(theme_id, HYPERFRAMES_THEMES["fresh_mint"])
    color_preset = str(props.get("colorPreset") or "natural")
    video_filter = HF_COLOR_FILTERS.get(color_preset, "none")
    font_heading = str(props.get("fontHeading") or "Baloo 2").replace("'", "").strip() or "Baloo 2"
    font_specs = [
        ("Montserrat Black", "Montserrat-Black.ttf", "900"),
        ("Baloo 2", "Baloo2-ExtraBold.ttf", "800"),
        ("Dancing Script", "DancingScript-Bold.ttf", "700"),
        ("Pacifico", "Pacifico-Regular.ttf", "400"),
        ("Be Vietnam Pro", "BeVietnamPro-Black.ttf", "900"),
        ("Anton", "Anton-Regular.ttf", "400"),
        ("Oswald", "Oswald-Bold.ttf", "700"),
        ("Nunito", "Nunito-Black.ttf", "900"),
        ("Quicksand", "Quicksand-Bold.ttf", "700"),
        ("Bricolage Grotesque", "BricolageGrotesque-ExtraBold.ttf", "800"),
        ("Lora", "Lora-Bold.ttf", "700"),
        ("Paytone One", "PaytoneOne-Regular.ttf", "400"),
    ]
    font_faces_css = "\n    ".join(
        f"@font-face {{ font-family: '{fam}'; src: url('./fonts/{fname}') format('truetype'); font-weight: {wt}; font-style: normal; }}"
        for fam, fname, wt in font_specs
    )

    words = props.get("words") or []
    chunks = _build_semantic_word_chunks(words, max_words=5, max_chars=28)
    wc = props.get("wildcardSpec") or {}
    is_wildcard = bool(isinstance(wc, dict) and wc)
    if isinstance(wc, dict) and wc.get("accentColor"):
        active_color = str(wc.get("accentColor") or active_color)
    frame_w = int(props.get("width") or (1920 if props.get("aspectRatio") == "16:9" else 1080))
    frame_h = int(props.get("height") or (1080 if props.get("aspectRatio") == "16:9" else 1920))
    content_vibe = str(props.get("contentVibe") or "learned_dna").strip()
    is_vlog = content_vibe not in ("", "learned_dna")
    sub_top_px = int(round(frame_h * float((wc.get("subtitleY") if isinstance(wc, dict) and wc.get("subtitleY") else None) or props.get("subtitleY") or (0.83 if frame_w > frame_h else 0.73))))
    sub_variant = str(wc.get("subtitleVariant") or "clean_stroke") if isinstance(wc, dict) else "clean_stroke"
    letterbox_px = 0 if frame_w > frame_h else (int(wc.get("letterboxPx") or 0) if isinstance(wc, dict) else 0)
    icon_density = str(props.get("iconDensity") or "balanced")
    sticker_density = str(props.get("stickerDensity") or "normal")
    default_cta = "✨ Lưu Lại Xem Sau" if is_vlog else "🛒 Giỏ Hàng Góc Trái"
    cta_raw = str(wc.get("ctaLabel") or default_cta) if isinstance(wc, dict) else default_cta
    stamp_html_text = "CHILL<br/>VLOG" if is_vlog else "TIKTOK<br/>SHOP"
    cta_label = _twemoji_inline_svg_html(cta_raw, size_px=34)
    archetype = str(wc.get("layoutArchetype") or "editorial_zine") if is_wildcard else "clean_editorial"
    motif_kind = str(wc.get("motifKind") or "sparkle_burst") if is_wildcard else "sparkle_burst"
    hook_layout = str(wc.get("hookLayout") or "center_bold") if is_wildcard else "center_bold"
    show_rating = bool(wc.get("showRatingBadge")) if is_wildcard else False
    ticker_raw = str(wc.get("tickerText") or f"🔥 {brand} · {product} · GIỎ HÀNG GÓC TRÁI")
    ticker_text = (
        _clean_sticker_text(ticker_raw)
        if icon_density == "minimal"
        else _twemoji_inline_svg_html(ticker_raw, size_px=24)
    )
    raw_custom_svg = str(wc.get("customSvgOverlay") or "").strip() if is_wildcard else ""
    if raw_custom_svg and ("<script" in raw_custom_svg.lower() or "on" in raw_custom_svg.lower() and "onload=" in raw_custom_svg.lower()):
        raw_custom_svg = ""
    pop_palette = (
        wc.get("popPalette")
        if isinstance(wc, dict) and isinstance(wc.get("popPalette"), list) and len(wc.get("popPalette")) >= 3
        else ["#FF4D6D", "#FFE500", "#00F5D4", "#38BDF8", "#A855F7"]
    )
    sticker_events = (
        []
        if sticker_density == "off"
        else (
            wc.get("stickerEvents")
            if isinstance(wc, dict) and isinstance(wc.get("stickerEvents"), list)
            else []
        )
    )
    if sticker_events:
        from style_dna import resolve_animated_sticker_asset
        for s_idx, s_item in enumerate(sticker_events):
            if isinstance(s_item, dict):
                if not s_item.get("stickerAsset"):
                    s_item["stickerAsset"] = resolve_animated_sticker_asset(str(s_item.get("emoji") or ""), s_idx)
                if not s_item.get("styleKind"):
                    s_item["styleKind"] = "animated_sticker" if (s_item.get("stickerAsset") and s_idx % 2 == 0) else "messenger_bubble"

    clips_meta = []
    unique_usps: list[str] = []
    for c in props.get("clips") or []:
        clips_meta.append(
            {
                "start": float(c.get("startInTimeline") or 0.0),
                "duration": max(0.5, float(c.get("duration") or 2.0)),
            }
        )
        pill = str(c.get("featurePill") or "").strip()
        if pill and pill not in unique_usps and len(unique_usps) < 3:
            unique_usps.append(pill)

    lottie_payloads: dict[str, Any] = {}
    lot_dir = ROOT_DIR / "assets" / "lottie_stickers"
    for s_idx, s_item in enumerate(sticker_events):
        if isinstance(s_item, dict) and s_item.get("styleKind") == "animated_sticker":
            asset_s = str(s_item.get("stickerAsset") or "")
            stem = Path(asset_s).stem
            lot_file = lot_dir / f"{stem}.json"
            if stem and lot_file.exists():
                try:
                    lottie_payloads[stem] = json.loads(lot_file.read_text(encoding="utf-8-sig"))
                    s_item["lottieKey"] = stem
                except Exception:
                    pass

    data_json = json.dumps(
        {
            "duration": duration,
            "activeColor": active_color,
            "particleColor": theme["particle"],
            "transitionLevel": str(props.get("transitionLevel") or "balanced"),
            "disableFlashShake": props.get("disableFlashShake", True) is not False,
            "isWildcard": is_wildcard,
            "archetype": archetype,
            "motif": motif_kind,
            "popPalette": pop_palette,
            "stickerEvents": sticker_events,
            "lottiePayloads": lottie_payloads,
            "chunks": chunks,
            "clips": clips_meta,
            "usps": unique_usps,
            "beats": beats,
            "badgeStart": badge_start,
            "badgeEnd": badge_end,
            "checklistStart": round(duration * 0.24, 3),
            "checklistEnd": round(duration * 0.68, 3),
            "ctaStart": round(duration * 0.68, 3),
        },
        ensure_ascii=False,
    )

    gsap_src = "./gsap.min.js" if has_local_gsap else "https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"
    voice_tag = (
        f'<audio data-start="0" data-duration="{duration:.3f}" data-volume="1.0" src="./voice.wav"></audio>'
        if has_voice
        else ""
    )
    bgm_tag = (
        f'<audio data-start="0" data-duration="{duration:.3f}" data-volume="{bgm_vol:.3f}" src="./bgm.wav"></audio>'
        if has_bgm
        else ""
    )

    story_bars = "".join(
        f'<div class="story-seg" style="flex:{c["duration"]:.2f}"><div class="story-fill" id="sf-{idx}"></div></div>'
        for idx, c in enumerate(clips_meta or [{"start": 0.0, "duration": duration}])
    )
    usp_rows = "".join(
        f'<div class="usp-row" id="usp-{idx}"><span class="usp-tick" id="tick-{idx}">✓</span><span>{_twemoji_inline_svg_html(u, size_px=26) if icon_density == "expressive" else _clean_sticker_text(u)}</span></div>'
        for idx, u in enumerate(unique_usps)
    )
    def _render_hf_sticker(idx: int, st: dict[str, Any]) -> str:
        xp = float(st.get("xPct", 0.08)) * 100
        yp = float(st.get("yPct", 0.30)) * 100
        bg = html.escape(str(st.get("bg") or pop_palette[idx % len(pop_palette)]))
        rot = int(st.get("rotateDeg") or (-6 if idx % 2 == 0 else 6))
        lbl = _clean_sticker_text(str(st.get("label") or "HOT"))
        asset = str(st.get("stickerAsset") or "").strip().lstrip("/")
        if asset.startswith("assets/"):
            asset = asset[len("assets/"):]
        lkey = str(st.get("lottieKey") or "").strip()
        if st.get("styleKind") == "animated_sticker" and lkey:
            return (
                f'<div class="hf-sticker-anim" id="hf-stk-{idx}" style="left:{xp:.1f}%;top:{yp:.1f}%;--rot:{rot}deg;">'
                f'<div id="hf-lot-{idx}" style="width:136px;height:136px;filter:drop-shadow(0 10px 22px rgba(0,0,0,0.45));"></div>'
                f'<span class="hf-stk-pill" style="background:{bg};">{lbl}</span>'
                f'</div>'
            )
        if st.get("styleKind") == "animated_sticker" and asset and asset.lower().endswith(".png"):
            return (
                f'<div class="hf-sticker-anim" id="hf-stk-{idx}" style="left:{xp:.1f}%;top:{yp:.1f}%;--rot:{rot}deg;">'
                f'<img src="./{html.escape(asset)}" style="width:132px;height:132px;object-fit:contain;filter:drop-shadow(0 10px 22px rgba(0,0,0,0.45));" alt=""/>'
                f'<span class="hf-stk-pill" style="background:{bg};">{lbl}</span>'
                f'</div>'
            )
        return (
            f'<div class="hf-sticker-bubble" id="hf-stk-{idx}" style="left:{xp:.1f}%;top:{yp:.1f}%;background:{bg};--rot:{rot}deg;">'
            f'<span class="hf-stk-lb">{lbl}</span>'
            f'</div>'
        )

    sticker_divs = "".join(
        _render_hf_sticker(idx, st)
        for idx, st in enumerate(sticker_events)
        if isinstance(st, dict)
    )

    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <script src="{gsap_src}"></script>
  {('<script src="./lottie.min.js"></script>' if (ROOT_DIR / "assets" / "lottie.min.js").exists() else '')}
  <style>
    {font_faces_css}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: {frame_w}px;
      height: {frame_h}px;
      overflow: hidden;
      background: transparent !important;
      font-family: '{font_heading}', 'Be Vietnam Pro', 'Segoe UI', system-ui, sans-serif;
    }}
    .root {{
      position: relative;
      width: {frame_w}px;
      height: {frame_h}px;
      overflow: hidden;
      background: transparent !important;
    }}
    .clip {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      filter: {video_filter};
    }}
    .scrim {{
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(0,0,0,0.48) 0%, rgba(0,0,0,0) 28%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.68) 100%);
      pointer-events: none;
    }}
    #fx-canvas {{
      position: absolute;
      inset: 0;
      pointer-events: none;
    }}
    .story-bar {{
      position: absolute;
      top: 24px;
      left: 36px;
      right: 36px;
      display: flex;
      gap: 8px;
      pointer-events: none;
    }}
    .story-seg {{
      height: 7px;
      border-radius: 999px;
      background: rgba(255,255,255,0.22);
      overflow: hidden;
    }}
    .story-fill {{
      width: 0%;
      height: 100%;
      background: {theme["progress_gradient"]};
    }}
    .hook-card {{
      position: absolute;
      top: 260px;
      left: 56px;
      right: 56px;
      padding: 28px 34px;
      border-radius: 28px;
      background: {theme["card_bg"]};
      backdrop-filter: blur(18px);
      border: {theme["card_border"]};
      box-shadow: 0 24px 54px rgba(0,0,0,0.52);
      text-align: center;
      opacity: 0;
      clip-path: inset(0 100% 0 0);
    }}
    .hook-brand {{
      display: inline-block;
      padding: 6px 22px;
      border-radius: 999px;
      background: {theme["brand_bg"]};
      color: #FFFFFF;
      font-weight: 900;
      font-size: 26px;
      letter-spacing: 1.8px;
      text-transform: uppercase;
      margin-bottom: 12px;
    }}
    .hook-product {{
      font-weight: 900;
      font-size: 64px;
      line-height: 1.08;
      color: {theme["product_color"]};
      text-shadow: 0 4px 16px rgba(0,0,0,0.75);
    }}
    .hook-cat {{
      margin-top: 10px;
      font-weight: 800;
      font-size: 32px;
      color: {theme["cat_color"]};
    }}
    .bento-usp {{
      position: absolute;
      top: 470px;
      left: 46px;
      padding: 16px 22px;
      border-radius: 22px;
      background: rgba(9, 13, 22, 0.72);
      backdrop-filter: blur(14px);
      border: 2px solid rgba(103,232,249,0.45);
      box-shadow: 0 16px 36px rgba(0,0,0,0.45);
      display: flex;
      flex-direction: column;
      gap: 10px;
      opacity: 0;
      transform: translateX(-30px);
    }}
    .usp-row {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
      font-size: 28px;
      color: #FFFFFF;
      opacity: 0.25;
    }}
    .usp-tick {{
      width: 30px;
      height: 30px;
      border-radius: 999px;
      background: rgba(255,255,255,0.18);
      color: #FFFFFF;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 900;
    }}
    .usp-row.on {{
      opacity: 1;
    }}
    .usp-row.on .usp-tick {{
      background: #10B981;
    }}
    .subtitle-wrap {{
      position: absolute;
      top: {sub_top_px}px;
      left: 44px;
      right: 44px;
      transform: translateY(-50%);
      display: flex;
      justify-content: center;
      pointer-events: none;
    }}
    .subtitle-inner {{
      display: inline-flex;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
      gap: 8px 14px;
      padding: {"0px" if sub_variant == "clean_stroke" else "12px 24px"};
      border-radius: 20px;
      background: {"transparent" if sub_variant == "clean_stroke" else ("rgba(15,23,42,0.74)" if sub_variant == "glass_pill" else f"{theme['pill_active']}D9")};
      border: {"2px solid rgba(255,255,255,0.22)" if sub_variant == "glass_pill" else "none"};
    }}
    .word {{
      display: inline-block;
      font-weight: 900;
      font-size: 54px;
      line-height: 1.2;
      color: rgba(255,255,255,0.92);
      -webkit-text-stroke: 9px #090D16;
      paint-order: stroke fill;
      text-shadow: 0 5px 12px rgba(0,0,0,0.92);
    }}
    .word.active {{
      color: {active_color};
      text-shadow: 0 0 22px {active_color}99, 0 5px 12px rgba(0,0,0,0.92);
    }}
    .lbox-top, .lbox-bot {{
      position: absolute;
      left: 0;
      right: 0;
      height: {letterbox_px}px;
      background: #050810;
      pointer-events: none;
    }}
    .lbox-top {{ top: 0; }}
    .lbox-bot {{ bottom: 0; }}
    .cta-pill {{
      position: absolute;
      bottom: 110px;
      left: 52px;
      padding: 14px 28px;
      border-radius: 999px;
      background: {theme["cta_bg"]};
      border: {theme["cta_border"]};
      color: #FFFFFF;
      font-weight: 900;
      font-size: 32px;
      box-shadow: 0 12px 28px rgba(0,0,0,0.48);
      opacity: 0;
      transform: translateY(20px);
    }}
    .ai-svg-art {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      opacity: 0.78;
    }}
    .polaroid-frame {{
      position: absolute;
      top: 108px;
      left: 42px;
      right: 42px;
      bottom: 185px;
      border: 18px solid #FAF8F5;
      border-bottom-width: 78px;
      border-radius: 16px;
      box-shadow: 0 28px 64px rgba(0,0,0,0.55);
      pointer-events: none;
    }}
    .tape-l, .tape-r {{
      position: absolute;
      top: 90px;
      width: 148px;
      height: 36px;
      background: rgba(253, 224, 71, 0.76);
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
      pointer-events: none;
    }}
    .tape-l {{ left: 74px; transform: rotate(-22deg); }}
    .tape-r {{ right: 74px; transform: rotate(20deg); }}
    .hud-bracket {{
      position: absolute;
      width: 66px;
      height: 66px;
      pointer-events: none;
    }}
    .hud-tl {{ top: 54px; left: 28px; border-top: 5px solid {active_color}; border-left: 5px solid {active_color}; }}
    .hud-tr {{ top: 54px; right: 28px; border-top: 5px solid {active_color}; border-right: 5px solid {active_color}; }}
    .hud-bl {{ bottom: 64px; left: 28px; border-bottom: 5px solid {active_color}; border-left: 5px solid {active_color}; }}
    .hud-br {{ bottom: 64px; right: 28px; border-bottom: 5px solid {active_color}; border-right: 5px solid {active_color}; }}
    .hud-rec {{
      position: absolute;
      top: 74px;
      right: 48px;
      padding: 6px 16px;
      border-radius: 10px;
      background: rgba(9,13,22,0.78);
      border: 2px solid {active_color};
      color: {active_color};
      font-weight: 900;
      font-size: 20px;
      letter-spacing: 1.4px;
      pointer-events: none;
    }}
    .zine-masthead {{
      position: absolute;
      top: 50px;
      left: 36px;
      right: 36px;
      display: flex;
      justify-content: space-between;
      border-bottom: 2px solid {active_color};
      padding-bottom: 8px;
      font-weight: 900;
      font-size: 22px;
      letter-spacing: 1.8px;
      color: #FFFFFF;
      text-shadow: 0 2px 8px rgba(0,0,0,0.8);
      pointer-events: none;
    }}
    .rating-pill {{
      position: absolute;
      top: 96px;
      left: 38px;
      padding: 8px 18px;
      border-radius: 999px;
      background: rgba(9,13,22,0.84);
      border: 2px solid {active_color};
      color: #FFE500;
      font-weight: 900;
      font-size: 22px;
      pointer-events: none;
    }}
    .ticker-bar {{
      position: absolute;
      bottom: 42px;
      left: 0;
      right: 0;
      height: 46px;
      background: {active_color};
      color: #090D16;
      font-weight: 900;
      font-size: 24px;
      display: flex;
      align-items: center;
      overflow: hidden;
      pointer-events: none;
    }}
    .ticker-inner {{
      white-space: nowrap;
      will-change: transform;
    }}
    .stamp-seal {{
      position: absolute;
      top: 320px;
      right: 32px;
      width: 136px;
      height: 136px;
      pointer-events: none;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .stamp-seal-text {{
      position: relative;
      z-index: 2;
      color: #090D16;
      font-weight: 900;
      font-size: 16px;
      line-height: 1.1;
      text-align: center;
    }}
    .kinetic-ribbon {{
      position: absolute;
      top: 970px;
      left: -30px;
      right: -30px;
      height: 58px;
      background: {active_color};
      color: #090D16;
      font-weight: 900;
      font-size: 27px;
      letter-spacing: 1.4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transform: rotate(-1.6deg);
      box-shadow: 0 10px 28px rgba(0,0,0,0.5);
      opacity: 0;
      pointer-events: none;
    }}
    .callout-arrow {{
      position: absolute;
      top: 685px;
      right: 36px;
      width: 220px;
      height: 140px;
      overflow: visible;
      pointer-events: none;
    }}
    .hf-sticker-anim {{
      position: absolute;
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      opacity: 0;
      transform: scale(0.2) rotate(var(--rot, -6deg));
      pointer-events: none;
      z-index: 4;
    }}
    .hf-stk-pill {{
      padding: 4px 14px;
      border-radius: 999px;
      border: 3px solid #FFFFFF;
      font-size: 19px;
      font-weight: 900;
      color: #090D16;
      box-shadow: 0 8px 20px rgba(0,0,0,0.45);
    }}
    .hf-sticker-bubble {{
      position: absolute;
      display: inline-flex;
      align-items: center;
      padding: 12px 22px;
      border-radius: 24px 24px 24px 6px;
      border: 3.5px solid #FFFFFF;
      box-shadow: 0 14px 32px rgba(0,0,0,0.45);
      opacity: 0;
      transform: scale(0.2) rotate(var(--rot, -5deg));
      pointer-events: none;
      z-index: 4;
    }}
    .hf-stk-lb {{ font-size: 22px; font-weight: 900; color: #090D16; letter-spacing: 0.5px; }}
  </style>
</head>
<body>
  <div class="root" data-composition-id="root" data-start="0" data-duration="{duration:.3f}" data-width="{frame_w}" data-height="{frame_h}">
    <div class="scrim"></div>
    {('<div class="lbox-top"></div><div class="lbox-bot"></div>' if letterbox_px > 0 else '')}
    <div id="hf-clock" style="position:absolute;top:0;left:0;height:1px;width:0%;opacity:0;pointer-events:none;"></div>
    <canvas id="fx-canvas" width="{frame_w}" height="{frame_h}"></canvas>
    {(f'<div class="ai-svg-art" id="hf-ai-svg">{raw_custom_svg}</div>' if raw_custom_svg else '')}
    <div class="stamp-seal" id="hf-stamp">
      <svg id="hf-stamp-svg" viewBox="0 0 140 140" width="136" height="136" style="position:absolute;inset:0;">
        <polygon points="70,4 84,20 105,12 108,33 129,38 121,58 136,74 120,88 127,108 106,112 101,132 81,123 65,137 52,121 31,128 28,107 7,102 15,82 0,66 16,52 9,32 30,28 35,8 55,17" fill="{active_color}"/>
      </svg>
      <div class="stamp-seal-text">{stamp_html_text}</div>
    </div>
    {(f'<div class="kinetic-ribbon" id="hf-ribbon">⚡ {brand} · {html.escape(unique_usps[0]) if unique_usps else product}</div>' if archetype in ('bento_split', 'kinetic_poster') else '')}
    <svg class="callout-arrow" viewBox="0 0 220 140">
      <path id="hf-arrow-path" d="M 190 16 Q 110 8 42 86 M 42 86 L 72 82 M 42 86 L 48 56" fill="none" stroke="{active_color}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="320" stroke-dashoffset="320"/>
    </svg>
    {sticker_divs}
    {('<div class="polaroid-frame"></div><div class="tape-l"></div><div class="tape-r"></div>' if is_wildcard and archetype == 'polaroid_scrapbook' else '')}
    {('<div class="hud-bracket hud-tl"></div><div class="hud-bracket hud-tr"></div><div class="hud-bracket hud-bl"></div><div class="hud-bracket hud-br"></div><div class="hud-rec" id="hf-rec">● REC · CAM 01</div>' if archetype == 'tech_hud' else '')}
    {('<div class="zine-masthead"><span id="hf-zine-issue">ISSUE #01 · ' + brand + '</span><span style="color:' + active_color + '">TIKTOK EDIT 2026</span></div>') if archetype == 'editorial_zine' else ''}
    {(f'<div class="ticker-bar"><div class="ticker-inner" id="hf-ticker">{ticker_text} &nbsp; ★ &nbsp; {ticker_text} &nbsp; ★ &nbsp; {ticker_text}</div></div>' if is_wildcard and (archetype == 'bento_split' or hook_layout == 'breaking_ticker') else '')}
    <div class="story-bar">{story_bars}</div>
    <div class="hook-card" id="hf-hook">
      <div class="hook-brand">{brand}</div>
      <div class="hook-product">{product}</div>
      <div class="hook-cat">{category}</div>
    </div>
    <div class="bento-usp" id="hf-bento">{usp_rows}</div>
    <div class="subtitle-wrap"><div class="subtitle-inner" id="hf-sub"></div></div>
    <div class="cta-pill" id="hf-cta">{cta_label}</div>
  </div>
  <script>
    const HF_DATA = {data_json};
    const tl = gsap.timeline({{ paused: true }});
    // Tween a real DOM property across full HF_DATA.duration so GSAP fires onUpdate on every frame
    tl.to('#hf-clock', {{ width: '100%', duration: HF_DATA.duration, ease: 'none' }}, 0);

    // Clip-path mask reveal for Editorial Hook Card
    tl.to('#hf-hook', {{
      opacity: 1,
      clipPath: 'inset(0 0% 0 0)',
      duration: 0.45,
      ease: 'power3.out'
    }}, HF_DATA.badgeStart);
    tl.to('#hf-hook', {{
      opacity: 0,
      y: -26,
      duration: 0.25,
      ease: 'power2.in'
    }}, Math.max(0.6, HF_DATA.badgeEnd - 0.25));

      if (HF_DATA.usps.length > 0) {{
      tl.to('#hf-bento', {{
        opacity: 1,
        x: 0,
        duration: 0.4,
        ease: 'back.out(1.4)'
      }}, HF_DATA.checklistStart);
      tl.to('#hf-arrow-path', {{
        strokeDashoffset: 0,
        duration: 0.65,
        ease: 'power2.out'
      }}, HF_DATA.checklistStart + 0.1);
      tl.to('#hf-ribbon', {{
        opacity: 1,
        duration: 0.35,
        ease: 'power2.out'
      }}, HF_DATA.checklistStart);
      tl.to('#hf-bento, #hf-arrow-path, #hf-ribbon', {{
        opacity: 0,
        duration: 0.25,
        ease: 'power2.in'
      }}, Math.max(HF_DATA.checklistStart + 1.0, HF_DATA.checklistEnd));
    }}

    // Beat-synced pulse on CTA (skipped when disableFlashShake=true)
    if (!HF_DATA.disableFlashShake) {{
      HF_DATA.beats.forEach((bt) => {{
        if (bt >= HF_DATA.ctaStart) {{
          tl.to('#hf-cta', {{ scale: 1.06, duration: 0.08, yoyo: true, repeat: 1, ease: 'power1.out' }}, bt);
        }}
      }});
    }}

    tl.to('#hf-cta', {{ opacity: 1, y: 0, duration: 0.35, ease: 'back.out(1.6)' }}, HF_DATA.ctaStart);

    const lottieAnims = {{}};
    if (window.lottie && HF_DATA.lottiePayloads) {{
      (HF_DATA.stickerEvents || []).forEach((st, idx) => {{
        const key = st.lottieKey;
        const container = document.getElementById(`hf-lot-${{idx}}`);
        const payload = key ? HF_DATA.lottiePayloads[key] : null;
        if (container && payload) {{
          lottieAnims[idx] = window.lottie.loadAnimation({{
            container,
            renderer: 'svg',
            loop: true,
            autoplay: false,
            animationData: payload,
          }});
        }}
      }});
    }}

    // Dynamic Multi-Color TikTok Sticker Popups synced to Beats
    (HF_DATA.stickerEvents || []).forEach((st, idx) => {{
      const sel = `#hf-stk-${{idx}}`;
      const sT = Math.max(0.1, Number(st.start || 1.0));
      const dT = Math.max(1.2, Number(st.duration || 2.4));
      tl.to(sel, {{ opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(1.9)' }}, sT);
      tl.to(sel, {{ opacity: 0, scale: 0.3, duration: 0.25, ease: 'power2.in' }}, sT + dT);
    }});

    const subBox = document.getElementById('hf-sub');
    const canvas = document.getElementById('fx-canvas');
    const ctx = canvas.getContext('2d');

    function syncAtTime(t) {{
      // Story segmented bar
      const segs = HF_DATA.clips.length ? HF_DATA.clips : [{{ start: 0, duration: HF_DATA.duration }}];
      segs.forEach((c, idx) => {{
        const fill = document.getElementById(`sf-${{idx}}`);
        if (!fill) return;
        const pct = t >= c.start + c.duration ? 100 : t <= c.start ? 0 : ((t - c.start) / c.duration) * 100;
        fill.style.width = `${{pct.toFixed(1)}}%`;
      }});

      // Bento USP sequential ticks
      HF_DATA.usps.forEach((_, idx) => {{
        const row = document.getElementById(`usp-${{idx}}`);
        if (row) row.classList.toggle('on', t >= HF_DATA.checklistStart + idx * 0.65);
      }});

      // Semantic subtitles (exact [start-0.08, end+0.14] window, no layout shift)
      const activeChunk = HF_DATA.chunks.find(c => t >= (c.start - 0.08) && t <= (c.end + 0.14));
      if (!activeChunk) {{
        subBox.innerHTML = '';
        subBox.style.display = 'none';
      }} else {{
        subBox.style.display = 'inline-flex';
        subBox.innerHTML = activeChunk.words.map((w) => {{
          const isAct = t >= (w.start - 0.03) && t <= (w.end + 0.09);
          return `<span class="word ${{isAct ? 'active' : ''}}">${{w.word}}</span>`;
        }}).join('');
      }}

      // Procedural Canvas Motion Graphics (Multi-Color Equalizer + Confetti + Motif Art + Bokeh)
      ctx.clearRect(0, 0, 1080, 1920);
      const ac = HF_DATA.activeColor || '#FFE500';
      const pal = Array.isArray(HF_DATA.popPalette) && HF_DATA.popPalette.length ? HF_DATA.popPalette : [ac, '#FF4D6D', '#00F5D4', '#38BDF8', '#A855F7'];
      const motif = HF_DATA.motif || 'sparkle_burst';

      // Dynamic HUD / Wildcard Multi-Color 18-bar Audio Equalizer
      if (HF_DATA.isWildcard || HF_DATA.archetype === 'tech_hud') {{
        for (let b = 0; b < 18; b++) {{
          const bh = 12 + Math.abs(Math.sin(t * 7.5 + b * 0.65)) * 42;
          ctx.fillStyle = pal[b % pal.length];
          ctx.globalAlpha = 0.88;
          ctx.fillRect(760 + b * 14, 1790 - bh, 8, bh);
        }}
        ctx.globalAlpha = 1.0;
      }}

      // Multi-Color Confetti Pop during Hook (0-3.2s) & CTA
      if (t <= 3.2 || t >= HF_DATA.ctaStart) {{
        const localT = t <= 3.2 ? t : (t - HF_DATA.ctaStart);
        for (let ci = 0; ci < 20; ci++) {{
          const cx = ((ci * 137 + 45) % 980) + 45;
          const cy = ((ci * 97 + localT * (240 + (ci % 4) * 85)) % 1820);
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(localT * (2.2 + (ci % 5) * 0.5));
          ctx.fillStyle = pal[ci % pal.length];
          ctx.globalAlpha = 0.85;
          ctx.fillRect(-8, -10, 16, ci % 2 === 0 ? 16 : 24);
          ctx.restore();
        }}
        ctx.globalAlpha = 1.0;
      }}

      if (HF_DATA.isWildcard && motif === 'cyber_grid') {{
        ctx.strokeStyle = ac;
        ctx.globalAlpha = 0.22;
        ctx.lineWidth = 1.5;
        for (let gx = 0; gx <= 1080; gx += 108) {{
          ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, 1920); ctx.stroke();
        }}
        for (let gy = 0; gy < 16; gy++) {{
          const yy = (gy * 130 + t * 85) % 1920;
          ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(1080, yy); ctx.stroke();
        }}
        ctx.globalAlpha = 1.0;
      }} else if (HF_DATA.isWildcard && motif === 'bubbles_ice') {{
        for (let i = 0; i < 10; i++) {{
          const bx = i % 2 === 0 ? 64 + i * 20 : 1016 - i * 20;
          const by = 1900 - ((t * (75 + i * 11) + i * 210) % 1900);
          const br = 14 + (i % 4) * 8;
          ctx.beginPath();
          ctx.arc(bx, by, br, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(255,255,255,0.12)';
          ctx.fill();
          ctx.strokeStyle = ac;
          ctx.lineWidth = 2;
          ctx.stroke();
        }}
      }} else if (HF_DATA.isWildcard && (motif === 'geometric_orbit' || motif === 'sparkle_burst')) {{
        ctx.save();
        ctx.translate(925, 320);
        ctx.rotate(t * 0.9);
        ctx.strokeStyle = ac;
        ctx.globalAlpha = 0.6;
        ctx.lineWidth = 3;
        ctx.setLineDash([14, 10]);
        ctx.beginPath(); ctx.arc(0, 0, 56, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#FFE500';
        ctx.beginPath(); ctx.arc(56, 0, 9, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }} else if (HF_DATA.isWildcard && motif === 'wave_ribbon') {{
        ctx.strokeStyle = ac;
        ctx.globalAlpha = 0.42;
        ctx.lineWidth = 4;
        ctx.beginPath();
        for (let wx = 0; wx <= 1080; wx += 24) {{
          const wy = 1850 + Math.sin(wx * 0.012 + t * 3.5) * 22;
          if (wx === 0) ctx.moveTo(wx, wy);
          else ctx.lineTo(wx, wy);
        }}
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      }}

      const tickerEl = document.getElementById('hf-ticker');
      if (tickerEl) {{
        const shift = -((t * 135) % 1200);
        tickerEl.style.transform = `translateX(${{shift.toFixed(1)}}px)`;
      }}
      const stampSvg = document.getElementById('hf-stamp-svg');
      if (stampSvg) {{
        stampSvg.style.transform = `rotate(${{(t * 36).toFixed(1)}}deg)`;
      }}
      (HF_DATA.stickerEvents || []).forEach((st, idx) => {{
        const el = document.getElementById(`hf-stk-${{idx}}`);
        if (el && el.classList.contains('hf-sticker-anim')) {{
          const bob = Math.sin(t * 3.2 + idx * 1.3) * 6;
          const sway = Math.sin(t * 2.4 + idx) * 3.5;
          el.style.marginTop = `${{bob.toFixed(1)}}px`;
          el.style.marginLeft = `${{sway.toFixed(1)}}px`;
        }}
        const anim = lottieAnims[idx];
        if (anim) {{
          const localT = Math.max(0, t - Number(st.start || 0));
          const fr = Number(anim.frameRate || 30);
          const tot = Math.max(1, Number(anim.totalFrames || 60));
          anim.goToAndStop((localT * fr * 0.8) % tot, true);
        }}
      }});
      const recEl = document.getElementById('hf-rec');
      const curClipIdx = Math.max(0, segs.findIndex(c => t >= c.start && t <= c.start + c.duration));
      if (recEl) recEl.textContent = `● REC · CAM 0${{curClipIdx + 1}}`;
      const zineEl = document.getElementById('hf-zine-issue');
      if (zineEl) zineEl.textContent = `ISSUE #0${{curClipIdx + 1}} · ${{HF_DATA.brand || '{brand}'}}`;

      for (let i = 0; i < 14; i++) {{
        const px = ((i * 193 + t * (28 + (i % 4) * 12)) % 1080);
        const py = ((i * 317 - t * (35 + (i % 3) * 15)) % 1920 + 1920) % 1920;
        const r = 3 + (i % 4) * 2;
        ctx.fillStyle = HF_DATA.particleColor || 'rgba(103, 232, 249, 0.2)';
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
      }}
    }}

    tl.eventCallback('onUpdate', () => syncAtTime(tl.time()));
    syncAtTime(0);

    window.__timelines = window.__timelines || {{}};
    window.__timelines['root'] = tl;
  </script>
</body>
</html>
"""


def render_hyperframes_video(
    output_path: Path | None = None,
    rebuild_props: bool = True,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render full 1080x1920 MP4 via HyperFrames CLI using Shared Schema props."""
    cli = find_hyperframes_cli()
    if not cli:
        raise RuntimeError(
            "Chưa tìm thấy HyperFrames CLI. Hãy chạy `npm install hyperframes` trong thư mục `hyperframes_studio/`."
        )

    if rebuild_props or not FILE_REMOTION_PROPS.exists():
        props = build_remotion_props(overrides=overrides)
    else:
        props = json.loads(FILE_REMOTION_PROPS.read_text(encoding="utf-8-sig"))

    clips = props.get("clips") or []
    if not clips:
        raise RuntimeError("Chưa có clip video nào trong `04_workspace/ready_for_openreel/01_clips/`.")

    total_duration = float(props.get("durationSec") or 25.0)
    named_out_path, selected_meta = resolve_script_named_output_path(total_duration)
    use_script_naming = output_path is None or Path(output_path) == FILE_DEFAULT_OUTPUT
    target_output_path = named_out_path if use_script_naming else Path(output_path)
    target_output_path.parent.mkdir(parents=True, exist_ok=True)

    if DIR_HYPERFRAMES_BUILD.exists():
        shutil.rmtree(DIR_HYPERFRAMES_BUILD, ignore_errors=True)
    DIR_HYPERFRAMES_BUILD.mkdir(parents=True, exist_ok=True)

    frame_w = int(props.get("width") or (1920 if props.get("aspectRatio") == "16:9" else 1080))
    frame_h = int(props.get("height") or (1080 if props.get("aspectRatio") == "16:9" else 1920))
    bg_mp4 = DIR_HYPERFRAMES_BUILD / "bg_track.mp4"
    _concat_clips_to_bg_mp4(clips, bg_mp4, total_duration, frame_w=frame_w, frame_h=frame_h)

    has_voice = False
    voice_rel = str(props.get("voiceSrc") or "").lstrip("/")
    if _remotion_mod.FILE_TTS_WAV.exists():
        shutil.copy2(_remotion_mod.FILE_TTS_WAV, DIR_HYPERFRAMES_BUILD / "voice.wav")
        has_voice = True
    elif voice_rel and (DIR_REMOTION_PUBLIC / voice_rel).exists():
        shutil.copy2(DIR_REMOTION_PUBLIC / voice_rel, DIR_HYPERFRAMES_BUILD / "voice.wav")
        has_voice = True

    has_bgm = False
    beats: list[float] = []
    bgm_rel = str(props.get("bgmSrc") or "").lstrip("/")
    if bgm_rel and (DIR_REMOTION_PUBLIC / bgm_rel).exists():
        bgm_dst = DIR_HYPERFRAMES_BUILD / "bgm.wav"
        shutil.copy2(DIR_REMOTION_PUBLIC / bgm_rel, bgm_dst)
        has_bgm = True
        beats = _extract_bgm_beats(cli, DIR_HYPERFRAMES_BUILD, bgm_dst, total_duration)

    has_local_gsap = False
    if LOCAL_GSAP_MIN.exists():
        shutil.copy2(LOCAL_GSAP_MIN, DIR_HYPERFRAMES_BUILD / "gsap.min.js")
        has_local_gsap = True

    lottie_js_src = ROOT_DIR / "assets" / "lottie.min.js"
    if lottie_js_src.exists():
        shutil.copy2(lottie_js_src, DIR_HYPERFRAMES_BUILD / "lottie.min.js")

    for sub_name in ("stickers", "fonts"):
        sub_src = ROOT_DIR / "assets" / sub_name
        if sub_src.exists():
            shutil.copytree(sub_src, DIR_HYPERFRAMES_BUILD / sub_name, dirs_exist_ok=True)

    index_html = DIR_HYPERFRAMES_BUILD / "index.html"
    index_html.write_text(
        _build_hyperframes_html(props, has_voice=has_voice, has_bgm=has_bgm, has_local_gsap=has_local_gsap, beats=beats),
        encoding="utf-8",
    )

    overlay_webm = DIR_HYPERFRAMES_BUILD / "overlay.webm"
    cmd = [
        str(cli),
        "render",
        str(DIR_HYPERFRAMES_BUILD),
        "--format",
        "webm",
        "-o",
        str(overlay_webm),
        "-f",
        "30",
        "-q",
        "looks",
        "-w",
        "4",
    ]
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(DIR_HYPERFRAMES_STUDIO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if proc.returncode != 0 or not overlay_webm.exists():
        raise RuntimeError(f"HyperFrames overlay render failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")

    # Composite transparent HyperFrames WebM overlay onto clean bg_track.mp4 + TTS/BGM audio via FFmpeg
    ffmpeg = find_ffmpeg()
    vcodec, vcodec_args = _detect_hw_h264_encoder(ffmpeg)
    color_preset = str(props.get("colorPreset") or "natural")
    eq_filter = (
        "eq=contrast=1.08:saturation=1.18:brightness=0.01"
        if color_preset == "warm_film"
        else "eq=contrast=1.09:saturation=1.20:brightness=0.01"
        if color_preset == "cool_vivid"
        else "eq=contrast=1.06:saturation=1.16:brightness=0.01"
    )
    bgm_vol = float(props.get("bgmVolume") or 0.14)

    wc_dict = props.get("wildcardSpec") if isinstance(props.get("wildcardSpec"), dict) else {}
    archetype = str(wc_dict.get("layoutArchetype") or "")
    raw_ov = str(props.get("overlayEffect") or "auto").strip()
    if raw_ov and raw_ov != "auto":
        ov_file = raw_ov
    elif archetype == "tech_hud":
        ov_file = "grid_hud_overlay.png"
    elif archetype in ("polaroid_scrapbook", "editorial_zine"):
        ov_file = "paper_texture_warm.png"
    elif color_preset == "warm_film":
        ov_file = "light_leak_warm.mp4"
    elif color_preset == "cool_vivid":
        ov_file = "light_leak_cool.mp4"
    else:
        ov_file = "bokeh_sparkle.mp4"
    ov_path = (ROOT_DIR / "assets" / "overlays" / ov_file) if ov_file and ov_file != "none" else None

    comp_cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(bg_mp4),
        "-c:v",
        "libvpx-vp9",
        "-i",
        str(overlay_webm),
    ]
    audio_idx = 2
    if ov_path and ov_path.exists():
        if ov_path.suffix.lower() in (".mp4", ".webm", ".mov"):
            comp_cmd.extend(["-stream_loop", "-1", "-i", str(ov_path)])
        else:
            comp_cmd.extend(["-loop", "1", "-i", str(ov_path)])
        ov_idx = audio_idx
        audio_idx += 1
        is_paper_ov = ov_file.startswith("paper_")
        b_mode = "overlay" if is_paper_ov else "screen"
        b_op = 0.16 if is_paper_ov else (0.24 if "grain" in ov_file else 0.30)
        filter_parts = [
            f"[0:v]{eq_filter},format=gbrp[bgv];"
            f"[{ov_idx}:v]scale={frame_w}:{frame_h}:force_original_aspect_ratio=increase,crop={frame_w}:{frame_h},setsar=1,format=gbrp[ovv];"
            f"[bgv][ovv]blend=all_mode={b_mode}:all_opacity={b_op}:shortest=1,format=yuv420p[bgv_ov];"
            f"[bgv_ov][1:v]overlay=0:0:shortest=1[vout]"
        ]
    else:
        filter_parts = [f"[0:v]{eq_filter}[bgv];[bgv][1:v]overlay=0:0:shortest=1[vout]"]
    audio_map: list[str] = []

    voice_file = DIR_HYPERFRAMES_BUILD / "voice.wav"
    bgm_file = DIR_HYPERFRAMES_BUILD / "bgm.wav"
    sfx_vol_default = float(props.get("sfxVolume") or 0.55)
    sfx_inputs: list[tuple[Path, float, float]] = []
    for sfx in (props.get("sfxEvents") or [])[:8]:
        if not isinstance(sfx, dict):
            continue
        s_rel = str(sfx.get("src") or "").lstrip("/")
        s_path = (DIR_REMOTION_PUBLIC / s_rel) if s_rel else None
        if s_path and s_path.exists():
            sfx_inputs.append(
                (
                    s_path,
                    max(0.0, float(sfx.get("start") or 0.0)),
                    float(sfx.get("volume") if sfx.get("volume") is not None else sfx_vol_default),
                )
            )

    audio_mix_labels: list[str] = []
    has_v = has_voice and voice_file.exists()
    has_b = has_bgm and bgm_file.exists()

    if has_v and has_b:
        comp_cmd.extend(["-i", str(voice_file), "-stream_loop", "-1", "-i", str(bgm_file)])
        v_idx = audio_idx
        b_idx = audio_idx + 1
        audio_idx += 2
        # Auto-duck BGM cleanly whenever narrator speaks
        filter_parts.append(
            f"[{v_idx}:a]asplit=2[vo_main][vo_sc];"
            f"[{b_idx}:a]volume={bgm_vol:.3f}[bgma];"
            f"[bgma][vo_sc]sidechaincompress=threshold=0.02:ratio=4:attack=80:release=420[bgm_duck]"
        )
        audio_mix_labels.extend(["[vo_main]", "[bgm_duck]"])
    elif has_v:
        comp_cmd.extend(["-i", str(voice_file)])
        audio_mix_labels.append(f"[{audio_idx}:a]")
        audio_idx += 1
    elif has_b:
        comp_cmd.extend(["-stream_loop", "-1", "-i", str(bgm_file)])
        filter_parts.append(f"[{audio_idx}:a]volume={bgm_vol:.3f}[bgma]")
        audio_mix_labels.append("[bgma]")
        audio_idx += 1

    for si, (sp_path, s_start, s_vol) in enumerate(sfx_inputs):
        comp_cmd.extend(["-i", str(sp_path)])
        delay_ms = int(round(s_start * 1000))
        s_lbl = f"sfx_{si}"
        filter_parts.append(f"[{audio_idx}:a]adelay={delay_ms}|{delay_ms},volume={s_vol:.2f}[{s_lbl}]")
        audio_mix_labels.append(f"[{s_lbl}]")
        audio_idx += 1

    if len(audio_mix_labels) == 1:
        audio_map = ["-map", audio_mix_labels[0]]
    elif len(audio_mix_labels) > 1:
        filter_parts.append(
            f"{''.join(audio_mix_labels)}amix=inputs={len(audio_mix_labels)}:duration=first:normalize=0:dropout_transition=2[aout]"
        )
        audio_map = ["-map", "[aout]"]

    comp_cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
            *audio_map,
            "-t",
            f"{total_duration:.3f}",
            "-c:v",
            vcodec,
            *vcodec_args,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(target_output_path),
        ]
    )
    proc_comp = subprocess.run(
        comp_cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    elapsed = round(time.time() - t0, 2)
    if proc_comp.returncode != 0 or not target_output_path.exists():
        raise RuntimeError(f"FFmpeg composite lỗi ({proc_comp.returncode}):\n{proc_comp.stderr[-600:]}")

    if target_output_path != FILE_DEFAULT_OUTPUT:
        FILE_DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_output_path, FILE_DEFAULT_OUTPUT)

    return {
        "ok": True,
        "engine": "hyperframes",
        "output_path": str(target_output_path),
        "default_output_path": str(FILE_DEFAULT_OUTPUT),
        "elapsed_sec": elapsed,
        "selected_script_id": selected_meta["selected_id"],
        "selected_script_label": selected_meta["label"],
        "props": props,
    }
