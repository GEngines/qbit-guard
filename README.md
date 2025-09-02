# <img alt="qbit-guard logo" src="img/qbit-guard-icon.png"> qbit-guard

A zero-dependency Python guard for qBittorrent that blocks pre-air TV episodes (Sonarr) and unreleased movies (Radarr), deletes ISO/BDMV-only torrents, and auto-blocklists bad releases in Sonarr/Radarr (with dedupe + queue failover). Runs on "torrent added", fetches metadata safely, and logs everything to stdout.

## Documentation

**The full documentation has moved to: https://gengines.github.io/qbit-guard/**

Please visit our GitHub Pages site for comprehensive documentation including:
- Installation instructions
- Configuration options
- Docker deployment guides
- Usage examples
- Troubleshooting tips

## Quick Links

- **Documentation:** https://gengines.github.io/qbit-guard/
- **Docker Image:** `ghcr.io/gengines/qbit-guard:<tag>`
- **UNRAID:** Available in Community Applications as "qbit-guard" (or via binhex's version)
- **Repository:** https://github.com/GEngines/qbit-guard

## Key Features

- **Pre-air gate (Sonarr)**: Stops new TV torrents, checks airDateUtc with configurable grace periods
- **Pre-air gate (Radarr)**: Stops new movie torrents, checks release dates with configurable grace periods
- **Extension policy**: Allow/Block by file extension with configurable strategies
- **ISO/BDMV cleaner**: Removes disc-image-only torrents that lack keepable video content
- **Smart blocklisting**: Blocklists in Sonarr/Radarr before deletion using deduped history
- **Internet cross-verification**: Optional TVmaze and/or TheTVDB API integration
- **Zero dependencies**: No external libraries, just Python 3.8+ stdlib
- **Container-friendly**: All configuration via environment variables, logs to stdout