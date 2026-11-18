"""Self-healing Local-First Cloudflare Tunnel & LAN discovery service for FastAPI."""

from __future__ import annotations

import atexit
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BIN_DIR = PROJECT_ROOT / "assets" / "bin"
LOCAL_CLOUDFLARED = LOCAL_BIN_DIR / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
CLOUDFLARED_WIN_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
PUBLIC_URL_RE = re.compile(r"(https://(?!api\.trycloudflare\.com)[a-zA-Z0-9-]+\.trycloudflare\.com)", re.IGNORECASE)


def _is_docker_bridge_ip(ip: str) -> bool:
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return True
    return False


def get_lan_addresses(port: int = 8000) -> tuple[str, list[str]]:
    """Detect local LAN IPv4 addresses, prioritizing 192.168.x.x and 10.x.x.x."""
    candidates: list[str] = []
    host_override = str(os.environ.get("HOST_LAN_IP") or "").strip()
    if host_override:
        candidates.append(host_override)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            primary_guess = s.getsockname()[0]
            if primary_guess and not primary_guess.startswith("127.") and not _is_docker_bridge_ip(primary_guess):
                candidates.append(primary_guess)
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = str(info[4][0])
            if ip and not ip.startswith("127.") and not ip.startswith("169.254.") and not _is_docker_bridge_ip(ip):
                candidates.append(ip)
    except Exception:
        pass

    unique: list[str] = []
    for ip in candidates:
        if ip not in unique:
            unique.append(ip)

    # Sort so 192.168.* comes first, then 10.*, then others
    unique.sort(key=lambda x: (0 if x.startswith("192.168.") else (1 if x.startswith("10.") else 2)))
    primary_ip = unique[0] if unique else "127.0.0.1"
    lan_urls = [f"http://{ip}:{port}" for ip in unique] or [f"http://127.0.0.1:{port}"]
    return primary_ip, lan_urls


class TunnelService:
    """Singleton manager for on-demand cloudflared Quick/Named tunnels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self.status: str = "STOPPED"
        self.public_url: str | None = None
        self.started_at: str | None = None
        self.last_error: str | None = None
        self.recent_logs: list[str] = []
        self.active_port: int = int(os.environ.get("PORT") or "8000")
        atexit.register(self.stop_tunnel)

    def _push_log(self, line: str) -> None:
        txt = line.strip()
        if not txt:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.recent_logs.append(f"[{stamp}] {txt}")
        if len(self.recent_logs) > 35:
            self.recent_logs.pop(0)

    def is_binary_valid(self, bin_path: Path) -> bool:
        try:
            if not bin_path.exists() or not bin_path.is_file():
                return False
            if bin_path.stat().st_size < 10 * 1024 * 1024:
                return False
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            res = subprocess.run(
                [str(bin_path), "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=6,
                creationflags=flags,
            )
            return res.returncode == 0
        except Exception:
            return False

    def resolve_cloudflared_binary(self) -> Path:
        sys_candidates: list[Path] = []
        if os.name == "nt":
            sys_candidates.extend(
                [
                    Path(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"),
                    Path(r"C:\Program Files\cloudflared\cloudflared.exe"),
                ]
            )
        else:
            sys_candidates.extend(
                [
                    Path("/opt/homebrew/bin/cloudflared"),
                    Path("/usr/local/bin/cloudflared"),
                    Path("/usr/bin/cloudflared"),
                ]
            )
        which_cf = shutil.which("cloudflared")
        if which_cf:
            sys_candidates.insert(0, Path(which_cf))

        for cand in sys_candidates:
            if self.is_binary_valid(cand):
                self._push_log(f"Sử dụng cloudflared hệ thống: {cand}")
                return cand

        if LOCAL_CLOUDFLARED.exists() and not self.is_binary_valid(LOCAL_CLOUDFLARED):
            self._push_log("Phát hiện cloudflared tải dở/lỗi — đang xóa và tải lại bản chuẩn...")
            try:
                LOCAL_CLOUDFLARED.unlink()
            except Exception:
                pass

        if not LOCAL_CLOUDFLARED.exists():
            if os.name != "nt":
                raise RuntimeError("Chưa cài đặt cloudflared trên hệ thống.")
            LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)
            tmp_dst = LOCAL_CLOUDFLARED.with_suffix(".download")
            self._push_log("Đang tải cloudflared.exe chính chủ từ Cloudflare...")
            req = urllib.request.Request(CLOUDFLARED_WIN_URL, headers={"User-Agent": "TikTokOpenReelAI/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp_dst, "wb") as f:
                shutil.copyfileobj(resp, f)
            tmp_dst.replace(LOCAL_CLOUDFLARED)
            self._push_log(f"Đã tải xong cloudflared ({LOCAL_CLOUDFLARED.stat().st_size // (1024 * 1024)} MB).")

        if self.is_binary_valid(LOCAL_CLOUDFLARED):
            return LOCAL_CLOUDFLARED

        raise RuntimeError("Không thể xác thực cloudflared.exe hợp lệ (>10MB).")

    def _reader_loop(self, pipe: Any) -> None:
        try:
            for raw_line in iter(pipe.readline, ""):
                if not raw_line:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                self._push_log(line)
                m = PUBLIC_URL_RE.search(line)
                if m:
                    with self._lock:
                        self.public_url = m.group(1)
                        self.status = "ACTIVE"
                        self.started_at = self.started_at or datetime.now(timezone.utc).isoformat()
                elif os.environ.get("CLOUDFLARE_TUNNEL_TOKEN") and "Registered tunnel connection" in line:
                    with self._lock:
                        self.status = "ACTIVE"
                        self.started_at = self.started_at or datetime.now(timezone.utc).isoformat()
                        self.public_url = (
                            str(os.environ.get("CLOUDFLARE_PUBLIC_HOSTNAME") or "").strip()
                            or "https://named-tunnel-active.cloudflare.com"
                        )
        except Exception:
            pass

    def _watch_exit(self, proc: subprocess.Popen[str]) -> None:
        code = proc.wait()
        with self._lock:
            if self._proc is proc and self.status != "STOPPED":
                self._push_log(f"cloudflared đã dừng (mã: {code}).")
                self.status = "STOPPED"
                self.public_url = None
                self.started_at = None
                self._proc = None

    def start_tunnel(self, port: int | None = None) -> dict[str, Any]:
        with self._lock:
            if port:
                self.active_port = int(port)
            if self.status == "ACTIVE" and self.public_url and self._proc and self._proc.poll() is None:
                return {"success": True, "status": self.status, "publicUrl": self.public_url}

        self.stop_tunnel()

        with self._lock:
            self.status = "STARTING"
            self.public_url = None
            self.last_error = None
            self.recent_logs = []

        try:
            bin_path = self.resolve_cloudflared_binary()
            custom_token = str(os.environ.get("CLOUDFLARE_TUNNEL_TOKEN") or "").strip()
            local_target = f"http://127.0.0.1:{self.active_port}"
            args = (
                [str(bin_path), "tunnel", "--no-autoupdate", "run", "--token", custom_token]
                if custom_token
                else [str(bin_path), "tunnel", "--no-autoupdate", "--url", local_target]
            )
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
            with self._lock:
                self._proc = proc
            if proc.stdout:
                threading.Thread(target=self._reader_loop, args=(proc.stdout,), daemon=True).start()
            if proc.stderr:
                threading.Thread(target=self._reader_loop, args=(proc.stderr,), daemon=True).start()
            threading.Thread(target=self._watch_exit, args=(proc,), daemon=True).start()

            deadline = time.time() + 18.0
            while time.time() < deadline:
                with self._lock:
                    if self.status == "ACTIVE" and self.public_url:
                        return {"success": True, "status": "ACTIVE", "publicUrl": self.public_url}
                    if self.status == "ERROR":
                        return {"success": False, "status": "ERROR", "publicUrl": None, "error": self.last_error}
                if proc.poll() is not None:
                    break
                time.sleep(0.25)

            with self._lock:
                if self.public_url:
                    return {"success": True, "status": self.status, "publicUrl": self.public_url}
                return {
                    "success": False,
                    "status": self.status,
                    "publicUrl": None,
                    "error": self.last_error or "Đang kết nối Cloudflare Tunnel, vui lòng chờ thêm vài giây hoặc kiểm tra mạng.",
                }
        except Exception as exc:
            with self._lock:
                self.status = "ERROR"
                self.last_error = str(exc)
                self._push_log(f"LỖI: {exc}")
                return {"success": False, "status": "ERROR", "publicUrl": None, "error": self.last_error}

    def stop_tunnel(self) -> dict[str, Any]:
        with self._lock:
            proc = self._proc
            self._proc = None
            self.status = "STOPPED"
            self.public_url = None
            self.started_at = None
            self.last_error = None

        if proc is not None and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    proc.terminate()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return {"success": True, "status": "STOPPED"}

    def get_status(self, port: int | None = None) -> dict[str, Any]:
        use_port = int(port or self.active_port or 8000)
        primary_ip, lan_urls = get_lan_addresses(use_port)
        has_token = bool(str(os.environ.get("CLOUDFLARE_TUNNEL_TOKEN") or "").strip())
        with self._lock:
            if port:
                self.active_port = use_port
            return {
                "lanIp": primary_ip,
                "lanUrls": lan_urls,
                "localUrl": f"http://localhost:{use_port}",
                "port": use_port,
                "tunnel": {
                    "status": self.status,
                    "publicUrl": self.public_url,
                    "tunnelType": "NAMED_TUNNEL" if has_token else "QUICK_TUNNEL",
                    "startedAt": self.started_at,
                    "pid": self._proc.pid if (self._proc and self._proc.poll() is None) else None,
                    "error": self.last_error,
                    "recentLogs": list(self.recent_logs),
                },
            }


tunnel_service = TunnelService()
