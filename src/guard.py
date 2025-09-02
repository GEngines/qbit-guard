#!/usr/bin/env python3
"""
guard.py

Guard for qBittorrent 5.x:

Flow (on torrent ADDED):
  1) Stop torrent immediately (no payload).
  2) PRE-AIR gate (Sonarr + optional TVmaze/TheTVDB cross-check).
     - If pre-air BLOCK: blocklist in Sonarr (dedup + retry + queue failover), delete from qB.
  3) If pre-air ALLOW (or not applicable): fetch metadata/file list (start -> wait -> stop),
     then Extension Policy + ISO/BDMV cleaner:
       - If policy/ISO says delete (no keepable video, all files disallowed, pure disc images, etc.):
           blocklist in Sonarr/Radarr as applicable, delete.
       - Else: start torrent for real.

Configurable via environment variables and optional /config/extensions.json.
All logs go to stdout (container logs). Pure stdlib.
"""

from __future__ import annotations
import os, sys, re, json, ssl, time, datetime, logging
import http.cookiejar as cookiejar
import urllib.parse as uparse
import urllib.request as ureq
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Set
from version import VERSION
# --------------------------- Logging ---------------------------

# Add custom DETAILED logging level (between INFO=20 and DEBUG=10)
DETAILED_LEVEL = 15
logging.addLevelName(DETAILED_LEVEL, "DETAILED")

def detailed(self, message, *args, **kwargs):
    """Log message with DETAILED level."""
    if self.isEnabledFor(DETAILED_LEVEL):
        self._log(DETAILED_LEVEL, message, args, **kwargs)

logging.Logger.detailed = detailed

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# Map DETAILED to our custom level
level_value = DETAILED_LEVEL if LOG_LEVEL == "DETAILED" else getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=level_value,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("qbit-guard")
log.info(f"qbit-guard starting - version: {VERSION}")

# --------------------------- Helpers (extensions) ---------------------------

def _split_exts(s: str) -> Set[str]:
    """Parse comma/space/semicolon-separated extensions; returns naked, lowercase extensions (no dots)."""
    if not s:
        return set()
    parts = re.split(r"[,\s;]+", s.strip())
    return {p.lower().lstrip(".") for p in parts if p}

def _ext_of(path: str) -> str:
    base = os.path.basename(path or "")
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def _generate_detailed_extension_summary(disallowed_files: List[Dict[str, Any]], max_examples: int = 5) -> str:
    """Generate detailed summary of blocked extensions with counts and examples."""
    if not disallowed_files:
        return ""
    
    # Group files by extension
    ext_groups = {}
    for file_info in disallowed_files:
        filename = file_info.get("name", "")
        ext = _ext_of(filename)
        if ext not in ext_groups:
            ext_groups[ext] = []
        ext_groups[ext].append(filename)
    
    # Sort by count (descending) then by extension name
    sorted_exts = sorted(ext_groups.items(), key=lambda x: (-len(x[1]), x[0]))
    
    summary_parts = []
    for ext, filenames in sorted_exts:
        count = len(filenames)
        ext_display = f".{ext}" if ext else "(no extension)"
        
        # Show up to max_examples filenames for this extension
        examples = filenames[:max_examples]
        examples_str = ", ".join(f'"{os.path.basename(f)}"' for f in examples)
        
        if count > max_examples:
            examples_str += f" (+{count - max_examples} more)"
        
        summary_parts.append(f"{ext_display}: {count} file{'s' if count != 1 else ''} ({examples_str})")
    
    return "; ".join(summary_parts)


# --------------------------- Config ---------------------------

# Canonical sets
DISC_IMAGE_EXTS   = _split_exts("iso, img, mdf, nrg, cue, bin")
RISKY_EXEC_EXTS   = _split_exts("exe, bat, cmd, sh, ps1, msi, dmg, apk, jar, com, scr, vbs, vb, lnk, reg")
ARCHIVE_EXTS      = _split_exts("zip, rar, 7z, tar, gz, bz2, xz, zst")

DEFAULT_ALLOWED_EXTS = _split_exts("""
mkv, mp4, m4v, mov, webm, avi, m2ts, ts,
srt, ass, ssa, sub, idx, sup,
flac, mka, mp3, aac, ac3, eac3, dts, opus,
nfo, txt, jpg, jpeg, png, webp
""")

# Default blocked = disc images ∪ risky executables ∪ archives
DEFAULT_BLOCKED_EXTS = set().union(DISC_IMAGE_EXTS, RISKY_EXEC_EXTS, ARCHIVE_EXTS)

@dataclass
class Config:
    """Holds all configuration derived from environment variables."""
    # qB
    qbit_host: str = os.getenv("QBIT_HOST", "http://127.0.0.1:8080").rstrip("/")
    qbit_user: str = os.getenv("QBIT_USER", "admin")
    qbit_pass: str = os.getenv("QBIT_PASS", "adminadmin")
    allowed_categories: Set[str] = frozenset(
        c.strip().lower() for c in os.getenv("QBIT_ALLOWED_CATEGORIES", "tv-sonarr,radarr").split(",") if c.strip()
    )
    ignore_tls: bool = os.getenv("QBIT_IGNORE_TLS", "0") == "1"
    dry_run: bool = os.getenv("QBIT_DRY_RUN", "0") == "1"
    delete_files: bool = os.getenv("QBIT_DELETE_FILES", "true").lower() in ("1","true","yes")
    user_agent: str = os.getenv("USER_AGENT", "qbit-guard/2.0")

    # Pre-air (Sonarr)
    enable_preair: bool = os.getenv("ENABLE_PREAIR_CHECK", "1") == "1"
    sonarr_url: str = (os.getenv("SONARR_URL", "http://127.0.0.1:8989") or "").rstrip("/")
    sonarr_apikey: str = os.getenv("SONARR_APIKEY", "")
    sonarr_categories: Set[str] = frozenset(
        c.strip().lower() for c in os.getenv("SONARR_CATEGORIES", "tv-sonarr").split(",") if c.strip()
    )
    early_grace_hours: float = float(os.getenv("EARLY_GRACE_HOURS", "6"))
    early_hard_limit_hours: float = float(os.getenv("EARLY_HARD_LIMIT_HOURS", "72"))
    whitelist_overrides_hard_limit: bool = os.getenv("WHITELIST_OVERRIDES_HARD_LIMIT", "0") == "1"
    whitelist_groups: Set[str] = frozenset(
        g.strip().lower() for g in os.getenv("EARLY_WHITELIST_GROUPS", "").split(",") if g.strip()
    )
    whitelist_indexers: Set[str] = frozenset(
        i.strip().lower() for i in os.getenv("EARLY_WHITELIST_INDEXERS", "").split(",") if i.strip()
    )
    whitelist_trackers: Set[str] = frozenset(
        t.strip().lower() for t in os.getenv("EARLY_WHITELIST_TRACKERS", "").split(",") if t.strip()
    )
    resume_if_no_history: bool = os.getenv("RESUME_IF_NO_HISTORY", "1") == "1"
    sonarr_timeout_sec: int = int(os.getenv("SONARR_TIMEOUT_SEC", "45"))
    sonarr_retries: int = int(os.getenv("SONARR_RETRIES", "3"))



    # Internet cross-checks
    internet_check_provider: str = os.getenv("INTERNET_CHECK_PROVIDER", "tvmaze").strip().lower()  # off|tvmaze|tvdb|both
    tvmaze_base: str = os.getenv("TVMAZE_BASE", "https://api.tvmaze.com").rstrip("/")
    tvmaze_timeout: int = int(os.getenv("TVMAZE_TIMEOUT_SEC", "8"))
    tvdb_base: str = os.getenv("TVDB_BASE", "https://api4.thetvdb.com/v4").rstrip("/")
    tvdb_apikey: str = os.getenv("TVDB_APIKEY", "")
    tvdb_pin: str = os.getenv("TVDB_PIN", "")
    tvdb_language: str = os.getenv("TVDB_LANGUAGE", "eng")
    tvdb_order: str = os.getenv("TVDB_ORDER", "default").strip().lower()  # default|official
    tvdb_timeout: int = int(os.getenv("TVDB_TIMEOUT_SEC", "8"))
    tvdb_bearer: str = os.getenv("TVDB_BEARER", "")

    # ISO cleaner / metadata fetch
    enable_iso_check: bool = os.getenv("ENABLE_ISO_CHECK", "1") == "1"
    min_keepable_video_mb: float = float(os.getenv("MIN_KEEPABLE_VIDEO_MB", "50"))
    metadata_poll_interval: float = float(os.getenv("METADATA_POLL_INTERVAL", "1.5"))
    metadata_max_wait_sec: int = int(os.getenv("METADATA_MAX_WAIT_SEC", "0"))  # 0 = wait indefinitely
    metadata_download_budget_bytes: int = int(os.getenv("METADATA_DOWNLOAD_BUDGET_BYTES", "0"))  # 0 = no cap

    # Radarr (ISO deletes)
    radarr_url: str = (os.getenv("RADARR_URL", "http://127.0.0.1:7878") or "").rstrip("/")
    radarr_apikey: str = os.getenv("RADARR_APIKEY", "")
    radarr_categories: Set[str] = frozenset(
        c.strip().lower() for c in os.getenv("RADARR_CATEGORIES", "radarr").split(",") if c.strip()
    )
    radarr_timeout_sec: int = int(os.getenv("RADARR_TIMEOUT_SEC", "45"))
    radarr_retries: int = int(os.getenv("RADARR_RETRIES", "3"))

    # -------- Extension Policy (customizable) --------
    # Strategy:
    #   "block" (default): allow everything EXCEPT what's in blocked list
    #   "allow": allow ONLY what's in allowed list (everything else blocked)
    ext_strategy: str = os.getenv("GUARD_EXT_STRATEGY", "block").strip().lower()
    allowed_exts: Set[str] = None  # set in __post_init__
    blocked_exts: Set[str] = None  # set in __post_init__
    exts_file: str = os.getenv("GUARD_EXTS_FILE", "/config/extensions.json")
    # Enforcement:
    #   - If ALL files are disallowed by policy -> delete (default True)
    #   - If ANY file is disallowed -> delete (default False)
    ext_delete_if_all_blocked: bool = os.getenv("GUARD_EXT_DELETE_IF_ALL_BLOCKED", "1") in ("1","true","yes")
    ext_delete_if_any_blocked: bool = os.getenv("GUARD_EXT_DELETE_IF_ANY_BLOCKED", "0") in ("1","true","yes")
    ext_violation_tag: str = os.getenv("GUARD_EXT_VIOLATION_TAG", "trash:ext")
    
    # New option: uncheck blocked files instead of deleting the entire torrent (default True)
    uncheck_blocked_files: bool = os.getenv("GUARD_UNCHECK_BLOCKED_FILES", "1") in ("1","true","yes")

    # Disc-image set (used for ISO/BDMV detection); can be overridden
    disc_exts_env: str = os.getenv("GUARD_DISC_EXTS", "")  # e.g. "iso,img,mdf,toast"
    disc_exts: Set[str] = None  # set in __post_init__

    detailed_logging: bool = os.getenv("LOG_LEVEL", "INFO").upper() == "DETAILED"


    def __post_init__(self):
        # defaults
        self.allowed_exts = set(DEFAULT_ALLOWED_EXTS)
        self.blocked_exts = set(DEFAULT_BLOCKED_EXTS)

        # Optional JSON file: {"strategy": "...", "allowed": [...], "blocked": [...]}
        if os.path.isfile(self.exts_file):
            try:
                with open(self.exts_file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                strategy = str(data.get("strategy", self.ext_strategy)).strip().lower()
                if strategy in ("block","allow"):
                    self.ext_strategy = strategy
                allowed_val = data.get("allowed", [])
                blocked_val = data.get("blocked", [])
                if isinstance(allowed_val, list):
                    allowed = _split_exts(",".join(allowed_val))
                else:
                    allowed = _split_exts(str(allowed_val or ""))
                if isinstance(blocked_val, list):
                    blocked = _split_exts(",".join(blocked_val))
                else:
                    blocked = _split_exts(str(blocked_val or ""))
                if allowed:
                    self.allowed_exts = allowed
                if blocked:
                    self.blocked_exts = blocked
                log.info("Loaded extension policy from %s | strategy=%s | allowed=%d | blocked=%d",
                         self.exts_file, self.ext_strategy, len(self.allowed_exts), len(self.blocked_exts))
            except Exception as e:
                log.warning("Failed to read %s: %s (falling back to env/defaults)", self.exts_file, e)

        # Env overrides
        env_allowed = _split_exts(os.getenv("GUARD_ALLOWED_EXTS", ""))
        env_blocked = _split_exts(os.getenv("GUARD_BLOCKED_EXTS", ""))

        # Disc set: env override or default constant
        env_disc = _split_exts(self.disc_exts_env)
        self.disc_exts = env_disc if env_disc else set(DISC_IMAGE_EXTS)

        env_strategy = os.getenv("GUARD_EXT_STRATEGY", "").strip().lower()
        if env_allowed:
            self.allowed_exts = env_allowed
        if env_blocked:
            self.blocked_exts = env_blocked
        if env_strategy in ("block","allow"):
            self.ext_strategy = env_strategy

        log.info("Extension policy | strategy=%s | allowed=%d | blocked=%d | enforce(any=%s, all=%s, uncheck=%s)",
                 self.ext_strategy, len(self.allowed_exts), len(self.blocked_exts),
                 self.ext_delete_if_any_blocked, self.ext_delete_if_all_blocked, self.uncheck_blocked_files)

    # --- Policy helpers ---
    def is_ext_allowed(self, ext: str) -> bool:
        if not ext:
            return self.ext_strategy == "block"  # unknown ext allowed in block mode
        if ext in self.blocked_exts:
            return False
        if self.ext_strategy == "allow":
            return ext in self.allowed_exts
        return True  # block strategy

    def is_path_allowed(self, path: str) -> bool:
        return self.is_ext_allowed(_ext_of(path))


# --------------------------- HTTP ---------------------------

class HttpClient:
    """Small urllib wrapper with cookie jar, TLS toggle, and defaults."""
    def __init__(self, ignore_tls: bool, user_agent: str):
        self.cj = cookiejar.CookieJar()
        if ignore_tls:
            ctx = ssl._create_unverified_context()
            self.opener = ureq.build_opener(ureq.HTTPCookieProcessor(self.cj),
                                            ureq.HTTPSHandler(context=ctx),
                                            ureq.HTTPHandler())
        else:
            self.opener = ureq.build_opener(ureq.HTTPCookieProcessor(self.cj))
        self.user_agent = user_agent

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> bytes:
        h = {"User-Agent": self.user_agent}
        if headers: h.update(headers)
        req = ureq.Request(url, headers=h)
        with self.opener.open(req, timeout=timeout) as r:
            return r.read()

    def post_bytes(self, url: str, payload: bytes, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> bytes:
        h = {"User-Agent": self.user_agent}
        if headers: h.update(headers)
        req = ureq.Request(url, data=payload, headers=h)
        with self.opener.open(req, timeout=timeout) as r:
            return r.read()

    def post_form(self, url: str, data: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> bytes:
        payload = uparse.urlencode(data or {}).encode()
        return self.post_bytes(url, payload, headers, timeout)

    def post_json(self, url: str, obj: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> bytes:
        payload = json.dumps(obj or {}).encode()
        h = {"Content-Type": "application/json"}
        if headers: h.update(headers)
        return self.post_bytes(url, payload, h, timeout)

    def delete(self, url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> bytes:
        h = {"User-Agent": self.user_agent}
        if headers: h.update(headers)
        req = ureq.Request(url, headers=h, method="DELETE")
        with self.opener.open(req, timeout=timeout) as r:
            return r.read()


# --------------------------- qBittorrent ---------------------------

class QbitClient:
    """qBittorrent Web API client with 5.x start/stop and 4.x pause/resume fallback."""
    def __init__(self, cfg: Config, http: HttpClient):
        self.cfg = cfg
        self.http = http

    def _url(self, path: str) -> str:
        return f"{self.cfg.qbit_host}{path}"

    def login(self) -> None:
        """Authenticate with qBittorrent."""
        # NOTE: If you hit 403s, add CSRF headers in HttpClient (Referer/Origin) or adjust qB settings.
        self.http.post_form(self._url("/api/v2/auth/login"),
                            {"username": self.cfg.qbit_user, "password": self.cfg.qbit_pass})
        log.info("qB: login OK")

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(path)
        if params: url += "?" + uparse.urlencode(params, doseq=True)
        raw = self.http.get(url)
        return None if not raw else json.loads(raw.decode("utf-8"))

    def post(self, path: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.http.post_form(self._url(path), data or {})

    def start(self, h: str) -> None:
        """Start torrent, trying /start then /resume."""
        for p in ("/api/v2/torrents/start", "/api/v2/torrents/resume"):
            try:
                self.post(p, {"hashes": h}); return
            except Exception:
                continue
        log.warning("qB: could not start/resume %s", h)

    def stop(self, h: str) -> None:
        """Stop torrent, trying /stop then /pause."""
        for p in ("/api/v2/torrents/stop", "/api/v2/torrents/pause"):
            try:
                self.post(p, {"hashes": h}); return
            except Exception:
                continue
        log.warning("qB: could not stop/pause %s", h)

    def delete(self, h: str, delete_files: bool) -> None:
        self.post("/api/v2/torrents/delete", {"hashes": h, "deleteFiles": "true" if delete_files else "false"})

    def reannounce(self, h: str) -> None:
        try:
            self.post("/api/v2/torrents/reannounce", {"hashes": h})
        except Exception:
            pass

    def add_tags(self, h: str, tags: str) -> None:
        try:
            self.post("/api/v2/torrents/addTags", {"hashes": h, "tags": tags})
        except Exception:
            pass

    def info(self, h: str) -> Optional[Dict[str, Any]]:
        arr = self.get_json("/api/v2/torrents/info", {"hashes": h}) or []
        return arr[0] if arr else None

    def files(self, h: str) -> List[Dict[str, Any]]:
        return self.get_json("/api/v2/torrents/files", {"hash": h}) or []

    def trackers(self, h: str) -> List[Dict[str, Any]]:
        return self.get_json("/api/v2/torrents/trackers", {"hash": h}) or []
    
    def set_file_priority(self, h: str, file_ids: List[int], priority: int) -> None:
        """Set priority for specific files in a torrent. Priority 0 = don't download, 1 = normal."""
        try:
            id_str = "|".join(str(i) for i in file_ids)
            self.post("/api/v2/torrents/filePrio", {"hash": h, "id": id_str, "priority": str(priority)})
        except Exception as e:
            log.warning("qB: could not set file priority for %s: %s", h, e)


# --------------------------- Sonarr / Radarr ---------------------------

class BaseArr:
    """Shared utilities for Sonarr/Radarr (v3 APIs)."""
    def __init__(self, base_url: str, api_key: str, http: HttpClient, timeout: int, retries: int, name: str):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.http = http
        self.timeout = timeout
        self.retries = retries
        self.name = name

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.key)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base}/api/v3{path}"
        if params: url += "?" + uparse.urlencode(params, doseq=True)
        raw = self.http.get(url, headers={"X-Api-Key": self.key}, timeout=self.timeout)
        return None if not raw else json.loads(raw.decode("utf-8"))

    def _post_empty(self, path: str) -> None:
        url = f"{self.base}/api/v3{path}"
        last = None
        for a in range(self.retries):
            try:
                self.http.post_bytes(url, b"", headers={"X-Api-Key": self.key, "Content-Type": "application/json", "Content-Length": "0"}, timeout=self.timeout)
                return
            except Exception as e:
                last = e
                time.sleep(min(2**a, 8))
        raise last

    def _delete(self, path: str, query: Dict[str, Any]) -> None:
        url = f"{self.base}/api/v3{path}"
        if query: url += "?" + uparse.urlencode(query, doseq=True)
        self.http.delete(url, headers={"X-Api-Key": self.key}, timeout=self.timeout)

    def history_for_download(self, download_id: str) -> List[Dict[str, Any]]:
        """Return history rows for a given downloadId (with fallback page scan)."""
        try:
            obj = self._get("/history", {"downloadId": download_id})
            recs = obj.get("records", obj) if isinstance(obj, dict) else obj
            if recs: return recs
        except Exception:
            pass
        try:
            obj = self._get("/history", {"page":1,"pageSize":200,"sortKey":"date","sortDirection":"descending"})
            recs = obj.get("records", []) if isinstance(obj, dict) else (obj or [])
            return [r for r in recs if (r.get("downloadId","").lower() == download_id.lower())]
        except Exception:
            return []

    def queue_ids_for_download(self, download_id: str) -> List[int]:
        """Return queue row IDs for a given downloadId (used for queue failover blocklist)."""
        try:
            obj = self._get("/queue", {"page":1,"pageSize":500,"sortKey":"timeleft","sortDirection":"ascending"})
            recs = obj.get("records", obj) if isinstance(obj, dict) else obj
            return [int(r["id"]) for r in (recs or []) if r.get("id") and r.get("downloadId","").lower()==download_id.lower()]
        except Exception:
            return []

    @staticmethod
    def dedup_grabbed_ids(history_rows: Sequence[Dict[str, Any]]) -> List[int]:
        """Pick at most one ID per unique source/release title, newest first."""
        grabbed = []
        for r in history_rows:
            et = (r.get("eventType") or "").lower()
            d = r.get("data") or {}
            if et == "grabbed" or d.get("sourceTitle") or d.get("releaseTitle"):
                grabbed.append(r)
        grabbed.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
        seen, ids = set(), []
        for r in grabbed:
            d = r.get("data") or {}
            title = (d.get("sourceTitle") or d.get("releaseTitle") or "").strip().lower()
            key = title or ("grab-" + (r.get("downloadId") or ""))
            if key and key not in seen and r.get("id"):
                seen.add(key)
                ids.append(int(r["id"]))
        return ids

class SonarrClient(BaseArr):
    """Sonarr v3 client with blocklist helpers."""
    def __init__(self, cfg: Config, http: HttpClient):
        super().__init__(cfg.sonarr_url, cfg.sonarr_apikey, http, cfg.sonarr_timeout_sec, cfg.sonarr_retries, "Sonarr")

    def blocklist_download(self, download_id: str) -> None:
        """Blocklist a release by failing one grabbed history row; falls back to queue removal with blocklist=true."""
        if not self.enabled:
            return
        rows = self.history_for_download(download_id)
        ids = self.dedup_grabbed_ids(rows)
        if ids:
            try:
                self._post_empty(f"/history/failed/{ids[0]}")
                log.info("Sonarr: blocklisted via history id=%s", ids[0])
                return
            except Exception as e:
                log.warning("Sonarr: history/failed error (%s); trying queue failover", e)
        qids = self.queue_ids_for_download(download_id)
        if qids:
            try:
                self._delete(f"/queue/{qids[0]}", {"blocklist":"true","removeFromClient":"false"})
                log.info("Sonarr: blocklisted via queue id=%s", qids[0])
            except Exception as e:
                log.error("Sonarr: queue failover error: %s", e)
        else:
            log.info("Sonarr: nothing to fail or in queue for downloadId=%s", download_id)

    # Lightweight series/episode fetch (for pre-air)
    def episode(self, episode_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/episode/{episode_id}")
        except Exception as e:
            log.warning("Sonarr: episode %s fetch failed: %s", episode_id, e)
            return None

    def series(self, series_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/series/{series_id}")
        except Exception as e:
            log.warning("Sonarr: series %s fetch failed: %s", series_id, e)
            return None

class RadarrClient(BaseArr):
    """Radarr v3 client with blocklist helpers (used on ISO deletes)."""
    def __init__(self, cfg: Config, http: HttpClient):
        super().__init__(cfg.radarr_url, cfg.radarr_apikey, http, cfg.radarr_timeout_sec, cfg.radarr_retries, "Radarr")

    def blocklist_download(self, download_id: str) -> None:
        """Blocklist a release by failing one grabbed history row; falls back to queue removal with blocklist=true."""
        if not self.enabled:
            return
        rows = self.history_for_download(download_id)
        ids = self.dedup_grabbed_ids(rows)
        if ids:
            try:
                self._post_empty(f"/history/failed/{ids[0]}")
                log.info("Radarr: blocklisted via history id=%s", ids[0])
                return
            except Exception as e:
                log.warning("Radarr: history/failed error (%s); trying queue failover", e)
        qids = self.queue_ids_for_download(download_id)
        if qids:
            try:
                self._delete(f"/queue/{qids[0]}", {"blocklist":"true","removeFromClient":"false"})
                log.info("Radarr: blocklisted via queue id=%s", qids[0])
            except Exception as e:
                log.error("Radarr: queue failover error: %s", e)
        else:
            log.info("Radarr: nothing to fail or in queue for downloadId=%s", download_id)

    # Lightweight movie fetch (for pre-air)
    def movie(self, movie_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._get(f"/movie/{movie_id}")
        except Exception as e:
            log.warning("Radarr: movie %s fetch failed: %s", movie_id, e)
            return None


# --------------------------- Utilities ---------------------------

def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)

def parse_iso_utc(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s: return None
    if s.endswith("Z"): s = s[:-1] + "+00:00"
    try: return datetime.datetime.fromisoformat(s)
    except Exception: return None

def hours_until(dt: datetime.datetime) -> float:
    return (dt - now_utc()).total_seconds() / 3600.0

def domain_from_url(u: str) -> str:
    try:
        s = u.split("://",1)[-1]
        host = s.split("/",1)[0].lower()
        return host.split(":")[0]
    except Exception:
        return u.lower()


# --------------------------- Internet Airdates ---------------------------

class InternetDates:
    """Optional TVmaze/TheTVDB cross-check to supplement Sonarr's airDateUtc."""
    def __init__(self, cfg: Config, http: HttpClient, sonarr: SonarrClient, radarr: RadarrClient):
        self.cfg = cfg
        self.http = http
        self.sonarr = sonarr
        self.radarr = radarr
        self._tvdb_token = cfg.tvdb_bearer.strip()

    def _get(self, url: str, timeout: int) -> Any:
        raw = self.http.get(url, timeout=timeout)
        return None if not raw else json.loads(raw.decode("utf-8"))

    # TVmaze
    def tvmaze_show_id(self, series: Dict[str, Any]) -> Optional[int]:
        tvdb = series.get("tvdbId") or None
        imdb = series.get("imdbId") or None
        title = series.get("title") or None
        try:
            if tvdb:
                j = self._get(f"{self.cfg.tvmaze_base}/lookup/shows?thetvdb={int(tvdb)}", self.cfg.tvmaze_timeout)
                if isinstance(j, dict) and j.get("id"): return int(j["id"])
            if imdb and not str(imdb).startswith("tt"):
                imdb = "tt" + str(imdb)
            if imdb:
                j = self._get(f"{self.cfg.tvmaze_base}/lookup/shows?imdb={uparse.quote(str(imdb))}", self.cfg.tvmaze_timeout)
                if isinstance(j, dict) and j.get("id"): return int(j["id"])
            if title:
                j = self._get(f"{self.cfg.tvmaze_base}/singlesearch/shows?q={uparse.quote(title)}", self.cfg.tvmaze_timeout)
                if isinstance(j, dict) and j.get("id"): return int(j["id"])
        except Exception:
            return None
        return None

    def tvmaze_episode_airstamp(self, tm_id: int, season: int, number: int) -> Optional[datetime.datetime]:
        try:
            j = self._get(f"{self.cfg.tvmaze_base}/shows/{tm_id}/episodebynumber?season={season}&number={number}", self.cfg.tvmaze_timeout)
            s = j.get("airstamp") if isinstance(j, dict) else None
            return parse_iso_utc(s) if s else None
        except Exception:
            return None

    # TVDB
    def _tvdb_login(self) -> Optional[str]:
        if self._tvdb_token:
            return self._tvdb_token
        if not self.cfg.tvdb_apikey:
            return None
        body = {"apikey": self.cfg.tvdb_apikey}
        if self.cfg.tvdb_pin: body["pin"] = self.cfg.tvdb_pin
        try:
            r = self.http.post_json(f"{self.cfg.tvdb_base}/login", obj=body, timeout=self.cfg.tvdb_timeout)
            j = json.loads(r.decode("utf-8")) if r else {}
            token = j.get("data", {}).get("token") or j.get("token")
            if token:
                self._tvdb_token = token
                return token
        except Exception:
            return None
        return None

    def tvdb_episode_airstamp(self, tvdb_series_id: int, season: int, number: int) -> Optional[datetime.datetime]:
        token = self._tvdb_login()
        if not token: return None
        order = self.cfg.tvdb_order if self.cfg.tvdb_order in ("default","official") else "default"
        lang = self.cfg.tvdb_language or "eng"
        try:
            # page through a few pages
            for page in range(0, 10):
                url = f"{self.cfg.tvdb_base}/series/{tvdb_series_id}/episodes/{order}/{lang}?page={page}"
                raw = self.http.get(url, headers={"Authorization":"Bearer "+token}, timeout=self.cfg.tvdb_timeout)
                j = json.loads(raw.decode("utf-8")) if raw else {}
                for ep in (j.get("data") or []):
                    sn = ep.get("seasonNumber"); en = ep.get("number")
                    if sn == season and en == number:
                        s = ep.get("airstamp") or ep.get("firstAired") or ep.get("airDate") or ep.get("date")
                        if not s: return None
                        if isinstance(s, str) and s.endswith("Z"): s = s[:-1] + "+00:00"
                        if isinstance(s, str) and len(s) == 10 and s[4] == "-" and s[7] == "-":
                            s += "T00:00:00+00:00"
                        try: return datetime.datetime.fromisoformat(s)
                        except Exception: return None
                if not j.get("data"): break
        except Exception:
            return None
        return None

    # Movie lookups
    def tvmaze_movie_release_date(self, movie: Dict[str, Any]) -> Optional[datetime.datetime]:
        """Look up movie release date via TVmaze API using IMDB ID if available."""
        imdb = movie.get("imdbId") or None
        title = movie.get("title") or None
        if not imdb and not title:
            return None
            
        try:
            # Try IMDB lookup first
            if imdb and not str(imdb).startswith("tt"):
                imdb = "tt" + str(imdb)
            if imdb:
                # TVmaze doesn't have great movie support, but we can try
                # Note: TVmaze is primarily for TV shows, movie support is limited
                pass
                
            # For now, TVmaze movie support is limited, so we return None
            # In a real implementation, you might want to use a movie-specific API
            return None
        except Exception:
            return None

    def tvdb_movie_release_date(self, movie: Dict[str, Any]) -> Optional[datetime.datetime]:
        """Look up movie release date via TVDB API using movie ID."""
        tvdb_id = movie.get("tvdbId") or None
        if not tvdb_id:
            return None
            
        token = self._tvdb_login()
        if not token:
            return None
            
        try:
            # TVDB v4 movie endpoint
            url = f"{self.cfg.tvdb_base}/movies/{int(tvdb_id)}"
            raw = self.http.get(url, headers={"Authorization": "Bearer " + token}, timeout=self.cfg.tvdb_timeout)
            j = json.loads(raw.decode("utf-8")) if raw else {}
            
            movie_data = j.get("data") if isinstance(j, dict) else {}
            if movie_data:
                # Check various possible date fields
                release_date = (movie_data.get("releaseDate") or 
                              movie_data.get("firstAired") or 
                              movie_data.get("year"))
                
                if release_date:
                    # Handle different date formats
                    if isinstance(release_date, str):
                        if release_date.endswith("Z"):
                            release_date = release_date[:-1] + "+00:00"
                        if len(release_date) == 4 and release_date.isdigit():
                            # Just a year, assume January 1st
                            release_date += "-01-01T00:00:00+00:00"
                        elif len(release_date) == 10 and release_date[4] == "-" and release_date[7] == "-":
                            release_date += "T00:00:00+00:00"
                        
                        try:
                            return datetime.datetime.fromisoformat(release_date)
                        except Exception:
                            pass
                            
        except Exception:
            pass
            
        return None


# --------------------------- Pre-Air Gate ---------------------------

class PreAirGate:
    """Implements the pre-air decision logic using Sonarr (and optional internet cross-checks)."""
    def __init__(self, cfg: Config, sonarr: SonarrClient, internet: InternetDates):
        self.cfg = cfg
        self.sonarr = sonarr
        self.internet = internet

    def should_apply(self, category_norm: str) -> bool:
        return self.cfg.enable_preair and self.sonarr.enabled and (category_norm in self.cfg.sonarr_categories)

    def decision(self, qbit: QbitClient, h: str, tracker_hosts: Set[str]) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Return (allow, reason, history_rows). 'allow' True means proceed to file check/start.
        'reason' is textual for logs; 'history_rows' used for potential blocklist if blocked.
        """
        # Give Sonarr a moment to write "Grabbed" history
        time.sleep(0.8)

        # Fetch history for this download
        hist = []
        for _ in range(5):
            hist = self.sonarr.history_for_download(h)
            if hist: break
            time.sleep(0.8)

        episodes = {int(r["episodeId"]) for r in hist if r.get("episodeId")}
        rel_groups, indexers = set(), set()
        for r in hist:
            d = r.get("data") or {}
            if d.get("releaseGroup"): rel_groups.add(str(d["releaseGroup"]).lower())
            if d.get("indexer"): indexers.add(str(d["indexer"]).lower())

        if not episodes:
            msg = "No Sonarr history."
            if self.cfg.resume_if_no_history:
                log.info("Pre-air: %s Proceeding to file check.", msg)
                return True, "no-history", hist
            log.info("Pre-air: %s Keeping stopped.", msg)
            return False, "no-history", hist

        # Load episodes and compute future hours from Sonarr
        future_hours: List[float] = []
        series_cache: Dict[int, Dict[str, Any]] = {}
        for eid in episodes:
            ep = self.sonarr.episode(eid) or {}
            air = parse_iso_utc(ep.get("airDateUtc"))
            if air and air > now_utc():
                future_hours.append(hours_until(air))
            elif air is None:
                future_hours.append(99999.0)

        all_aired = len(future_hours) == 0
        max_future = max(future_hours) if future_hours else 0.0

        # Internet cross-checks
        if not all_aired and self.cfg.internet_check_provider in ("tvmaze","both"):
            inet_future = []
            for eid in episodes:
                ep = self.sonarr.episode(eid) or {}
                sid = ep.get("seriesId")
                if not sid:
                    inet_future.append(99999.0); continue
                if sid not in series_cache:
                    series_cache[sid] = self.sonarr.series(sid) or {}
                series = series_cache[sid]
                tm_id = self.internet.tvmaze_show_id(series)
                season = ep.get("seasonNumber"); number = ep.get("episodeNumber")
                if tm_id and season is not None and number is not None:
                    dt = self.internet.tvmaze_episode_airstamp(tm_id, int(season), int(number))
                    if dt and dt > now_utc(): inet_future.append(hours_until(dt))
                    elif dt is None: inet_future.append(99999.0)
            if inet_future:
                m = max(inet_future)
                max_future = min(max_future, m) if max_future else m
                all_aired = False

        if not all_aired and self.cfg.internet_check_provider in ("tvdb","both"):
            inet_future = []
            for eid in episodes:
                ep = self.sonarr.episode(eid) or {}
                sid = ep.get("seriesId")
                if not sid:
                    inet_future.append(99999.0); continue
                if sid not in series_cache:
                    series_cache[sid] = self.sonarr.series(sid) or {}
                series = series_cache[sid]
                tvdb_series_id = series.get("tvdbId")
                season = ep.get("seasonNumber"); number = ep.get("episodeNumber")
                if tvdb_series_id and season is not None and number is not None:
                    dt = self.internet.tvdb_episode_airstamp(int(tvdb_series_id), int(season), int(number))
                    if dt and dt > now_utc(): inet_future.append(hours_until(dt))
                    elif dt is None: inet_future.append(99999.0)
            if inet_future:
                m = max(inet_future)
                max_future = min(max_future, m) if max_future else m
                all_aired = False

        # Whitelist/grace/hard-cap decisions
        allow_by_grace = (not all_aired) and (max_future <= self.cfg.early_grace_hours)
        allow_by_group = bool(self.cfg.whitelist_groups and (rel_groups & self.cfg.whitelist_groups))
        allow_by_indexer = bool(self.cfg.whitelist_indexers and (indexers & self.cfg.whitelist_indexers))
        allow_by_tracker = bool(self.cfg.whitelist_trackers and any(any(w in h for w in self.cfg.whitelist_trackers) for h in tracker_hosts))
        whitelist_allowed = allow_by_group or allow_by_indexer or allow_by_tracker

        if (not all_aired) and (max_future > self.cfg.early_hard_limit_hours) and (not (self.cfg.whitelist_overrides_hard_limit and whitelist_allowed)):
            log.info("Pre-air: BLOCK_CAP max_future=%.2f h", max_future)
            return False, "cap", hist

        if all_aired or allow_by_grace or whitelist_allowed:
            reason = "+".join([x for x,ok in [("aired",all_aired),("grace",allow_by_grace),("whitelist",whitelist_allowed)] if ok]) or "allow"
            log.info("Pre-air: ALLOW (%s)", reason)
            return True, reason, hist

        log.info("Pre-air: BLOCK (max_future=%.2f h)", max_future)
        return False, "block", hist


# --------------------------- Pre-Air Movie Gate ---------------------------

class PreAirMovieGate:
    """Implements the pre-air decision logic using Radarr (and optional internet cross-checks) for movies."""
    def __init__(self, cfg: Config, radarr: RadarrClient, internet: InternetDates):
        self.cfg = cfg
        self.radarr = radarr
        self.internet = internet

    def should_apply(self, category_norm: str) -> bool:
        return self.cfg.enable_preair and self.radarr.enabled and (category_norm in self.cfg.radarr_categories)

    def decision(self, qbit: QbitClient, h: str, tracker_hosts: Set[str]) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Return (allow, reason, history_rows). 'allow' True means proceed to file check/start.
        'reason' is textual for logs; 'history_rows' used for potential blocklist if blocked.
        """
        # Give Radarr a moment to write "Grabbed" history
        time.sleep(0.8)

        # Fetch history for this download
        hist = []
        for _ in range(5):
            hist = self.radarr.history_for_download(h)
            if hist: break
            time.sleep(0.8)

        movies = {int(r["movieId"]) for r in hist if r.get("movieId")}
        rel_groups, indexers = set(), set()
        for r in hist:
            d = r.get("data") or {}
            if d.get("releaseGroup"): rel_groups.add(str(d["releaseGroup"]).lower())
            if d.get("indexer"): indexers.add(str(d["indexer"]).lower())

        if not movies:
            msg = "No Radarr history."
            if self.cfg.resume_if_no_history:
                log.info("Pre-air Movie: %s Proceeding to file check.", msg)
                return True, "no-history", hist
            log.info("Pre-air Movie: %s Keeping stopped.", msg)
            return False, "no-history", hist

        # Load movies and compute future hours from Radarr
        future_hours: List[float] = []
        movie_cache: Dict[int, Dict[str, Any]] = {}
        for mid in movies:
            movie = self.radarr.movie(mid) or {}
            movie_cache[mid] = movie
            
            # Check various release date fields that Radarr might use
            release_date = None
            for field in ["digitalRelease", "physicalRelease", "inCinemas", "releaseDate"]:
                date_str = movie.get(field)
                if date_str:
                    release_date = parse_iso_utc(date_str)
                    break
                    
            if release_date and release_date > now_utc():
                future_hours.append(hours_until(release_date))
            elif release_date is None:
                future_hours.append(99999.0)

        all_released = len(future_hours) == 0
        max_future = max(future_hours) if future_hours else 0.0

        # Internet cross-checks for movies
        if not all_released and self.cfg.internet_check_provider in ("tvdb","both"):
            inet_future = []
            for mid in movies:
                movie = movie_cache[mid]
                release_date = self.internet.tvdb_movie_release_date(movie)
                if release_date and release_date > now_utc():
                    inet_future.append(hours_until(release_date))
                elif release_date is None:
                    inet_future.append(99999.0)
                    
            if inet_future:
                m = max(inet_future)
                max_future = min(max_future, m) if max_future else m
                all_released = False

        # Whitelist/grace/hard-cap decisions (same logic as TV shows)
        allow_by_grace = (not all_released) and (max_future <= self.cfg.early_grace_hours)
        allow_by_group = bool(self.cfg.whitelist_groups and (rel_groups & self.cfg.whitelist_groups))
        allow_by_indexer = bool(self.cfg.whitelist_indexers and (indexers & self.cfg.whitelist_indexers))
        allow_by_tracker = bool(self.cfg.whitelist_trackers and any(any(w in h for w in self.cfg.whitelist_trackers) for h in tracker_hosts))
        whitelist_allowed = allow_by_group or allow_by_indexer or allow_by_tracker

        if (not all_released) and (max_future > self.cfg.early_hard_limit_hours) and (not (self.cfg.whitelist_overrides_hard_limit and whitelist_allowed)):
            log.info("Pre-air Movie: BLOCK_CAP max_future=%.2f h", max_future)
            return False, "cap", hist

        if all_released or allow_by_grace or whitelist_allowed:
            reason = "+".join([x for x,ok in [("released",all_released),("grace",allow_by_grace),("whitelist",whitelist_allowed)] if ok]) or "allow"
            log.info("Pre-air Movie: ALLOW (%s)", reason)
            return True, reason, hist

        log.info("Pre-air Movie: BLOCK (max_future=%.2f h)", max_future)
        return False, "block", hist


# --------------------------- Metadata Fetcher ---------------------------

class MetadataFetcher:
    """Starts torrent and waits until metadata (file list) is available, then stops again."""
    def __init__(self, cfg: Config, qbit: QbitClient):
        self.cfg = cfg
        self.qbit = qbit

    def fetch(self, torrent_hash: str) -> List[Dict[str, Any]]:
        """
        Wait until /api/v2/torrents/files is non-empty.
        No speed clamps here; we stop immediately once files appear.
        Optional: max wait and download budget guards.
        """
        # If already present, don't start it.
        files = self.qbit.files(torrent_hash) or []
        if files:
            return files

        self.qbit.start(torrent_hash)
        start_ts = time.time()
        ticks = 0
        base_downloaded = None

        try:
            while True:
                # Best-effort reannounce every ~15s to hasten magnet resolution
                if ticks % max(1, int(15.0 / max(self.cfg.metadata_poll_interval, 0.5))) == 0:
                    self.qbit.reannounce(torrent_hash)

                files = self.qbit.files(torrent_hash) or []
                if files:
                    break

                # State / downloaded budget guard
                info = self.qbit.info(torrent_hash) or {}
                if info:
                    state = (info.get("state") or "").lower()
                    if state in ("pauseddl","pausedup","stalleddl"):
                        self.qbit.start(torrent_hash)
                    cur_downloaded = int(info.get("downloaded_session") or info.get("downloaded") or 0)
                    if base_downloaded is None:
                        base_downloaded = cur_downloaded
                    delta = cur_downloaded - base_downloaded
                    if self.cfg.metadata_download_budget_bytes > 0 and delta > self.cfg.metadata_download_budget_bytes:
                        log.warning("Metadata wait exceeded budget (%s > %s); aborting wait.", delta, self.cfg.metadata_download_budget_bytes)
                        files = []
                        break

                if self.cfg.metadata_max_wait_sec > 0 and (time.time() - start_ts) >= self.cfg.metadata_max_wait_sec:
                    break

                time.sleep(self.cfg.metadata_poll_interval)
                ticks += 1
        finally:
            # Stop asap after metadata obtained (or on abort)
            self.qbit.stop(torrent_hash)

        return files or []


# --------------------------- ISO + Extension Policy Cleaner ---------------------------

class IsoCleaner:
    """
    Detects ISO/BDMV-only torrents and applies extension policy.
    - If pure disc images (ISO/BDMV) with no keepable video -> delete
    - If extension policy deems ALL files disallowed -> delete (configurable)
    - If SOME files disallowed -> log (optionally delete if ext_delete_if_any_blocked)
    """
    VIDEO_RE = re.compile(r'\.(mkv|mp4|m4v|avi|ts|m2ts|mov|webm)$', re.I)

    def __init__(self, cfg: Config, qbit: QbitClient, sonarr: SonarrClient, radarr: RadarrClient):
        self.cfg = cfg
        self.qbit = qbit
        self.sonarr = sonarr
        self.radarr = radarr
        self.min_bytes = int(cfg.min_keepable_video_mb * 1024 * 1024)

        # Build disc-image regex from a single source of truth
        disc_pat = r'\.(' + '|'.join(sorted(map(re.escape, self.cfg.disc_exts))) + r')$'
        self.disc_re = re.compile(disc_pat, re.I)

    def _is_disc_path(self, name: str) -> bool:
        n = (name or "").replace("\\","/").lower()
        return bool(self.disc_re.search(n) or "/bdmv/" in n or "/video_ts/" in n)

    def has_keepable_video(self, files: Sequence[Dict[str, Any]]) -> bool:
        for f in files:
            n = f.get("name","")
            sz = int(f.get("size",0))
            if self.VIDEO_RE.search(n) and sz >= self.min_bytes and self.cfg.is_path_allowed(n):
                return True
        return False

    def _blocklist_arr_if_applicable(self, category_norm: str, torrent_hash: str) -> None:
        if category_norm in self.cfg.sonarr_categories and self.sonarr.enabled:
            try: self.sonarr.blocklist_download(torrent_hash)
            except Exception as e: log.error("Sonarr blocklist error: %s", e)
        if category_norm in self.cfg.radarr_categories and self.radarr.enabled:
            try: self.radarr.blocklist_download(torrent_hash)
            except Exception as e: log.error("Radarr blocklist error: %s", e)

    def evaluate_and_act(self, torrent_hash: str, category_norm: str) -> bool:
        """
        Returns True if it deleted the torrent (ISO/BDMV-only or extension-policy violation), False otherwise.
        Will notify Sonarr/Radarr before deletion based on category.
        """
        all_files = self.qbit.files(torrent_hash) or []
        relevant = [f for f in all_files if int(f.get("size",0)) > 0]

        # ---- Extension policy analysis (before disc detection) ----
        disallowed = [f for f in relevant if not self.cfg.is_path_allowed(f.get("name",""))]
        if disallowed:
            total = len(relevant)
            bad = len(disallowed)
            allowed = [f for f in relevant if self.cfg.is_path_allowed(f.get("name",""))]
            good = len(allowed)
            sample = (disallowed[0].get("name","") if disallowed else "")
            
            # Standard info logging
            log.info("Ext policy: %d/%d file(s) disallowed. e.g., %s", bad, total, sample)
            
            # Enhanced detailed logging with extension breakdown
            if self.cfg.detailed_logging:
                detailed_summary = _generate_detailed_extension_summary(disallowed)
                log.detailed("Extension policy details: %s", detailed_summary)
            
            # Check if we should delete the entire torrent
            should_delete = (self.cfg.ext_delete_if_any_blocked or 
                           (self.cfg.ext_delete_if_all_blocked and bad == total))
            
            if should_delete:
                # Delete due to extension policy
                self.qbit.add_tags(torrent_hash, self.cfg.ext_violation_tag)
                self._blocklist_arr_if_applicable(category_norm, torrent_hash)
                if not self.cfg.dry_run:
                    try:
                        self.qbit.delete(torrent_hash, self.cfg.delete_files)
                        log.info("Removed torrent %s due to extension policy.", torrent_hash)
                    except Exception as e:
                        log.error("qB delete failed: %s", e)
                else:
                    log.info("DRY-RUN: would remove torrent %s due to extension policy.", torrent_hash)
                return True
            
            # If uncheck_blocked_files is enabled and we have some allowed files
            elif self.cfg.uncheck_blocked_files and good > 0:
                # Get file IDs for disallowed files (qBittorrent uses 0-based indexing)
                disallowed_ids = []
                for i, f in enumerate(all_files):
                    if not self.cfg.is_path_allowed(f.get("name","")) and int(f.get("size",0)) > 0:
                        disallowed_ids.append(i)
                
                if disallowed_ids:
                    log.info("Unchecking %d disallowed file(s), keeping %d allowed file(s)", bad, good)
                    if not self.cfg.dry_run:
                        try:
                            # Set priority to 0 (don't download) for disallowed files
                            self.qbit.set_file_priority(torrent_hash, disallowed_ids, 0)
                            # Add partial tag to indicate some files were unchecked
                            self.qbit.add_tags(torrent_hash, "guard:partial")
                            log.info("Unchecked %d file(s) from torrent %s due to extension policy.", 
                                   len(disallowed_ids), torrent_hash)
                        except Exception as e:
                            log.error("Failed to uncheck files: %s", e)
                    else:
                        log.info("DRY-RUN: would uncheck %d file(s) from torrent %s due to extension policy.", 
                               len(disallowed_ids), torrent_hash)

        # ---- Disc-image detection (ISO/BDMV) ----
        all_discish = (len(relevant) > 0) and all(self._is_disc_path(f.get("name","")) for f in relevant)
        keepable = self.has_keepable_video(relevant)

        if all_discish and not keepable:
            log.info("ISO cleaner: disc-image content detected (no keepable video).")
            self.qbit.add_tags(torrent_hash, "trash:iso")
            self._blocklist_arr_if_applicable(category_norm, torrent_hash)
            if not self.cfg.dry_run:
                try:
                    self.qbit.delete(torrent_hash, self.cfg.delete_files)
                    log.info("Removed torrent %s (ISO/BDMV-only).", torrent_hash)
                except Exception as e:
                    log.error("qB delete failed: %s", e)
            else:
                log.info("DRY-RUN: would remove torrent %s (ISO/BDMV-only).", torrent_hash)
            return True

        log.info("ISO/Ext check: keepable=%s, files=%d (disallowed=%d, action=%s).",
                 keepable, len(relevant), len(disallowed), 
                 "partial" if (disallowed and self.cfg.uncheck_blocked_files and len([f for f in relevant if self.cfg.is_path_allowed(f.get("name",""))]) > 0) else "passed")
        return False


# --------------------------- Orchestrator ---------------------------

class TorrentGuard:
    """Main orchestrator that wires qB, Sonarr/Radarr, pre-air, metadata, and ISO/Extension cleaner together."""
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = HttpClient(cfg.ignore_tls, cfg.user_agent)
        self.qbit = QbitClient(cfg, self.http)
        self.sonarr = SonarrClient(cfg, self.http)
        self.radarr = RadarrClient(cfg, self.http)
        self.internet = InternetDates(cfg, self.http, self.sonarr, self.radarr)
        self.preair = PreAirGate(cfg, self.sonarr, self.internet)
        self.preair_movie = PreAirMovieGate(cfg, self.radarr, self.internet)
        self.metadata = MetadataFetcher(cfg, self.qbit)
        self.iso = IsoCleaner(cfg, self.qbit, self.sonarr, self.radarr)

    def run(self, torrent_hash: str, passed_category: str) -> None:
        """Entry point for a single torrent hash."""
        # Login qB
        try:
            self.qbit.login()
        except Exception as e:
            log.error("qB login failed: %s", e)
            sys.exit(2)

        info = self.qbit.info(torrent_hash)
        if not info:
            log.info("No torrent found for hash; exiting.")
            return

        category = (passed_category or info.get("category") or "").strip()
        category_norm = category.lower()
        name = info.get("name") or ""
        log.info("Processing: hash=%s category='%s' name='%s'", torrent_hash, category, name)

        if category_norm not in self.cfg.allowed_categories:
            log.info("Category '%s' not in allowed list %s — skipping.", category, sorted(self.cfg.allowed_categories))
            return

        # Stop immediately and tag
        self.qbit.stop(torrent_hash)
        self.qbit.add_tags(torrent_hash, "guard:stopped")

        # Tracker hosts (for whitelist decisions)
        trackers = self.qbit.trackers(torrent_hash) or []
        tracker_hosts = {domain_from_url(t.get("url","")) for t in trackers if t.get("url")}

        # 1) PRE-AIR gate first (TV shows and movies)
        preair_applied = False
        
        # Check TV show pre-air gate
        tv_should_apply = self.preair.should_apply(category_norm)
        movie_should_apply = self.preair_movie.should_apply(category_norm)
        
        # Validate configuration: categories should not overlap between services when both are enabled
        if tv_should_apply and movie_should_apply:
            log.warning("Category '%s' matches both Sonarr (%s) and Radarr (%s) pre-air categories. "
                       "This may lead to unexpected behavior. Consider using distinct categories.",
                       category, sorted(self.cfg.sonarr_categories), sorted(self.cfg.radarr_categories))
        
        if tv_should_apply:
            preair_applied = True
            allow, reason, history_rows = self.preair.decision(self.qbit, torrent_hash, tracker_hosts)
            if not allow:
                if not self.cfg.dry_run:
                    try:
                        self.sonarr.blocklist_download(torrent_hash)
                    except Exception as e:
                        log.error("Sonarr blocklist error: %s", e)
                    self.qbit.add_tags(torrent_hash, "trash:preair")
                    try:
                        self.qbit.delete(torrent_hash, self.cfg.delete_files)
                        log.info("Pre-air TV: deleted torrent %s (reason=%s).", torrent_hash, reason)
                    except Exception as e:
                        log.error("qB delete failed: %s", e)
                else:
                    log.info("DRY-RUN: would delete torrent %s due to TV pre-air (reason=%s).", torrent_hash, reason)
                return
            else:
                log.info("Pre-air TV passed (reason=%s). Proceeding to file/ISO/ext check.", reason)
        
        # Check movie pre-air gate (independent of TV check)
        if movie_should_apply:
            preair_applied = True
            allow, reason, history_rows = self.preair_movie.decision(self.qbit, torrent_hash, tracker_hosts)
            if not allow:
                if not self.cfg.dry_run:
                    try:
                        self.radarr.blocklist_download(torrent_hash)
                    except Exception as e:
                        log.error("Radarr blocklist error: %s", e)
                    self.qbit.add_tags(torrent_hash, "trash:preair-movie")
                    try:
                        self.qbit.delete(torrent_hash, self.cfg.delete_files)
                        log.info("Pre-air Movie: deleted torrent %s (reason=%s).", torrent_hash, reason)
                    except Exception as e:
                        log.error("qB delete failed: %s", e)
                else:
                    log.info("DRY-RUN: would delete torrent %s due to movie pre-air (reason=%s).", torrent_hash, reason)
                return
            else:
                log.info("Pre-air Movie passed (reason=%s). Proceeding to file/ISO/ext check.", reason)
        
        if not preair_applied:
            log.info("Pre-air gate not applicable for category '%s' or services disabled.", category)

        # 2) Metadata + ISO/Extension policy cleaner
        if self.cfg.enable_iso_check:
            files = self.metadata.fetch(torrent_hash)
            if not files:
                log.warning("Metadata not available; skipping ISO/ext check.")
            else:
                deleted = self.iso.evaluate_and_act(torrent_hash, category_norm)
                if deleted:
                    return

        # 3) Start for real
        self.qbit.add_tags(torrent_hash, "guard:allowed")
        if not self.cfg.dry_run:
            self.qbit.start(torrent_hash)
        log.info("Started torrent %s after checks.", torrent_hash)


# --------------------------- Main ---------------------------

def main(argv: List[str]) -> None:
    """
    CLI entry point.
    Usage: qbit-guard.py <INFO_HASH> [<CATEGORY>]
    """
    if len(argv) < 2:
        print("Usage: qbit-guard.py <INFO_HASH> [<CATEGORY>]")
        sys.exit(1)
    torrent_hash = argv[1].strip()
    passed_category = (argv[2] if len(argv) >= 3 else "").strip()

    cfg = Config()
    guard = TorrentGuard(cfg)
    try:
        guard.run(torrent_hash, passed_category)
    except Exception as e:
        log.error("Unhandled error: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main(sys.argv)
