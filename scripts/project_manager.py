#!/usr/bin/env python3
"""Multi-Project Workspace Manager for TikTok OpenReel AI.

Keeps shared AI models (`03_voice_clone`), shared BGM/SFX (`06_assets_audio`), and
render studios (`remotion_studio`, `hyperframes_studio`) at the repository root,
while strictly isolating `01_video_mau`, `02_video_tho`, `04_workspace`, and `05_output`
per project under `projects/<project_id>/`.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT_DIR / "projects"
ACTIVE_PROJECT_FILE = ROOT_DIR / "active_project.json"
PROJECT_SCOPED_ROOTS = ("02_video_tho", "04_workspace", "05_output")


def sanitize_project_id(raw: str) -> str:
    norm = unicodedata.normalize("NFKD", str(raw or "").strip())
    ascii_str = "".join(ch for ch in norm if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_str.lower()).strip("_-")
    return slug[:48] or f"project_{int(time.time())}"


def _list_project_dirs() -> list[Path]:
    if not PROJECTS_DIR.exists():
        return []
    return [
        d
        for d in sorted(PROJECTS_DIR.iterdir(), key=lambda x: x.name.lower())
        if d.is_dir() and not d.name.startswith(".") and d.name != "default"
    ]


def _get_fallback_project_id() -> str:
    dirs = _list_project_dirs()
    if dirs:
        return dirs[0].name
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    fallback_id = "du_an_dau_tien"
    proj_dir = PROJECTS_DIR / fallback_id
    ensure_project_dirs(proj_dir)
    meta_file = proj_dir / "project.json"
    if not meta_file.exists():
        meta_file.write_text(
            json.dumps(
                {"id": fallback_id, "name": "Dự án đầu tiên", "created_at": int(time.time())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return fallback_id


def get_active_project_id() -> str:
    env_id = str(os.environ.get("TIKTOK_PROJECT_ID") or "").strip()
    if env_id and env_id != "default" and (PROJECTS_DIR / env_id).is_dir():
        return env_id
    if ACTIVE_PROJECT_FILE.exists():
        try:
            data = json.loads(ACTIVE_PROJECT_FILE.read_text(encoding="utf-8-sig"))
            pid = str(data.get("active_id") or "").strip()
            if pid and pid != "default" and (PROJECTS_DIR / pid).is_dir():
                return pid
        except Exception:
            pass
    fallback = _get_fallback_project_id()
    try:
        ACTIVE_PROJECT_FILE.write_text(
            json.dumps({"active_id": fallback, "updated_at": int(time.time())}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return fallback


def get_project_root(project_id: str | None = None) -> Path:
    raw_pid = str(project_id or "").strip()
    if raw_pid and raw_pid != "default" and (PROJECTS_DIR / raw_pid).is_dir():
        pid = raw_pid
    else:
        pid = get_active_project_id()
    proj_dir = PROJECTS_DIR / pid
    proj_dir.mkdir(parents=True, exist_ok=True)
    return proj_dir


def ensure_project_dirs(project_root: Path) -> None:
    (ROOT_DIR / "01_video_mau").mkdir(parents=True, exist_ok=True)
    (ROOT_DIR / "04_workspace" / "frames" / "01_video_mau").mkdir(parents=True, exist_ok=True)
    for rel in (
        "02_video_tho",
        "04_workspace",
        "04_workspace/frames",
        "04_workspace/frames/02_video_tho",
        "04_workspace/ready_for_openreel",
        "04_workspace/ready_for_openreel/01_clips",
        "05_output",
    ):
        (project_root / rel).mkdir(parents=True, exist_ok=True)


def _describe_project(pid: str, proj_root: Path, active_id: str) -> dict[str, Any]:
    meta_file = proj_root / "project.json"
    display_name = pid
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8-sig"))
            display_name = str(meta.get("name") or display_name)
        except Exception:
            pass

    raw_dir = proj_root / "02_video_tho"
    out_dir = proj_root / "05_output"
    brief_file = proj_root / "04_workspace" / "brand_brief.json"

    raw_count = sum(1 for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}) if raw_dir.exists() else 0
    out_count = sum(1 for p in out_dir.glob("*.mp4") if p.is_file()) if out_dir.exists() else 0
    brand = ""
    brief_ready = False
    if brief_file.exists():
        try:
            b = json.loads(brief_file.read_text(encoding="utf-8-sig"))
            brand = str(b.get("brand") or "").strip()
            usps = str(b.get("usps") or "").strip()
            raw_b = str(b.get("raw_brief") or "").strip()
            prod = str(b.get("product_line") or "").strip()
            dur = float(b.get("target_duration_sec") or 0)
            brief_ready = bool(
                (len(raw_b) >= 12 and dur >= 8)
                or (brand and brand.lower() != "chưa thiết lập" and max(len(usps), len(raw_b), len(prod)) >= 5 and dur >= 8)
            )
            if not brand and len(raw_b) >= 12:
                brand = "Brief Thô (Chờ AI)"
        except Exception:
            pass

    missing_reasons: list[str] = []
    if not brief_ready:
        missing_reasons.append("Thiếu Brief")
    if raw_count <= 0:
        missing_reasons.append("Thiếu Video thô")

    return {
        "id": pid,
        "name": display_name,
        "is_active": pid == active_id,
        "is_default": False,
        "path": str(proj_root),
        "raw_video_count": raw_count,
        "output_count": out_count,
        "brand": brand,
        "brief_ready": brief_ready,
        "ready": brief_ready and raw_count > 0,
        "missing_reasons": missing_reasons,
    }


def list_projects() -> dict[str, Any]:
    active_id = get_active_project_id()
    items = [_describe_project(d.name, d, active_id) for d in _list_project_dirs()]
    return {
        "active_id": active_id,
        "active_root": str(get_project_root(active_id)),
        "projects": items,
    }


def set_active_project(project_id: str) -> dict[str, Any]:
    pid = str(project_id or "").strip()
    if not pid or pid == "default":
        raise FileNotFoundError("Project mặc định đã bị xoá, vui lòng chọn Project trong thư mục projects/.")
    proj_dir = PROJECTS_DIR / pid
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"Không tìm thấy project: {pid}")
    ensure_project_dirs(proj_dir)
    ACTIVE_PROJECT_FILE.write_text(
        json.dumps({"active_id": pid, "updated_at": int(time.time())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.environ["TIKTOK_PROJECT_ID"] = pid
    return list_projects()


def create_project(
    name: str,
    switch_to: bool = True,
    raw_brief: str = "",
    target_duration_sec: float = 25.0,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Vui lòng nhập tên Project.")
    pid = sanitize_project_id(clean_name)
    if pid == "default":
        pid = f"project_{int(time.time())}"
    proj_dir = PROJECTS_DIR / pid
    if proj_dir.exists():
        raise ValueError(f"Project `{pid}` đã tồn tại.")
    ensure_project_dirs(proj_dir)
    (proj_dir / "project.json").write_text(
        json.dumps({"id": pid, "name": clean_name, "created_at": int(time.time())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if str(raw_brief or "").strip():
        brief_path = proj_dir / "04_workspace" / "brand_brief.json"
        brief_path.write_text(
            json.dumps(
                {
                    "target_duration_sec": round(max(8.0, min(90.0, float(target_duration_sec or 25.0))), 1),
                    "raw_brief": str(raw_brief).strip(),
                    "brand": "",
                    "product_line": "",
                    "category": "",
                    "usps": "",
                    "offer_cta": "",
                    "banned_words": "",
                    "brief_ai_extracted": False,
                    "phonetic_map": {"Freeship": "phờ ri síp"},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if switch_to:
        return set_active_project(pid)
    return list_projects()
