#!/usr/bin/env python3
"""Download Vietnamese-supported Google Fonts and generate transparent SVG stickers."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT_DIR / "assets" / "fonts"
STICKERS_DIR = ROOT_DIR / "assets" / "stickers"

FONT_SPECS = {
    "Montserrat-Black.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Montserrat:wght@900&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/static/Montserrat-Black.ttf",
        ],
    },
    "Baloo2-ExtraBold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Baloo+2:wght@800&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/baloo2/static/Baloo2-ExtraBold.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/baloo2/Baloo2%5Bwght%5D.ttf",
        ],
    },
    "DancingScript-Bold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Dancing+Script:wght@700&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/dancingscript/static/DancingScript-Bold.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/dancingscript/DancingScript%5Bwght%5D.ttf",
        ],
    },
    "Pacifico-Regular.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Pacifico&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/pacifico/Pacifico-Regular.ttf",
        ],
    },
    "BeVietnamPro-Black.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@900&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/bevietnampro/BeVietnamPro-Black.ttf",
        ],
    },
    "Anton-Regular.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Anton&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
        ],
    },
    "Oswald-Bold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Oswald:wght@700&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/oswald/static/Oswald-Bold.ttf",
        ],
    },
    "Nunito-Black.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Nunito:wght@900&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/nunito/static/Nunito-Black.ttf",
        ],
    },
    "Quicksand-Bold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Quicksand:wght@700&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/quicksand/static/Quicksand-Bold.ttf",
        ],
    },
    "BricolageGrotesque-ExtraBold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@800&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/bricolagegrotesque/static/BricolageGrotesque-ExtraBold.ttf",
        ],
    },
    "Lora-Bold.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Lora:wght@700&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/lora/static/Lora-Bold.ttf",
        ],
    },
    "PaytoneOne-Regular.ttf": {
        "css_url": "https://fonts.googleapis.com/css2?family=Paytone+One&display=swap",
        "github_urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/paytoneone/PaytoneOne-Regular.ttf",
        ],
    },
}

SVG_STICKERS = {
    "floral_top.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 110" fill="none">
  <!-- Botanical arch with blossoms & mint leaves -->
  <path d="M55 82 C110 38, 250 38, 305 82" stroke="#34D399" stroke-width="4" stroke-linecap="round" opacity="0.9"/>
  <!-- Left leaves -->
  <path d="M90 66 C70 46, 52 52, 62 72 C74 78, 86 74, 90 66Z" fill="#10B981" stroke="#065F46" stroke-width="2.5"/>
  <path d="M126 52 C112 28, 92 30, 98 52 C108 60, 120 58, 126 52Z" fill="#6EE7B7" stroke="#065F46" stroke-width="2.5"/>
  <!-- Right leaves -->
  <path d="M270 66 C290 46, 308 52, 298 72 C286 78, 274 74, 270 66Z" fill="#10B981" stroke="#065F46" stroke-width="2.5"/>
  <path d="M234 52 C248 28, 268 30, 262 52 C252 60, 240 58, 234 52Z" fill="#6EE7B7" stroke="#065F46" stroke-width="2.5"/>
  <!-- Center flower -->
  <g transform="translate(180,38)">
    <circle cx="0" cy="-16" r="11" fill="#FDA4AF" stroke="#FFFFFF" stroke-width="2.5"/>
    <circle cx="15" cy="-5" r="11" fill="#FDA4AF" stroke="#FFFFFF" stroke-width="2.5"/>
    <circle cx="9" cy="13" r="11" fill="#FDA4AF" stroke="#FFFFFF" stroke-width="2.5"/>
    <circle cx="-9" cy="13" r="11" fill="#FDA4AF" stroke="#FFFFFF" stroke-width="2.5"/>
    <circle cx="-15" cy="-5" r="11" fill="#FDA4AF" stroke="#FFFFFF" stroke-width="2.5"/>
    <circle cx="0" cy="0" r="8" fill="#FDE047" stroke="#FFFFFF" stroke-width="2"/>
  </g>
  <!-- Small side blossoms -->
  <g transform="translate(138,50) scale(0.65)">
    <circle cx="0" cy="-12" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="11" cy="-4" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="7" cy="10" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="-7" cy="10" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="-11" cy="-4" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="0" cy="0" r="6" fill="#FACC15"/>
  </g>
  <g transform="translate(222,50) scale(0.65)">
    <circle cx="0" cy="-12" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="11" cy="-4" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="7" cy="10" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="-7" cy="10" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="-11" cy="-4" r="9" fill="#FFFFFF" stroke="#F472B6" stroke-width="2"/>
    <circle cx="0" cy="0" r="6" fill="#FACC15"/>
  </g>
</svg>
""",
    "floral_bottom.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 95" fill="none">
  <path d="M55 24 C120 62, 240 62, 305 24" stroke="#34D399" stroke-width="4" stroke-linecap="round" opacity="0.9"/>
  <path d="M98 42 C76 58, 60 50, 70 32 C82 28, 92 34, 98 42Z" fill="#34D399" stroke="#065F46" stroke-width="2.5"/>
  <path d="M262 42 C284 58, 300 50, 290 32 C278 28, 268 34, 262 42Z" fill="#34D399" stroke="#065F46" stroke-width="2.5"/>
  <g transform="translate(180,54) scale(0.85)">
    <circle cx="0" cy="-14" r="10" fill="#F9A8D4" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="13" cy="-4" r="10" fill="#F9A8D4" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="8" cy="11" r="10" fill="#F9A8D4" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="-8" cy="11" r="10" fill="#F9A8D4" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="-13" cy="-4" r="10" fill="#F9A8D4" stroke="#FFFFFF" stroke-width="2"/>
    <circle cx="0" cy="0" r="7" fill="#FDE047" stroke="#FFFFFF" stroke-width="2"/>
  </g>
  <circle cx="132" cy="52" r="5" fill="#FDE047"/>
  <circle cx="228" cy="52" r="5" fill="#FDE047"/>
</svg>
""",
    "sparkle_star.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" fill="none">
  <path d="M40 4 L47 33 L76 40 L47 47 L40 76 L33 47 L4 40 L33 33 Z" fill="#FDE047" stroke="#FFFFFF" stroke-width="3" stroke-linejoin="round"/>
  <circle cx="62" cy="18" r="5" fill="#FFFFFF"/>
</svg>
""",
    "badge_ribbon.svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 64" fill="none">
  <rect x="10" y="8" width="300" height="48" rx="24" fill="#FB7185" stroke="#FFFFFF" stroke-width="4"/>
  <rect x="16" y="13" width="288" height="38" rx="19" stroke="#FDE047" stroke-width="1.5" stroke-dasharray="6 4"/>
</svg>
""",
}


def _is_valid_ttf(data: bytes) -> bool:
    if len(data) < 20000:
        return False
    # TrueType (\x00\x01\x00\x00 or 'true'), OpenType ('OTTO'), TTC ('ttcf')
    return data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true")


def _download_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Python-urllib/3.11"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _extract_ttf_urls_from_css(css_url: str) -> list[str]:
    # Non-browser User-Agent makes Google Fonts return direct .ttf URLs instead of woff2 subsets
    css_bytes = _download_bytes(css_url, headers={"User-Agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)"})
    css_text = css_bytes.decode("utf-8", errors="ignore")
    urls = re.findall(r"url\((https://[^)]+\.(?:ttf|otf))\)", css_text)
    if not urls:
        # Fallback: inspect standard CSS and replace if any ttf appears
        css_bytes = _download_bytes(css_url, headers={"User-Agent": "Python-urllib/3.11"})
        css_text = css_bytes.decode("utf-8", errors="ignore")
        urls = re.findall(r"url\((https://[^)]+)\)", css_text)
    return urls


def setup_fonts_and_stickers(force: bool = False) -> dict[str, object]:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    STICKERS_DIR.mkdir(parents=True, exist_ok=True)

    downloaded_fonts: dict[str, int] = {}
    errors: list[str] = []

    for filename, spec in FONT_SPECS.items():
        dst = FONTS_DIR / filename
        if not force and dst.exists() and _is_valid_ttf(dst.read_bytes()):
            downloaded_fonts[filename] = dst.stat().st_size
            continue

        candidate_urls = list(spec["github_urls"])
        try:
            candidate_urls.extend(_extract_ttf_urls_from_css(spec["css_url"]))
        except Exception:
            pass

        saved = False
        for url in candidate_urls:
            try:
                data = _download_bytes(url)
                if _is_valid_ttf(data):
                    dst.write_bytes(data)
                    downloaded_fonts[filename] = len(data)
                    saved = True
                    break
            except Exception:
                continue

        if not saved:
            errors.append(f"Failed to download {filename}")

    stickers_created: list[str] = []
    for name, svg_content in SVG_STICKERS.items():
        out = STICKERS_DIR / name
        out.write_text(svg_content, encoding="utf-8")
        stickers_created.append(name)

    return {
        "ok": len(errors) == 0 and len(downloaded_fonts) == len(FONT_SPECS),
        "fonts": downloaded_fonts,
        "stickers": stickers_created,
        "errors": errors,
    }


if __name__ == "__main__":
    result = setup_fonts_and_stickers()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
