# <img alt="qbit-guard logo" src="https://gengines.github.io/qbit-guard/img/qbit-guard-icon.png"> Environment Variables Reference

Complete reference of all environment variables supported by qbit-guard, organized by feature area.

---

## Essential qBittorrent Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `QBIT_HOST` | `http://127.0.0.1:8080` | qBittorrent WebUI URL |
| `QBIT_USER` | `admin` | qBittorrent WebUI username |
| `QBIT_PASS` | `adminadmin` | qBittorrent WebUI password |
| `QBIT_ALLOWED_CATEGORIES` | `radarr,tv-sonarr` | Comma-separated list of categories to process |
| `QBIT_DELETE_FILES` | `true` | Delete files when removing torrents |
| `QBIT_IGNORE_TLS` | `0` | Set to `1` to ignore SSL certificate errors |
| `QBIT_DRY_RUN` | `0` | Set to `1` for testing mode (no actual deletions) |

---

## Container Watcher (Polling Mode)

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCH_POLL_SECONDS` | `3.0` | How often to check qBittorrent for new torrents (seconds) |
| `WATCH_PROCESS_EXISTING_AT_START` | `0` | Process existing torrents when container starts (`0` or `1`) |
| `WATCH_RESCAN_KEYWORD` | `rescan` | Keyword in category/tags to force reprocessing |

---

## Sonarr Integration (Pre-air Gate)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_PREAIR_CHECK` | `1` | Enable pre-air checking (`0` or `1`) |
| `SONARR_URL` | `http://127.0.0.1:8989` | Sonarr base URL |
| `SONARR_APIKEY` | - | Sonarr API key |
| `SONARR_CATEGORIES` | `tv-sonarr` | Categories to apply pre-air checks to |
| `EARLY_GRACE_HOURS` | `6` | Allow releases this many hours before air date |
| `EARLY_HARD_LIMIT_HOURS` | `72` | Block releases more than this many hours early |
| `WHITELIST_OVERRIDES_HARD_LIMIT` | `0` | Let whitelisted releases bypass hard limit (`0` or `1`) |
| `EARLY_WHITELIST_GROUPS` | - | Comma-separated list of trusted release groups |
| `EARLY_WHITELIST_INDEXERS` | - | Comma-separated list of trusted indexers |
| `EARLY_WHITELIST_TRACKERS` | - | Comma-separated list of trusted trackers |
| `RESUME_IF_NO_HISTORY` | `1` | Proceed if Sonarr history not found (`0` or `1`) |
| `SONARR_TIMEOUT_SEC` | `45` | HTTP timeout for Sonarr API calls |
| `SONARR_RETRIES` | `3` | Retry attempts for Sonarr operations |

---

## Radarr Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `RADARR_URL` | `http://127.0.0.1:7878` | Radarr base URL |
| `RADARR_APIKEY` | - | Radarr API key |
| `RADARR_PREAIR_CATEGORIES` | `radarr` | Categories to apply movie pre-air checks to |
| `RADARR_CATEGORIES` | `radarr` | Categories to apply Radarr blocklisting to |
| `RADARR_TIMEOUT_SEC` | `45` | HTTP timeout for Radarr API calls |
| `RADARR_RETRIES` | `3` | Retry attempts for Radarr operations |

!!! info "Movie Pre-air Logic"
    Movie pre-air checking uses orchestrated logic with fallbacks:
    
    1. **Primary**: TMDB API for digital/physical release dates (if `TMDB_APIKEY` is set)
    2. **Fallback**: Radarr metadata (`digitalRelease`, `physicalRelease`, `inCinemas`, `releaseDate`)
    3. **Cross-verification**: Optional TVDB integration for additional validation
    
    Movie pre-air checking is controlled by the same `ENABLE_PREAIR_CHECK` flag used for TV shows.

---

## Internet Cross-Verification

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERNET_CHECK_PROVIDER` | `tvmaze` | Provider selection: `off`, `tvmaze`, `tvdb`, or `both` |

### TVmaze Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `TVMAZE_BASE` | `https://api.tvmaze.com` | TVmaze API base URL |
| `TVMAZE_TIMEOUT_SEC` | `8` | HTTP timeout for TVmaze API calls |

### TheTVDB Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `TVDB_BASE` | `https://api4.thetvdb.com/v4` | TheTVDB API base URL |
| `TVDB_APIKEY` | - | TheTVDB API key (required for TVDB) |
| `TVDB_PIN` | - | TheTVDB PIN (optional) |
| `TVDB_LANGUAGE` | `eng` | Language code for TheTVDB |
| `TVDB_ORDER` | `default` | Episode order: `default` or `official` |
| `TVDB_TIMEOUT_SEC` | `8` | HTTP timeout for TheTVDB API calls |
| `TVDB_BEARER` | - | Reuse existing bearer token (optional) |

### TMDB Integration
| Variable | Default | Description |
|----------|---------|-------------|
| `TMDB_APIKEY` | - | TMDB (The Movie Database) API key for movie release date verification |
| `TMDB_BASE` | `https://api.themoviedb.org/3` | TMDB API base URL |
| `TMDB_TIMEOUT_SEC` | `8` | HTTP timeout for TMDB API calls |

!!! tip "TMDB Benefits"
    TMDB provides authoritative digital and physical release dates for movies, improving pre-air filtering accuracy. It serves as the primary source for movie release dates, with Radarr as fallback.

---

## ISO/BDMV Cleanup

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_ISO_CHECK` | `1` | Enable ISO/disc image cleanup (`0` or `1`) |
| `MIN_KEEPABLE_VIDEO_MB` | `50` | Minimum size for video files to keep (MB) |
| `METADATA_POLL_INTERVAL` | `1.5` | Seconds between file list checks during metadata fetching |
| `METADATA_MAX_WAIT_SEC` | `0` | Max wait for metadata resolution (`0` = infinite) |
| `METADATA_DOWNLOAD_BUDGET_BYTES` | `0` | Max bytes to download during metadata wait (`0` = no limit) |

---

## Extension Policy

| Variable | Default | Description |
|----------|---------|-------------|
| `GUARD_EXT_STRATEGY` | `block` | Extension strategy: `block` or `allow` |
| `GUARD_ALLOWED_EXTS` | - | Comma-separated list of allowed extensions (for `allow` mode) |
| `GUARD_BLOCKED_EXTS` | - | Comma-separated list of blocked extensions (overrides defaults in `block` mode) |
| `GUARD_EXT_DELETE_IF_ALL_BLOCKED` | `1` | Delete only if all files are disallowed (`0` or `1`) |
| `GUARD_EXT_DELETE_IF_ANY_BLOCKED` | `0` | Delete if any file is disallowed (`0` or `1`) |
| `GUARD_EXT_VIOLATION_TAG` | `trash:ext` | Tag applied to torrents deleted for extension violations |
| `GUARD_UNCHECK_BLOCKED_FILES` | `1` | Uncheck blocked files instead of deleting entire torrent (`0` or `1`) |
| `GUARD_DISC_EXTS` | `iso,img,mdf,nrg,cue,bin` | Disc image extensions |
| `GUARD_EXTS_FILE` | - | Path to JSON config file (optional) |

!!! tip "Selective File Control"
    When `GUARD_UNCHECK_BLOCKED_FILES=1` (default), qbit-guard will:
    
    - **Uncheck** blocked files (set priority to 0) instead of deleting the entire torrent
    - **Preserve** allowed files for download
    - **Tag** the torrent with `guard:partial` to indicate partial processing
    - **Continue** with the download of remaining allowed files
    
    This provides more granular control and prevents losing wanted content due to a few unwanted files.

---

## Logging and Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity: `INFO`, `DETAILED`, or `DEBUG` |
| `USER_AGENT` | `qbit-guard/2.0` | HTTP User-Agent string for API calls |

!!! note "Logging Levels"
    - **INFO**: Standard operational logs  
    - **DETAILED**: Enhanced extension policy logging with file counts and examples
    - **DEBUG**: Full debugging information including HTTP requests/responses

---

## Configuration by Use Case

### Minimal Setup
```bash
# Only required when using containers (defaults work for localhost)
QBIT_HOST=http://qbittorrent:8080
QBIT_PASS=your_password

# Note: QBIT_USER, QBIT_ALLOWED_CATEGORIES, ENABLE_ISO_CHECK all have sensible defaults
```

### Pre-air Gate Only
```bash
# qBittorrent connection (for containers)
QBIT_HOST=http://qbittorrent:8080
QBIT_PASS=your_password

# Sonarr pre-air checking - API key required
SONARR_URL=http://sonarr:8989
SONARR_APIKEY=your_sonarr_api_key

# Note: ENABLE_PREAIR_CHECK=1 by default, along with reasonable grace periods
```

### Full Featured Setup
```bash
# qBittorrent (for containers)
QBIT_HOST=http://qbittorrent:8080
QBIT_PASS=your_password

# Sonarr pre-air checking
SONARR_URL=http://sonarr:8989
SONARR_APIKEY=your_sonarr_api_key
EARLY_WHITELIST_GROUPS=trusted_group1,trusted_group2

# Radarr integration with TMDB enhancement
RADARR_URL=http://radarr:7878
RADARR_APIKEY=your_radarr_api_key
TMDB_APIKEY=your_tmdb_api_key  # Enhanced movie release date accuracy

# Selective file control
GUARD_UNCHECK_BLOCKED_FILES=1  # Default behavior
GUARD_EXT_STRATEGY=allow
GUARD_ALLOWED_EXTS=mkv,mp4,m4v,avi,ts,m2ts,mov,webm,srt,ass

# Optional overrides
MIN_KEEPABLE_VIDEO_MB=100
LOG_LEVEL=DETAILED  # Enhanced extension logging

# Note: Many features enabled by default - ISO cleanup, pre-air checks, TVmaze verification
```

### High Performance Setup
```bash
# Faster polling
WATCH_POLL_SECONDS=1.0

# Increased timeouts for slow networks
SONARR_TIMEOUT_SEC=90
RADARR_TIMEOUT_SEC=90
TVMAZE_TIMEOUT_SEC=15

# Process existing torrents on startup
WATCH_PROCESS_EXISTING_AT_START=1

# Metadata limits for large torrents
METADATA_MAX_WAIT_SEC=300
METADATA_DOWNLOAD_BUDGET_BYTES=104857600  # 100MB
```

### Selective File Control Example
```bash
# Enable selective file unchecking (default behavior)
GUARD_UNCHECK_BLOCKED_FILES=1

# Use allow strategy for precise control
GUARD_EXT_STRATEGY=allow
GUARD_ALLOWED_EXTS=mkv,mp4,m4v,avi,ts,m2ts,mov,webm,srt,ass,sub

# Only delete if ALL files are blocked (not just some)
GUARD_EXT_DELETE_IF_ALL_BLOCKED=1
GUARD_EXT_DELETE_IF_ANY_BLOCKED=0

# Enhanced logging to see what's being unchecked
LOG_LEVEL=DETAILED

# Connection settings
QBIT_HOST=http://qbittorrent:8080
QBIT_PASS=your_password
QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
```

### Movies with TMDB Integration Example
```bash
# Core connection
QBIT_HOST=http://qbittorrent:8080
QBIT_PASS=your_password
QBIT_ALLOWED_CATEGORIES=radarr

# Movie-focused pre-air checking with TMDB
ENABLE_PREAIR_CHECK=1
RADARR_URL=http://radarr:7878
RADARR_APIKEY=your_radarr_api_key
TMDB_APIKEY=your_tmdb_api_key  # Primary source for release dates

# Enhanced grace periods for movies
EARLY_GRACE_HOURS=12
EARLY_HARD_LIMIT_HOURS=168  # 1 week

# Optional: Additional verification
INTERNET_CHECK_PROVIDER=both
TVDB_APIKEY=your_tvdb_api_key

# Log detailed release date checks
LOG_LEVEL=DETAILED
```

---

## Default Values Summary

Variables with meaningful defaults that you may not need to set:

| Variable | Default | Notes |
|----------|---------|-------|
| `QBIT_HOST` | `http://127.0.0.1:8080` | Usually needs to be changed for containers |
| `QBIT_USER` | `admin` | Most qBittorrent installations |
| `QBIT_PASS` | `adminadmin` | Default qBittorrent password |
| `QBIT_ALLOWED_CATEGORIES` | `radarr,tv-sonarr` | Common categories for *arr services |
| `QBIT_DELETE_FILES` | `true` | Usually desired behavior |
| `ENABLE_PREAIR_CHECK` | `1` | Pre-air checking enabled by default |
| `SONARR_URL` | `http://127.0.0.1:8989` | Default Sonarr port |
| `RADARR_URL` | `http://127.0.0.1:7878` | Default Radarr port |
| `ENABLE_ISO_CHECK` | `1` | ISO cleanup enabled by default |
| `INTERNET_CHECK_PROVIDER` | `tvmaze` | TVmaze enabled by default (no API key needed) |
| `WATCH_POLL_SECONDS` | `3.0` | Good balance of responsiveness/resources |
| `EARLY_GRACE_HOURS` | `6` | Reasonable pre-air grace period |
| `EARLY_HARD_LIMIT_HOURS` | `72` | Prevents very early releases |
| `MIN_KEEPABLE_VIDEO_MB` | `50` | Filters out samples and extras |
| `LOG_LEVEL` | `INFO` | Change to `DETAILED` for extension details or `DEBUG` for troubleshooting |
| `USER_AGENT` | `qbit-guard/2.0` | HTTP User-Agent for API calls |

---

## Next Steps

- **[Configuration Guide →](configure.md)** - Detailed setup instructions
- **[Examples →](../examples.md)** - Working configurations
- **[Troubleshooting →](../troubleshooting.md)** - Common variable issues
