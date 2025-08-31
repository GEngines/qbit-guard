# <img alt="qbit-guard logo" src="https://gengines.github.io/qbit-guard/img/qbit-guard-icon.png"> Development Guide

This guide covers development setup, testing procedures, debugging techniques, and troubleshooting for qbit-guard.

---

## Development Setup

### Prerequisites

- **Python 3.8+** with standard library
- **Docker** and **Docker Compose** for testing
- **qBittorrent** instance for testing (can be containerized)
- Access to **Sonarr/Radarr** instances (optional, for integration testing)

### Local Development

1. **Clone the repository**:
   ```bash
   git clone https://github.com/GEngines/qbit-guard.git
   cd qbit-guard
   ```

2. **Set up environment variables** for testing:
   ```bash
   export QBIT_HOST=http://localhost:8080
   export QBIT_USER=admin
   export QBIT_PASS=adminadmin
   export QBIT_ALLOWED_CATEGORIES=test
   export QBIT_DRY_RUN=1  # Important for testing
   export LOG_LEVEL=DEBUG
   ```

3. **Run the script directly**:
   ```bash
   cd src
   python3 guard.py <torrent_id> <category>
   ```

4. **Or test the watcher**:
   ```bash
   cd src  
   python3 watcher.py
   ```

### Container Development

1. **Build local image**:
   ```bash
   docker build -t qbit-guard:dev .
   ```

2. **Test with docker-compose**:
   ```bash
   # Use the provided docker-compose.yml
   docker-compose up qbit-guard
   ```

---

## Testing Procedures

### Unit Testing

The project uses Python's built-in testing capabilities:

```bash
# Test configuration loading
python3 -c "
import sys
sys.path.append('src')
import guard
# Test environment variable parsing
print('Config loaded successfully')
"
```

### Integration Testing

1. **Test qBittorrent Connection**:
   ```bash
   # Verify API connectivity
   curl -u admin:password http://localhost:8080/api/v2/app/version
   ```

2. **Test with Dry Run**:
   ```bash
   QBIT_DRY_RUN=1 LOG_LEVEL=DEBUG python3 src/guard.py test_torrent test_category
   ```

3. **Test Pre-air Checking**:
   ```bash
   ENABLE_PREAIR_CHECK=1 SONARR_URL=http://localhost:8989 SONARR_APIKEY=your_key QBIT_DRY_RUN=1 python3 src/guard.py test_torrent tv-sonarr
   ```

### Manual Testing Scenarios

1. **Add a test torrent** in qBittorrent with correct category
2. **Monitor logs** for processing behavior
3. **Test different categories** and configuration combinations
4. **Simulate network issues** by using unreachable service URLs

---

## Debugging Techniques

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG
```

Debug mode provides detailed information about:
- HTTP request/response details
- Sonarr/Radarr API communication
- File analysis decisions  
- Whitelist matching logic
- Metadata fetch progress

### Enhanced Extension Logging

For detailed extension blocking information without full debug output:

```bash
LOG_LEVEL=DETAILED
```

DETAILED mode provides:
- All INFO-level messages
- Enhanced extension policy summaries showing:
  - Count of blocked files per extension type
  - Example filenames for each blocked extension (up to 5 examples)
  - Clear breakdown of why torrents are being blocked

Example DETAILED output:
```
2025-01-15 12:00:00 | INFO | Ext policy: 8/12 file(s) disallowed. e.g., movie.iso
2025-01-15 12:00:00 | DETAILED | Extension policy details: .iso: 3 files ("movie.iso", "disc2.iso", "extras.iso"); .exe: 2 files ("setup.exe", "crack.exe"); .rar: 3 files ("archive1.rar", "archive2.rar", "backup.rar")
```

This level is perfect for diagnosing extension policy issues without the verbosity of full DEBUG logging.

### Key Log Indicators

Monitor these log messages:

**Success Indicators:**
- ✅ `qB: login OK` - qBittorrent authentication successful
- ✅ `Started torrent ... after checks` - Normal processing completed
- ✅ `Torrent allowed` - Torrent passed all checks

**Expected Behavior:**
- ⚠️ `Pre-air: BLOCK` - Pre-air blocking working correctly
- ⚠️ `ISO cleanup: removing` - Disc image cleanup working

**Error Indicators:**
- ❌ `Unhandled error` - Configuration or connectivity issue
- ❌ `qB: login failed` - Authentication problem
- ❌ `Timeout` - Network connectivity issues

### Network Debugging

1. **Test API connectivity** from the container:
   ```bash
   docker-compose exec qbit-guard wget -qO- http://qbittorrent:8080/api/v2/app/version
   docker-compose exec qbit-guard wget -qO- http://sonarr:8989/api/v3/system/status
   ```

2. **Check DNS resolution**:
   ```bash
   docker-compose exec qbit-guard nslookup qbittorrent
   docker-compose exec qbit-guard nslookup sonarr
   ```

3. **Verify network connectivity**:
   ```bash
   docker-compose exec qbit-guard ping qbittorrent
   docker network inspect $(docker-compose config --volumes)
   ```

---

## Common Development Issues

### Environment Variable Issues

**Problem**: Variables not being read
```bash
# Check environment in container
docker-compose exec qbit-guard printenv | grep QBIT_
```

**Solution**: Ensure variables are properly set in docker-compose.yml or environment

### qBittorrent Connection Issues

**Problem**: Cannot connect to qBittorrent
- Verify `QBIT_HOST` is accessible from qbit-guard container
- Check qBittorrent WebUI is enabled
- Confirm username/password are correct
- Test with `curl` from inside the container

### API Timeout Issues

**Problem**: Sonarr/Radarr API calls timing out
- Increase timeout values: `SONARR_TIMEOUT_SEC=90`
- Use direct container IPs instead of service names
- Avoid routing through reverse proxies for API calls
- Check network latency between containers

### Metadata Fetch Issues

**Problem**: Magnet metadata never loads
- Check qBittorrent logs for tracker/DHT issues
- Increase `METADATA_MAX_WAIT_SEC` or set to 0 for infinite wait
- Verify magnet has sufficient seeds/peers
- Try reducing `METADATA_POLL_INTERVAL` to 0.5 for faster checking

---

## Performance Optimization

### Resource Limits

For production deployments, set appropriate resource limits:

```yaml
services:
  qbit-guard:
    deploy:
      resources:
        limits:
          memory: 512M        # qbit-guard is lightweight
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.1'
```

### Polling Optimization

**Reduce polling frequency** for lower resource usage:
```bash
WATCH_POLL_SECONDS=10.0  # Check every 10 seconds instead of 3
```

**Optimize metadata fetching**:
```bash
METADATA_MAX_WAIT_SEC=120              # 2 minute timeout
METADATA_DOWNLOAD_BUDGET_BYTES=52428800  # 50MB limit
```

---

## Contributing Guidelines

### Code Style

- Follow Python PEP 8 style guidelines
- Use meaningful variable names
- Add comments for complex logic
- Keep functions focused and small

### Documentation

- Update this guide when adding new features
- Include examples in configuration changes
- Document new environment variables
- Update README.md if adding major features

### Testing

- Test with `QBIT_DRY_RUN=1` first
- Verify both container and script modes work
- Test with different qBittorrent versions (4.x and 5.x)
- Test network failure scenarios

### Pull Request Process

1. **Test thoroughly** with dry-run mode
2. **Update documentation** for any new features
3. **Include example configurations** for new variables
4. **Test both deployment modes** (container and script)

---

## Troubleshooting Development Issues

### Container Won't Start

```bash
# Check container logs
docker-compose logs qbit-guard

# Common causes:
# - Invalid environment variables
# - Network connectivity issues  
# - Missing required variables
```

### Script Execution Issues

```bash
# Check Python version
python3 --version  # Must be 3.8+

# Verify script permissions
ls -la src/guard.py
chmod +x src/guard.py

# Test with minimal config
QBIT_DRY_RUN=1 python3 src/guard.py test test
```

### API Authentication Issues

```bash
# Test qBittorrent WebUI access
curl -u admin:password http://localhost:8080/api/v2/app/version

# Test Sonarr API access  
curl -H "X-Api-Key: your_api_key" http://localhost:8989/api/v3/system/status

# Test Radarr API access
curl -H "X-Api-Key: your_api_key" http://localhost:7878/api/v3/system/status
```

---

## Next Steps

- **[Configuration Guide →](configure.md)** - Detailed setup instructions
- **[Troubleshooting →](../troubleshooting.md)** - Production troubleshooting guide
- **[Examples →](../examples.md)** - Working development configurations
