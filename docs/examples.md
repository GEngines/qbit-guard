# <img alt="qbit-guard logo" src="https://gengines.github.io/qbit-guard/img/qbit-guard-icon.png"> Configuration Examples

This page provides working examples of qbit-guard configurations for different deployment scenarios and use cases.

!!! info "Example Usage"
    All examples include complete Docker Compose configurations. Adapt environment variables to match your setup.

---

## :whale: Docker Compose Examples

=== "Minimal Setup"

    **Basic configuration for getting started quickly**

    ```yaml
    version: '3.8'

    services:
      qbit-guard:
        image: ghcr.io/gengines/qbit-guard:latest
        container_name: qbit-guard
        restart: unless-stopped
        environment:
          # Essential qBittorrent connection
          - QBIT_HOST=http://qbittorrent:8080
          - QBIT_USER=admin
          - QBIT_PASS=your_password_here
          - QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
          
          # Pre-air checking with Sonarr
          - ENABLE_PREAIR_CHECK=1
          - SONARR_URL=http://sonarr:8989
          - SONARR_APIKEY=your_sonarr_api_key_here
          
          # Pre-air checking with Radarr (for movies)
          - # Pre-air checking for movies now uses ENABLE_PREAIR_CHECK (same as TV shows)
          - RADARR_URL=http://radarr:7878
          - RADARR_APIKEY=your_radarr_api_key_here
          
          # ISO cleanup
          - ENABLE_ISO_CHECK=1
          
          - LOG_LEVEL=INFO
        networks: [arr-network]

    networks:
      arr-network: { driver: bridge }
    ```

    !!! tip "Getting Started"
        This minimal setup enables pre-air checking for both TV shows and movies, plus ISO cleanup. Perfect for testing qbit-guard functionality.

=== "Full Configuration"

    **Production-ready setup with all features enabled**

    ```yaml
    version: '3.8'

    services:
      qbit-guard:
        image: ghcr.io/gengines/qbit-guard:latest
        container_name: qbit-guard
        restart: unless-stopped
        environment:
          # qBittorrent connection
          - QBIT_HOST=http://qbittorrent:8080
          - QBIT_USER=admin
          - QBIT_PASS=your_password_here
          - QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
          - QBIT_DELETE_FILES=true
          
          # Pre-air checking with Sonarr
          - ENABLE_PREAIR_CHECK=1
          - SONARR_URL=http://sonarr:8989
          - SONARR_APIKEY=your_sonarr_api_key_here
          - SONARR_CATEGORIES=tv-sonarr
          - EARLY_GRACE_HOURS=6
          - EARLY_HARD_LIMIT_HOURS=72
          - EARLY_WHITELIST_GROUPS=SCENE,P2P,WEB
          - WHITELIST_OVERRIDES_HARD_LIMIT=1
          
          # Pre-air checking with Radarr (for movies)
          - # Pre-air checking for movies now uses ENABLE_PREAIR_CHECK (same as TV shows)
          - RADARR_URL=http://radarr:7878
          - RADARR_APIKEY=your_radarr_api_key_here
          - RADARR_PREAIR_CATEGORIES=radarr
          
          # Internet cross-verification
          - INTERNET_CHECK_PROVIDER=both
          - TVDB_APIKEY=your_tvdb_api_key_here
          
          # ISO/BDMV cleanup
          - ENABLE_ISO_CHECK=1
          - MIN_KEEPABLE_VIDEO_MB=100
          
          # Radarr integration for blocklisting
          - RADARR_URL=http://radarr:7878
          - RADARR_APIKEY=your_radarr_api_key_here
          
          # Performance tuning
          - WATCH_POLL_SECONDS=3.0
          - METADATA_MAX_WAIT_SEC=300
          - METADATA_DOWNLOAD_BUDGET_BYTES=104857600  # 100MB
          
          # Extension filtering
          - GUARD_EXT_STRATEGY=allow
          - GUARD_ALLOWED_EXTS=mkv,mp4,m4v,avi,ts,m2ts,mov,webm,srt,ass
          
          - LOG_LEVEL=INFO
        networks: [arr-network]

    networks:
      arr-network: { driver: bridge }
    ```

    !!! success "Production Ready"
        This configuration includes all features: TV and movie pre-air checking, internet verification, ISO cleanup, and extension filtering.

=== "High Performance"

    **Optimized for fast processing and high throughput**

    ```yaml
    version: '3.8'

    services:
      qbit-guard:
        image: ghcr.io/gengines/qbit-guard:latest
        container_name: qbit-guard
        restart: unless-stopped
        environment:
          - QBIT_HOST=http://qbittorrent:8080
          - QBIT_USER=admin
          - QBIT_PASS=your_password_here
          - QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
          
          # Fast polling and processing
          - WATCH_POLL_SECONDS=1.0
          - WATCH_PROCESS_EXISTING_AT_START=1
          
          # Aggressive timeouts for faster failure detection
          - SONARR_TIMEOUT_SEC=90
          - RADARR_TIMEOUT_SEC=90
          - TVMAZE_TIMEOUT_SEC=15
          - TVDB_TIMEOUT_SEC=15
          
          # More retries for reliability
          - SONARR_RETRIES=5
          - RADARR_RETRIES=5
          
          # Quick metadata fetching
          - METADATA_MAX_WAIT_SEC=60
          - METADATA_DOWNLOAD_BUDGET_BYTES=52428800  # 50MB
          
          # Enable all checks
          - ENABLE_PREAIR_CHECK=1
          - # Pre-air checking for movies now uses ENABLE_PREAIR_CHECK (same as TV shows)
          - ENABLE_ISO_CHECK=1
          - SONARR_URL=http://sonarr:8989
          - SONARR_APIKEY=your_sonarr_api_key_here
          - RADARR_URL=http://radarr:7878
          - RADARR_APIKEY=your_radarr_api_key_here
          
          - LOG_LEVEL=INFO
        networks: [arr-network]
        deploy:
          resources:
            limits:
              memory: 256M
              cpus: '0.5'

    networks:
      arr-network: { driver: bridge }
    ```

    !!! warning "Resource Usage"
        High-performance settings will use more CPU and network resources. Monitor system performance.

---

## :gear: Use Case Examples

=== "TV Shows Only"

    **Configuration focused on Sonarr integration**

    ```yaml
    environment:
      - QBIT_HOST=http://qbittorrent:8080
      - QBIT_USER=admin
      - QBIT_PASS=your_password_here
      - QBIT_ALLOWED_CATEGORIES=tv-sonarr
      
      # Pre-air checking for TV shows
      - ENABLE_PREAIR_CHECK=1
      - SONARR_URL=http://sonarr:8989
      - SONARR_APIKEY=your_sonarr_api_key_here
      - EARLY_GRACE_HOURS=6
      - EARLY_HARD_LIMIT_HOURS=72
      
      # Internet verification for better accuracy
      - INTERNET_CHECK_PROVIDER=tvmaze
      
      # Disable ISO check (not needed for TV shows)
      - ENABLE_ISO_CHECK=0
      
      - LOG_LEVEL=INFO
    ```

    !!! note "TV-Focused"
        This configuration focuses on TV show management with Sonarr integration and pre-air checking.

=== "Movies Only"

    **Configuration focused on Radarr integration**

    ```yaml
    environment:
      - QBIT_HOST=http://qbittorrent:8080
      - QBIT_USER=admin
      - QBIT_PASS=your_password_here
      - QBIT_ALLOWED_CATEGORIES=radarr
      
      # Movie pre-air checking with Radarr
      - # Pre-air checking for movies now uses ENABLE_PREAIR_CHECK (same as TV shows)
      - RADARR_URL=http://radarr:7878
      - RADARR_APIKEY=your_radarr_api_key_here
      - RADARR_PREAIR_CATEGORIES=radarr
      - EARLY_GRACE_HOURS=6
      - EARLY_HARD_LIMIT_HOURS=72
      
      # Disable TV pre-air checking
      - ENABLE_PREAIR_CHECK=0
      
      # Enable ISO cleanup for movie disc images
      - ENABLE_ISO_CHECK=1
      - MIN_KEEPABLE_VIDEO_MB=100
      
      # Strict extension filtering for movies
      - GUARD_EXT_STRATEGY=allow
      - GUARD_ALLOWED_EXTS=mkv,mp4,m4v,avi,ts,m2ts,mov,webm
      - GUARD_EXT_DELETE_IF_ANY_BLOCKED=1
      
      - LOG_LEVEL=INFO
    ```

    !!! tip "Movie Focus"
        Optimized for movie downloads with pre-air checking, ISO cleanup and strict file type filtering.

=== "Testing & Development"

    **Safe configuration for testing and debugging**

    ```yaml
    environment:
      # Dry run mode - no actual deletions
      - QBIT_DRY_RUN=1
      
      # Debug logging for troubleshooting
      - LOG_LEVEL=DEBUG
      
      # Fast polling for immediate testing
      - WATCH_POLL_SECONDS=1.0
      
      # Process existing torrents on startup
      - WATCH_PROCESS_EXISTING_AT_START=1
      
      # Short timeouts to fail fast during testing
      - SONARR_TIMEOUT_SEC=10
      - RADARR_TIMEOUT_SEC=10
      
      # Minimal metadata wait time
      - METADATA_MAX_WAIT_SEC=30
      
      # Standard connection settings
      - QBIT_HOST=http://qbittorrent:8080
      - QBIT_USER=admin
      - QBIT_PASS=your_password_here
      - QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
      
      # Enable features for testing
      - ENABLE_PREAIR_CHECK=1
      - # Pre-air checking for movies now uses ENABLE_PREAIR_CHECK (same as TV shows)
      - ENABLE_ISO_CHECK=1
      - SONARR_URL=http://sonarr:8989
      - SONARR_APIKEY=your_sonarr_api_key_here
      - RADARR_URL=http://radarr:7878
      - RADARR_APIKEY=your_radarr_api_key_here
    ```

    !!! danger "Dry Run Mode"
        This configuration runs in dry-run mode and won't actually delete torrents. Perfect for testing.

---

## :cloud: Kubernetes Examples

=== "ConfigMap"

    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: qbit-guard-config
    data:
      QBIT_HOST: "http://qbittorrent:8080"
      QBIT_USER: "admin"
      QBIT_ALLOWED_CATEGORIES: "tv-sonarr,radarr"
      ENABLE_PREAIR_CHECK: "1"
      SONARR_URL: "http://sonarr:8989"
      EARLY_GRACE_HOURS: "6"
      EARLY_HARD_LIMIT_HOURS: "72"
      INTERNET_CHECK_PROVIDER: "tvmaze"
      ENABLE_ISO_CHECK: "1"
      MIN_KEEPABLE_VIDEO_MB: "50"
      LOG_LEVEL: "INFO"
    ```

=== "Secret"

    ```yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: qbit-guard-secrets
    type: Opaque
    stringData:
      QBIT_PASS: "your_qbittorrent_password"
      SONARR_APIKEY: "your_sonarr_api_key"
      RADARR_APIKEY: "your_radarr_api_key"
      TVDB_APIKEY: "your_tvdb_api_key"
    ```

=== "Deployment"

    ```yaml
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: qbit-guard
    spec:
      replicas: 1
      selector:
        matchLabels:
          app: qbit-guard
      template:
        metadata:
          labels:
            app: qbit-guard
        spec:
          containers:
          - name: qbit-guard
            image: ghcr.io/gengines/qbit-guard:latest
            envFrom:
            - configMapRef:
                name: qbit-guard-config
            - secretRef:
                name: qbit-guard-secrets
            resources:
              limits:
                memory: "256Mi"
                cpu: "250m"
              requests:
                memory: "128Mi"
                cpu: "100m"
    ```

---

## :books: Next Steps

- **[Installation Guide →](usage/install.md)** - Set up your chosen configuration
- **[Configuration Guide →](usage/configure.md)** - Customize for your needs
- **[Troubleshooting →](troubleshooting.md)** - Fix common issues
- **[Environment Variables →](usage/env.md)** - Complete variable reference