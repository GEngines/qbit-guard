#!/usr/bin/env python3
"""
watcher.py  — stateless

Attaches to qBittorrent's /api/v2/sync/maindata and triggers guard.TorrentGuard
when new torrents appear. No disk state is kept; only an in-memory set of
hashes seen during the current process lifetime.

Behavior:
- On first snapshot:
  - If WATCH_PROCESS_EXISTING_AT_START=1, process all currently present torrents.
  - Otherwise, just index them (skip processing).
- During runtime:
  - Process a torrent the first time we see its infohash.
  - If qB reports torrents_removed, we forget those hashes so a future re-add
    will be processed again.
- Optional: force a rescan if category or tags contain WATCH_RESCAN_KEYWORD
  (default 'rescan'), even if we've already processed it in this session.
"""

import os, sys, json, time, signal, logging, urllib.parse as uparse
from typing import Dict, Set, Tuple
import urllib.error

# Your class-based guard + clients
from guard import Config, HttpClient, QbitClient, TorrentGuard
from version import VERSION

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

# Create a filter to add version to all log records
class VersionFilter(logging.Filter):
    def filter(self, record):
        record.version = VERSION
        return True


log = logging.getLogger("qbit-guard-watcher")
log.addFilter(VersionFilter())


POLL_SEC = float(os.getenv("WATCH_POLL_SECONDS", "3.0"))
PROCESS_EXISTING_AT_START = os.getenv("WATCH_PROCESS_EXISTING_AT_START", "0") == "1"
RESCAN_KEYWORD = os.getenv("WATCH_RESCAN_KEYWORD", "rescan").strip().lower()  # in category/tags -> force

# Connection retry configuration
MAX_RETRY_ATTEMPTS = int(os.getenv("QBIT_MAX_RETRY_ATTEMPTS", "5"))
INITIAL_BACKOFF_SEC = float(os.getenv("QBIT_INITIAL_BACKOFF_SEC", "1.0"))
MAX_BACKOFF_SEC = float(os.getenv("QBIT_MAX_BACKOFF_SEC", "60.0"))

def is_connection_error(e: Exception) -> bool:
    """Check if an exception indicates a connection problem that warrants retry."""
    if isinstance(e, urllib.error.HTTPError):
        # Common HTTP error codes that indicate connection/auth issues
        return e.code in (401, 403, 500, 502, 503, 504)
    if isinstance(e, (urllib.error.URLError, ConnectionError, OSError)):
        return True
    # Check for timeout and other network-related errors
    if "timeout" in str(e).lower() or "connection" in str(e).lower():
        return True
    return False

def exponential_backoff_sleep(attempt: int, initial_delay: float = INITIAL_BACKOFF_SEC, max_delay: float = MAX_BACKOFF_SEC) -> None:
    """Sleep with exponential backoff, capped at max_delay."""
    delay = min(initial_delay * (2 ** attempt), max_delay)
    log.warning("Connection failed, retrying in %.1f seconds (attempt %d/%d): %s", delay, attempt + 1, MAX_RETRY_ATTEMPTS, str(e).split('\n')[0][:100])
    time.sleep(delay)

def qb_sync_maindata(http: HttpClient, cfg: Config, rid: int) -> Dict:
    url = f"{cfg.qbit_host}/api/v2/sync/maindata"
    if rid:
        url += "?" + uparse.urlencode({"rid": rid})
    raw = http.get(url)
    return {} if not raw else json.loads(raw.decode("utf-8"))

def _should_process(h: str, t: Dict, seen: Set[str]) -> Tuple[bool, str]:
    # Manual rescan via keyword in category or tags
    cat = (t.get("category") or "").strip().lower()
    tags = (t.get("tags") or "").strip().lower()
    if RESCAN_KEYWORD and (RESCAN_KEYWORD in cat or RESCAN_KEYWORD in tags):
        return True, "manual-rescan"
    if h not in seen:
        return True, "new"
    return False, "already-seen"

def main():
    log.info("qbit-guard watcher initializing - version %s", VERSION)
    cfg = Config()
    http = HttpClient(cfg.ignore_tls, cfg.user_agent)
    qb = QbitClient(cfg, http)
    guard = TorrentGuard(cfg)
    log.info("Watcher configuration loaded - host=%s, categories=%s", cfg.qbit_host, sorted(cfg.allowed_categories))

    # graceful shutdown
    stop = {"flag": False}
    def _sig(*_): stop["flag"] = True
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, _sig)

    # login with retry logic
    def ensure_authenticated() -> bool:
        """Ensure we're authenticated with qBittorrent, with retry logic."""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                qb.login()
                return True
            except Exception as e:
                if not is_connection_error(e) or attempt == MAX_RETRY_ATTEMPTS - 1:
                    log.error("qBittorrent login failed after %d attempts: %s", attempt + 1, e)
                    return False
                exponential_backoff_sleep(attempt)
        return False

    if not ensure_authenticated():
        log.critical("Fatal: Unable to authenticate with qBittorrent after maximum retries")
        log.critical("Terminating watcher process (exit code 2)")
        sys.exit(2)

    seen: Set[str] = set()
    rid = 0
    first_snapshot = True
    consecutive_failures = 0
    log.info(
        "Watcher (stateless) started - version %s, host=%s, poll=%.1fs, process_existing_at_start=%s, rescan-keyword='%s'",
        VERSION, cfg.qbit_host, POLL_SEC, PROCESS_EXISTING_AT_START, RESCAN_KEYWORD or "(disabled)"
    )

    while not stop["flag"]:
        try:
            data = qb_sync_maindata(http, cfg, rid)
            if not data:
                time.sleep(POLL_SEC)
                continue

            # Reset failure counter on successful request
            consecutive_failures = 0

            rid = data.get("rid", rid)
            torrents = data.get("torrents") or {}
            removed = data.get("torrents_removed") or []

            # First snapshot behavior
            if first_snapshot:
                first_snapshot = False
                present = set(torrents.keys())
                if PROCESS_EXISTING_AT_START:
                    log.info("Initial snapshot: processing %d existing torrents.", len(present))
                    # fall through: they will be processed below (since not in 'seen' yet)
                else:
                    seen |= present
                    log.info("Initial snapshot: indexed %d existing torrents (not processing).", len(present))
                    time.sleep(POLL_SEC)
                    continue

            # Forget hashes for removed torrents so re-adds will trigger again
            for h in removed:
                if h in seen:
                    seen.discard(h)

            # Handle new/changed torrents in this delta
            for h, t in torrents.items():
                name = t.get("name") or ""
                category = (t.get("category") or "").strip()
                ok, reason = _should_process(h, t, seen)
                if not ok:
                    log.debug("Skip %s | %s", h, reason)
                    continue

                log.info("Processing %s | reason=%s | category='%s' | name='%s'", h, reason, category, name)
                try:
                    guard.run(h, category)
                except Exception as e:
                    log.error("Guard run failed for torrent %s (%s): %s", h[:8], name[:50], str(e).split('\n')[0][:100])
                finally:
                    seen.add(h)

        except Exception as e:
            if is_connection_error(e):
                consecutive_failures += 1
                log.warning("Connection error (consecutive failure %d): %s", consecutive_failures, str(e).split('\n')[0][:100])
                
                # If we've had multiple consecutive failures, attempt reconnection
                if consecutive_failures >= 2:
                    log.warning("Multiple connection failures detected (%d), attempting full reconnection...", consecutive_failures)
                    
                    # Reset connection state
                    rid = 0  # Reset request ID to start fresh
                    first_snapshot = True  # Re-initialize snapshot state
                    
                    # Attempt to re-authenticate with exponential backoff
                    reconnected = False
                    for attempt in range(MAX_RETRY_ATTEMPTS):
                        try:
                            qb.login()
                            log.info("Successfully reconnected to qBittorrent after %d attempts", attempt + 1)
                            consecutive_failures = 0
                            reconnected = True
                            break
                        except Exception as auth_e:
                            if not is_connection_error(auth_e) or attempt == MAX_RETRY_ATTEMPTS - 1:
                                log.error("Reconnection attempt failed after %d attempts: %s", attempt + 1, auth_e)
                                break
                            exponential_backoff_sleep(attempt)
                    
                    if not reconnected:
                        log.critical("Fatal: Failed to reconnect to qBittorrent after multiple attempts")
                        log.critical("Terminating watcher process (exit code 3)")
                        sys.exit(3)
                else:
                    # Single failure, just wait before retry
                    exponential_backoff_sleep(0)
            else:
                # Non-connection error, log and continue
                log.error("Watcher loop error (non-connection): %s", str(e).split('\n')[0][:100])
                consecutive_failures = 0

        time.sleep(POLL_SEC)

    log.info("Received shutdown signal, cleaning up...")
    log.info("qbit-guard watcher shutdown complete")

if __name__ == "__main__":
    main()
