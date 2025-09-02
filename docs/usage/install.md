# <img alt="qbit-guard logo" src="../../img/qbit-guard-icon.png"> Installation Guide

qbit-guard can be deployed in two ways: as a **containerized service** (recommended) or as a **traditional script**. Choose the method that best fits your setup.

---

## Docker Installation (Recommended)

The containerized version runs as a standalone service that continuously monitors qBittorrent, eliminating the need for webhook configuration.

### Prerequisites

- **Docker** and **Docker Compose** installed
  - **Linux/macOS**: [Install Docker Engine](https://docs.docker.com/engine/install/) and [Docker Compose](https://docs.docker.com/compose/install/)
  - **Windows**: [Install Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) (includes Docker Compose)
- **qBittorrent** accessible over the network
- **Sonarr/Radarr** accessible over the network (optional but recommended)
- Network connectivity between all services

### Quick Start

1. **Pull the official image**:
   ```bash
   # Linux/macOS/Windows (PowerShell/Command Prompt)
   docker pull ghcr.io/gengines/qbit-guard:latest
   ```

2. **Create a basic docker-compose.yml**:
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
         - QBIT_PASS=your_password
         - QBIT_ALLOWED_CATEGORIES=tv-sonarr,radarr
         - ENABLE_PREAIR_CHECK=1
         - SONARR_URL=http://sonarr:8989
         - SONARR_APIKEY=your_api_key
         - LOG_LEVEL=INFO
       networks:
         - arr-network
   
   networks:
     arr-network:
       driver: bridge
   ```

3. **Start the service**:
   ```bash
   # Linux/macOS/Windows (PowerShell/Command Prompt)
   docker-compose up -d
   ```

### Container Modes

**Polling Mode (Default)**: The container continuously polls qBittorrent's API for new torrents. This is the recommended approach as it:
- Requires no qBittorrent webhook configuration
- Works reliably across container restarts
- Handles network interruptions gracefully
- Provides better visibility into processing status

**Webhook Mode**: Configure qBittorrent to call the container on torrent add events. This requires:
- Exposing the container port (`8080:8080`)
- Configuring qBittorrent's "Run external program" setting to call `http://qbit-guard:8080/webhook`
- Additional network connectivity setup
- More complex debugging when issues arise

For most users, polling mode is simpler and more reliable.

### UNRAID Deployment

For UNRAID users, qbit-guard is available through the Community Applications plugin, making installation even easier:

#### Option 1: Official qbit-guard Container

1. **Install via Community Applications**:
   - Open the UNRAID web interface
   - Navigate to **Apps** tab  
   - Search for **"qbit-guard"**
   - Click **Install** on the official qbit-guard container

2. **Configure the container**:
   - **Repository**: `ghcr.io/gengines/qbit-guard:latest`
   - **Network Type**: `bridge` (or your preferred network)
   - **Environment Variables**: Configure as needed (see [Environment Variables](env.md))

#### Option 2: binhex's qbit-guard Container

As an alternative, you can use binhex's version which uses the same underlying image:

1. **Install via Community Applications**:
   - Open the UNRAID web interface  
   - Navigate to **Apps** tab
   - Search for **"binhex-qbit-guard"**
   - Click **Install** on binhex's qbit-guard container

2. **Configure the container**:
   - Uses the same `ghcr.io/gengines/qbit-guard` image
   - May have pre-configured UNRAID-specific settings
   - Environment variables work identically

#### UNRAID-Specific Benefits

- **GUI Configuration**: UNRAID's template system provides a user-friendly interface for all environment variables
- **Integration**: Seamlessly integrates with other UNRAID containers (qBittorrent, Sonarr, Radarr)
- **Docker Management**: Built-in container management, logging, and monitoring
- **Network Isolation**: Easy network configuration and container communication
- **Auto-updates**: Automatic container updates when new versions are released

Both containers use the same official image and provide identical functionality - choose whichever fits your preference or existing UNRAID setup.

### Windows-Specific Considerations

When running Docker containers on Windows, consider these additional points:

- **Volume Mounts**: Windows paths in docker-compose.yml should use forward slashes or escaped backslashes:
  ```yaml
  # Correct Windows path syntax
  volumes:
    - "C:/qbit-guard/config:/config"
    # or
    - "C:\\qbit-guard\\config:/config"
  ```

- **Network Connectivity**: If running qBittorrent natively on Windows (not in Docker), use `host.docker.internal` instead of `localhost` or `127.0.0.1` to access it from containers:
  ```yaml
  environment:
    - QBIT_HOST=http://host.docker.internal:8080
  ```

- **Docker Desktop Settings**: Ensure "Use Docker Compose V2" is enabled in Docker Desktop settings for better compatibility.

### Network Requirements

qbit-guard needs network connectivity to your services:

- **qBittorrent API**: HTTP access to qBittorrent's Web UI (default port 8080)
- **Sonarr API**: HTTP access to Sonarr (default port 8989)
- **Radarr API**: HTTP access to Radarr (default port 7878)  
- **Internet APIs**: HTTPS access to TVmaze and TheTVDB for cross-verification

#### Docker Compose Networking

Create a shared network for all services:

```yaml
networks:
  arr-network:
    driver: bridge
```

All services (qbit-guard, qbittorrent, sonarr, radarr) should use the same network to enable service discovery by container name.

---

## Script Installation (Traditional)

For users who prefer the traditional webhook approach or need to customize the deployment:

### Prerequisites

- **Python 3.8+** installed
  - **Linux/macOS**: Install via package manager or [python.org](https://www.python.org/downloads/)
  - **Windows**: Download from [python.org](https://www.python.org/downloads/windows/) and ensure "Add Python to PATH" is checked during installation
- **qBittorrent** with WebUI enabled
- **Sonarr/Radarr** accessible (optional)

### Installation Steps

1. **Download and make executable**:

   **Linux/macOS:**
   ```bash
   curl -o /config/scripts/qbit-guard.py https://raw.githubusercontent.com/GEngines/qbit-guard/main/src/guard.py
   chmod +x /config/scripts/qbit-guard.py
   ```

   **Windows (PowerShell):**
   ```powershell
   # Create the scripts directory in user profile
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\qbit-guard\scripts"
   
   # Download the script
   Invoke-WebRequest -Uri "https://raw.githubusercontent.com/GEngines/qbit-guard/main/src/guard.py" -OutFile "$env:USERPROFILE\qbit-guard\scripts\qbit-guard.py"
   ```

   **Windows (Command Prompt with curl):**
   ```cmd
   mkdir "%USERPROFILE%\qbit-guard\scripts" 2>nul
   curl -o "%USERPROFILE%\qbit-guard\scripts\qbit-guard.py" https://raw.githubusercontent.com/GEngines/qbit-guard/main/src/guard.py
   ```

   **Manual Download (All Platforms):**
   
   If you prefer to download manually or the above commands don't work:
   
   1. **Create the directory structure**:
      - **Linux/macOS**: `/config/scripts/`
      - **Windows**: `%USERPROFILE%\qbit-guard\scripts\` (typically `C:\Users\YourUsername\qbit-guard\scripts\`)
   
   2. **Download the script file**:
      - Open [https://raw.githubusercontent.com/GEngines/qbit-guard/main/src/guard.py](https://raw.githubusercontent.com/GEngines/qbit-guard/main/src/guard.py) in your browser
      - Right-click → "Save As..." and save the file as `qbit-guard.py` in the directory you created above
   
   3. **Linux/macOS only**: Make the script executable:
      ```bash
      chmod +x /config/scripts/qbit-guard.py
      ```

2. **Configure qBittorrent**:
   - Navigate to **Options** → **Downloads** → **Run external program**
   - **Run on torrent added**:
   
     **Linux/macOS:**
     ```bash
     /usr/bin/python3 /config/scripts/qbit-guard.py %I %L
     ```
     
     **Windows:**
     ```cmd
     python "%USERPROFILE%\qbit-guard\scripts\qbit-guard.py" %I %L
     ```
     
     > **Note for Windows**: Use the full path to python.exe if `python` command is not in PATH:
     > ```cmd
     > "C:\Python39\python.exe" "%USERPROFILE%\qbit-guard\scripts\qbit-guard.py" %I %L
     > ```
   
   - **Important**: Remove any existing "Run on torrent added" scripts to avoid conflicts

3. **Set environment variables** in your container/docker-compose file

4. **Restart qBittorrent**

### Windows Troubleshooting

Common issues and solutions for Windows users:

- **Python not found**: Ensure Python is installed and added to PATH. Test with `python --version` in Command Prompt.
- **Script execution policy**: If using PowerShell and getting execution policy errors:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- **File permissions**: Windows doesn't require `chmod`, but ensure the script file is not marked as blocked. Right-click → Properties → General → Unblock if present.
- **Path separators**: Always use forward slashes in URLs and environment variables, even on Windows.
- **qBittorrent service account**: If running qBittorrent as a Windows service, ensure it has permission to execute the Python script.

### Script Mode vs Container Mode

| Feature | Container Mode | Script Mode |
|---------|---------------|-------------|
| **Setup Complexity** | Simple | Moderate |
| **Webhook Required** | No | Yes |
| **Continuous Monitoring** | Yes | Per-torrent |
| **Container Restarts** | Graceful | Manual reconfig |
| **Resource Usage** | Single process | Per-execution |
| **Debugging** | Centralized logs | Per-execution logs |
| **Recommended For** | Most users | Advanced setups |

---

## Next Steps

After installation, proceed to:

- **[Configuration Guide →](configure.md)** - Configure qBittorrent integration, Sonarr/Radarr, and other features
- **[Environment Variables →](env.md)** - Complete reference of all configuration options
- **[Examples →](../examples.md)** - Working Docker Compose and Kubernetes examples

> **Tip**: A complete working `docker-compose.yml` file is included in the repository root with all configuration options documented.
