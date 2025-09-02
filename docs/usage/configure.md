# <img alt="qbit-guard logo" src="https://gengines.github.io/qbit-guard/img/qbit-guard-icon.png"> Configuration Guide

All configuration is handled via environment variables with sensible defaults. This guide covers all the major configuration areas for qbit-guard.

---

## Essential qBittorrent Settings

These are the minimum required settings to connect qbit-guard to qBittorrent:

```bash
# qBittorrent connection
QBIT_HOST=http://qbittorrent:8080              # qB WebUI URL
QBIT_USER=admin                                # WebUI username  
QBIT_PASS=adminadmin                          # WebUI password
QBIT_ALLOWED_CATEGORIES="tv-sonarr,radarr"    # Comma-separated categories to process
QBIT_DELETE_FILES=true                        # Delete files when removing torrents
QBIT_IGNORE_TLS=0                            # Set to 1 to ignore SSL certificate errors
QBIT_DRY_RUN=0                               # Set to 1 for testing (no actual deletions)
```

### Important Notes

- **QBIT_HOST**: Must be accessible from the qbit-guard container/script
- **QBIT_ALLOWED_CATEGORIES**: Only torrents in these categories will be processed
- **QBIT_DRY_RUN**: Enable for testing - prevents actual torrent deletions

---

## Sonarr Integration (Pre-air Gate)

Configure Sonarr integration to block early TV show releases:

```bash
# Enable pre-air checking
ENABLE_PREAIR_CHECK=1
SONARR_URL=http://sonarr:8989
SONARR_APIKEY=your_sonarr_api_key_here
SONARR_CATEGORIES="tv-sonarr"                 # Categories to apply pre-air checks to

# Pre-air timing controls
EARLY_GRACE_HOURS=6                           # Allow releases this many hours before air date
EARLY_HARD_LIMIT_HOURS=72                     # Block releases more than this many hours early
WHITELIST_OVERRIDES_HARD_LIMIT=0             # Set to 1 to let whitelisted releases bypass hard limit

# Whitelisting (comma-separated, case-insensitive)
EARLY_WHITELIST_GROUPS="scene_group1,group2"
EARLY_WHITELIST_INDEXERS="indexer1,indexer2" 
EARLY_WHITELIST_TRACKERS="tracker1,tracker2"

# Fallback behavior
RESUME_IF_NO_HISTORY=1                        # Proceed if Sonarr history not found yet
```

### How Pre-air Checking Works

1. **Grace Period**: Allows releases within `EARLY_GRACE_HOURS` of air date (default: 6h)
2. **Hard Limit**: Blocks releases more than `EARLY_HARD_LIMIT_HOURS` early (default: 72h)
3. **Whitelists**: Trusted groups/indexers/trackers can bypass timing restrictions
4. **Blocklisting**: Blocked releases are automatically blocklisted in Sonarr before deletion

---

## Radarr Integration (Pre-air Gate & ISO Blocklisting)

Configure Radarr integration for both movie pre-air checking and ISO cleanup:

```bash
# Radarr connection
RADARR_URL=http://radarr:7878
RADARR_APIKEY=your_radarr_api_key_here

# Pre-air checking for movies (new feature)
ENABLE_RADARR_PREAIR_CHECK=1                 # Enable pre-air checking for movies
RADARR_PREAIR_CATEGORIES="radarr"            # Categories to apply pre-air checks to

# ISO cleanup (existing feature)
RADARR_CATEGORIES="radarr"                   # Categories to apply Radarr blocklisting to
```

### How Movie Pre-air Checking Works

Similar to TV show pre-air checking, but for movies:

1. **Grace Period**: Allows releases within `EARLY_GRACE_HOURS` of release date (default: 6h)
2. **Hard Limit**: Blocks releases more than `EARLY_HARD_LIMIT_HOURS` early (default: 72h)
3. **Whitelists**: Trusted groups/indexers/trackers can bypass timing restrictions
4. **Blocklisting**: Blocked releases are automatically blocklisted in Radarr before deletion

The system checks multiple release date fields from Radarr including `digitalRelease`, `physicalRelease`, `inCinemas`, and `releaseDate`.

This integration ensures that both ISO files deleted by qbit-guard and unreleased movies are also blocklisted in Radarr to prevent re-downloading.

---

## Internet Cross-Verification (Optional)

Add external verification of air dates using TVmaze and/or TheTVDB:

```bash
# Provider selection
INTERNET_CHECK_PROVIDER=tvmaze               # off, tvmaze, tvdb, or both

# TVmaze settings (no API key required)
TVMAZE_BASE=https://api.tvmaze.com
TVMAZE_TIMEOUT_SEC=8

# TheTVDB settings (requires API key)
TVDB_BASE=https://api4.thetvdb.com/v4
TVDB_APIKEY=your_tvdb_api_key_here
TVDB_PIN=your_tvdb_pin                       # Optional
TVDB_LANGUAGE=eng                            # Language code
TVDB_ORDER=default                           # default or official
TVDB_TIMEOUT_SEC=8
TVDB_BEARER=                                 # Reuse existing token (optional)
```

### Provider Options

- **`off`**: No internet verification
- **`tvmaze`**: Use TVmaze API (no key required)
- **`tvdb`**: Use TheTVDB API (requires API key)
- **`both`**: Use both services for cross-verification

---

## ISO/BDMV Cleanup

Configure automatic cleanup of disc image torrents:

```bash
# Enable ISO/disc image cleanup
ENABLE_ISO_CHECK=1

# Video file criteria  
MIN_KEEPABLE_VIDEO_MB=50                     # Minimum size for video files to keep (MB)

# Metadata fetching behavior
METADATA_POLL_INTERVAL=1.5                   # Seconds between file list checks
METADATA_MAX_WAIT_SEC=0                      # Max wait for metadata (0 = infinite)
METADATA_DOWNLOAD_BUDGET_BYTES=0             # Max bytes to download while waiting (0 = no limit)
```

### How ISO Cleanup Works

1. **Detection**: Identifies torrents containing only disc images (ISO, BDMV, VIDEO_TS)
2. **Video Check**: Looks for keepable video files above the size threshold
3. **Cleanup**: Removes torrents with no keepable video content
4. **Blocklisting**: Automatically blocklists removed torrents in appropriate *arr service

---

## Extension Policy

Control which file types are allowed or blocked:

```bash
# Strategy
GUARD_EXT_STRATEGY=block                     # block (default) or allow

# Lists
GUARD_ALLOWED_EXTS="mkv, mp4, srt, ass"                          # (used in allow mode)
GUARD_BLOCKED_EXTS="iso, exe, bat, cmd, sh, msi, zip, rar, 7z"   # (overrides defaults in block mode)

# Enforcement
GUARD_EXT_DELETE_IF_ALL_BLOCKED=1             # (default) – delete only if all files are disallowed
GUARD_EXT_DELETE_IF_ANY_BLOCKED=0             # – set to 1 to delete if any file is disallowed
GUARD_EXT_VIOLATION_TAG=trash:ext

# File unchecking (new feature)
GUARD_UNCHECK_BLOCKED_FILES=1                 # (default) – uncheck disallowed files instead of deleting torrent

# Disc set override (used by ISO detection and defaults)
GUARD_DISC_EXTS="iso,img,mdf,nrg,cue,bin"
```

### Extension Strategies

- **Block Strategy**: Allow everything except blocked extensions
- **Allow Strategy**: Only allow specified extensions

### Enforcement Options

- **GUARD_EXT_DELETE_IF_ALL_BLOCKED**: Delete torrent only if ALL files are disallowed (default: true)
- **GUARD_EXT_DELETE_IF_ANY_BLOCKED**: Delete torrent if ANY file is disallowed (default: false) 
- **GUARD_UNCHECK_BLOCKED_FILES**: Uncheck (don't download) disallowed files instead of deleting the entire torrent (default: true)

When `GUARD_UNCHECK_BLOCKED_FILES=1`, qbit-guard will:
- Identify files that match the blocklist
- Set their priority to 0 (don't download) if some files are allowed
- Add a "guard:partial" tag to indicate partial downloads
- Allow the torrent to continue downloading only the allowed files
- Still delete the torrent if ALL files would be unchecked

### Optional Config File

Instead of environment variables, use a JSON config file:

```bash
# Config file (optional)
GUARD_EXTS_FILE=/config/extensions.json
```

Example `extensions.json`:
```json
{
  "strategy": "allow",
  "allowed": ["mkv","mp4","m4v","webm","srt","ass","flac"],
  "blocked": ["iso","exe","zip","rar","7z"]
}
```

---

## Container Watcher Settings

Configure polling behavior for container mode:

```bash
WATCH_POLL_SECONDS=3.0                       # How often to check for new torrents
WATCH_PROCESS_EXISTING_AT_START=0            # Set to 1 to process existing torrents on startup
WATCH_RESCAN_KEYWORD=rescan                  # Add this keyword to category/tags to force reprocessing
```

### Connection Reliability

Configure reconnection behavior when qBittorrent restarts:

```bash
QBIT_MAX_RETRY_ATTEMPTS=5                    # Maximum reconnection attempts (default: 5)
QBIT_INITIAL_BACKOFF_SEC=1.0                 # Initial retry delay in seconds (default: 1.0)
QBIT_MAX_BACKOFF_SEC=60.0                    # Maximum retry delay in seconds (default: 60.0)
```

The watcher will automatically detect connection failures and attempt to reconnect with exponential backoff. On successful reconnection, it resets the request ID and re-authenticates to ensure clean state recovery.

---

## Reliability & Performance

Fine-tune timeouts and retry behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `SONARR_TIMEOUT_SEC` | 45 | HTTP timeout for Sonarr API calls |
| `SONARR_RETRIES` | 3 | Retry attempts for Sonarr blocklist operations |
| `RADARR_TIMEOUT_SEC` | 45 | HTTP timeout for Radarr API calls |
| `RADARR_RETRIES` | 3 | Retry attempts for Radarr blocklist operations |
| `USER_AGENT` | `qbit-guard/2.0` | HTTP User-Agent string |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`INFO` or `DEBUG`) |

---

## Configuration Examples

### Minimal Setup
```bash
QBIT_HOST=http://qbittorrent:8080
QBIT_USER=admin
QBIT_PASS=your_password
QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
ENABLE_ISO_CHECK=1
```

### Full Pre-air Setup
```bash
# qBittorrent
QBIT_HOST=http://qbittorrent:8080
QBIT_USER=admin
QBIT_PASS=your_password
QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr

# Sonarr pre-air checking (TV shows)
ENABLE_PREAIR_CHECK=1
SONARR_URL=http://sonarr:8989
SONARR_APIKEY=your_sonarr_api_key
EARLY_GRACE_HOURS=6
EARLY_HARD_LIMIT_HOURS=72
EARLY_WHITELIST_GROUPS=trusted_group1,trusted_group2

# Radarr pre-air checking (Movies)
ENABLE_RADARR_PREAIR_CHECK=1
RADARR_URL=http://radarr:7878
RADARR_APIKEY=your_radarr_api_key

# Internet verification
INTERNET_CHECK_PROVIDER=tvmaze

# ISO cleanup
ENABLE_ISO_CHECK=1

LOG_LEVEL=DEBUG
```

---

## Next Steps

- **[Environment Variables →](env.md)** - Complete reference of all variables
- **[Examples →](../examples.md)** - Working Docker Compose configurations
- **[Troubleshooting →](../troubleshooting.md)** - Common configuration issues
