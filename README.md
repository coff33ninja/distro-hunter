# Distro Hunter

Distro Hunter is a Windows-friendly Python tool that automates the discovery, downloading, and management of Linux distribution ISOs for Ventoy USB drives.

## 🚀 Features

- **Automatic Discovery**: Crawls official distro pages with pattern-based plugins to find the latest ISO releases
- **Smart Download**: Uses `aria2c` when available for fast, resumable downloads with automatic fallback to Python
- **Ventoy Integration**: Detects Ventoy USB drives and automatically copies updated ISOs to the correct folder structure
- **Plugin System**: Extensible architecture with built-in plugins for popular distributions and support for user-generated plugins
- **Health Monitoring**: Tracks download history, mirror health, and version changes for troubleshooting
- **Scheduled Tasks**: Designed to run cleanly from Windows Task Scheduler via PowerShell wrapper scripts
- **Interactive TUI**: Terminal User Interface for manual control and monitoring
- **Backup & Recovery**: Creates timestamped backups of configuration and plugin files
- **Validation & Reporting**: Validates downloaded ISOs against current releases and generates detailed reports

## 📦 What's Included

- **Core Engine**: Python modules for discovery, downloading, and Ventoy synchronization
- **Built-in Plugins**: Support for 50+ Linux distributions including:
  - Ubuntu family (Ubuntu, Kubuntu, Lubuntu, Xubuntu, Ubuntu Budgie, Ubuntu Cinnamon, Ubuntu MATE, Ubuntu Studio, Edubuntu)
  - Debian family (Debian Live variants, Netinst)
  - Fedora family (Workstation, KDE, Cinnamon, i3, Sway, LXQt, Mate Compiz, ARM64)
  - Arch-based (Arch Linux, EndeavourOS, Garuda, Manjaro, Nobara)
  - Enterprise (AlmaLinux, Rocky Linux)
  - Specialized (Alpine, ChimeraOS, FydeOS, Kali Linux, Pop!_OS, NixOS, SteamOS, SystemRescue, Zorin OS)
  - And many more...
- **External Plugin Support**: Add custom distros without modifying core code via `user_plugins` directory
- **Plugin Generator**: Create new plugins from webpage patterns with interactive review
- **PowerShell Scripts**: 
  - `Setup-DistroHunter.ps1` - Bootstraps Python virtual environment and dependencies
  - `Update-Ventoy.ps1` - Main execution script for scheduled tasks
  - `DistroHunter-Bootstrap.ps1` - Internal bootstrap utility
- **Comprehensive Test Suite**: Unit tests covering all major components
- **Example Files**: `config.example.json` for easy configuration

## 🔧 Quick Start

1. **Install Python 3.12 or newer** (64-bit recommended)

2. **Run the setup bootstrap once**:
   ```powershell
   .\Setup-DistroHunter.ps1
   ```

3. **Optional but recommended**: Leave `download.aria2_path` pointing at `tools/aria2/aria2c.exe` 
   (The first run will auto-download a portable `aria2c` if none is found)

4. **Configure your settings**:
   - Copy `config.example.json` to `config.json`
   - Edit for your download folder, Ventoy label, enabled plugins, and image extensions
   - The default plugin list is comprehensive - trim it if you don't need all distributions

5. **Test the installation**:
   ```powershell
   # List available plugins
   .\.venv\Scripts\python.exe -m distro_hunter list-plugins
   
   # Run a health check
   .\.venv\Scripts\python.exe -m distro_hunter doctor
   
   # Try a discovery run (dry run first)
   .\.venv\Scripts\python.exe -m distro_hunter run --dry-run
   
   # Launch the interactive TUI
   .\.venv\Scripts\python.exe -m distro_hunter tui
   ```

6. **Set up scheduled task** (optional but recommended):
   - Create a task that runs: `powershell.exe -ExecutionPolicy Bypass -File ".\Update-Ventoy.ps1"`
   - Configure triggers: daily, weekly, on workstation unlock, or at logon

## ⚙️ Configuration

Distro Hunter uses a JSON configuration file (default: `config.example.json`). Key sections:

```jsonc
{
  "download": {
    "download_dir": "downloads",                    // Where ISOs are stored locally
    "aria2_path": "tools/aria2/aria2c.exe",         // Path to aria2c executable
    "prefer_torrent": false,                        // Prefer torrents when available
    "retry_attempts": 3,                            // Download retry count
    "retry_backoff_seconds": 5,                     // Delay between retries
    "discovery_workers": 4                          // Parallel plugin discovery
  },
  "ventoy": {
    "enabled": true,                                // Enable Ventoy sync
    "label": "VENTOY",                              // Ventoy volume label to detect
    "copy_extensions": [".iso", ".img"],            // File types to copy
    "prune_removed": false                          // Remove old files from Ventoy
  },
  "logging": {
    "log_file": "logs/distro_hunter.log",           // Main log file
    "jsonl_log_file": null                          // JSONL log for automation (null = disabled)
  },
  "plugins": {
    "enabled": [],                                  // Empty = all built-in plugins
    "disabled": []                                  // Plugin slugs to disable
    // See config.example.json for profiles and overrides
  }
}
```

## 🧩 Plugin System

### Built-in Plugins
Located in `distro_hunter/plugins/`, each plugin is a Python file that:
- Defines a `NAME` constant for display
- Implements a `discover(context)` function returning `Candidate` objects
- Optionally specifies metadata like family, architecture, edition type

### User Plugins
Add custom distros by placing Python files in the `user_plugins/` directory. 
Use the generator to create starter plugins:

```powershell
# Generate a plugin from a webpage pattern
.\.venv\Scripts\python.exe -m distro_hunter generate-plugin `
  --name "My Distro" `
  --page-url "https://example.org/downloads/" `
  --include "iso" `
  --exclude "alpha|beta" `
  --with-test
```

### Plugin Metadata
Plugins can optionally define:
- `FAMILY` (e.g., "ubuntu", "fedora", "arch")
- `ARCHITECTURE` (e.g., "x86_64", "arm64", "universal")
- `EDITION_TYPE` (e.g., "desktop", "server", "minimal", "live")
- `SOURCE_KIND` (e.g., "official", "community", "third-party")

## 🔄 Workflow

When you run `distro_hunter run`:

1. **Discovery Phase**: 
   - Loads all enabled plugins (built-in + user)
   - Runs discovery in parallel to find latest ISO candidates
   - Applies scoring algorithms to pick best candidates
   - Persists selections to state file with version tracking

2. **Download Phase**:
   - Checks if selected ISO already exists locally
   - If not, attempts download using aria2c (with fallback to Python)
   - Supports resumable downloads via HTTP Range requests
   - Verifies checksums when available from source
   - Implements mirror failover with automatic backoff

3. **Ventoy Sync Phase**:
   - Detects Ventoy USB drive by volume label
   - Maps local ISOs to appropriate Ventoy folders based on:
     - Plugin-defined subdirectories
     - Auto-inferred paths from metadata
     - Manual source rules for custom files
   - Copies new/updated files, optionally pruning old ones

4. **Reporting Phase**:
   - Updates logs with human-readable and JSONL formats
   - Maintains history of selections, downloads, and health checks
   - Generates validation reports comparing local files to current releases

## 🛠️ Advanced Usage

### Command Line Interface
```powershell
# Core commands
.\.venv\Scripts\python.exe -m distro_hunter list-plugins    # Show available plugins
.\.venv\Scripts\python.exe -m distro_hunter doctor          # Health check all plugins
.\.venv\Scripts\python.exe -m distro_hunter discover        # Find latest ISOs
.\.venv\Scripts\python.exe -m distro_hunter download        # Download discovered ISOs
.\.venv\Scripts\python.exe -m distro_hunter sync            # Copy to Ventoy only
.\.venv\Scripts\python.exe -m distro_hunter run             # Full workflow (discover+download+sync)
.\.venv\Scripts\python.exe -m distro_hunter validate        # Check local vs current
.\.venv\Scripts\python.exe -m distro_hunter report          # Export status as JSON/CSV
.\.venv\Scripts\python.exe -m distro_hunter tui             # Interactive terminal UI
.\.venv\Scripts\python.exe -m distro_hunter backup          # Backup config/plugins
.\.venv\Scripts\python.exe -m distro_hunter generate-plugin # Create new plugin from webpage

# Common options
--plugin PLUGIN [PLUGIN...]    # Limit operations to specific plugins
--dry-run                      # Show actions without executing
--skip-sync                    # Skip Ventoy sync during run
--config FILE                  # Use custom config file
```

### PowerShell Integration
The included PowerShell scripts provide seamless integration:
- `Setup-DistroHunter.ps1`: Creates/updates virtual environment, installs dependencies
- `Update-Ventoy.ps1`: Main bootstrap that calls Setup then runs distro_hunter
- Both scripts automatically locate and use/ install portable aria2c

### Scheduled Task Tips
For reliable automated operation:
1. Set "Start in" to the Distro Hunter directory
2. Use highest privileges if Ventoy requires admin access
3. Consider "Run whether user is logged on or not" for server scenarios
4. Add a delay trigger at startup to avoid boot-time resource conflicts
5. Monitor logs/distro_hunter.log for operational insights

## 📁 Directory Structure

```
distro-hunter/
├── distro_hunter/              # Core Python package
│   ├── __init__.py
│   ├── __main__.py             # Entry point: python -m distro_hunter
│   ├── cli.py                  # Command-line interface
│   ├── core.py                 # Main orchestration logic
│   ├── config.py               # Configuration handling
│   ├── downloads.py            # Download management (aria2c + fallback)
│   ├── ventoy.py               # Ventoy detection and synchronization
│   ├── plugin_loader.py        # Plugin discovery and loading
│   ├── plugin_generator.py     # Create plugins from webpage patterns
│   ├── plugin_metadata.py      # Metadata inference and handling
│   ├── state.py                # Persistent state management (JSON)
│   ├── journal.py              # Logging (human-readable + JSONL)
│   ├── scoring.py              # Candidate ranking algorithms
│   ├── utils.py                # Helper functions
│   ├── exceptions.py           # Custom exception types
│   ├── run_lock.py             # Prevents overlapping scheduled runs
│   ├── startup_checks.py       # Pre-flight warnings
│   ├── tui.py                  # Terminal User Interface
│   └── plugins/                # Built-in distribution plugins
│       ├── __init__.py
│       ├── ubuntu_lts.py       # Example: Ubuntu LTS
│       ├── fedora_workstation.py # Example: Fedora Workstation
│       └── [50+ more plugin files]
├── user_plugins/               # Custom plugins go here
├── tools/                      # Portable tools (aria2c auto-downloaded here)
├── logs/                       # Runtime logs
├── backups/                    # Timestamped configuration backups
├── cache/                      # HTTP page cache for discovery
├── downloads/                  # Stored ISOs (configured)
├── state/                      # Persistent state files
├── tests/                      # Unit test suite
├── scripts/                    # PowerShell helper scripts
├── examples_adaptive_connections.py  # Adaptive networking demo
├── config.example.json         # Configuration template
├── README.md                   # This file
├── MISSING_DISTROS.md          # Tracking distros needing plugin work
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Build/package metadata
├── Setup-DistroHunter.ps1      # Environment bootstrap
└── Update-Ventoy.ps1           # Main execution script
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit Pull Requests for:

1. **New Distribution Plugins**: Add support for missing Linux distributions
2. **Core Improvements**: Enhance discovery algorithms, download reliability, or Ventoy integration
3. **Documentation**: Improve README, docstrings, or add usage examples
4. **Tests**: Expand test coverage for edge cases and error conditions
5. **Bug Fixes**: Report and fix issues you encounter

Please ensure new plugins follow the existing patterns and include appropriate metadata.

## ⚠️ Important Notes

- **Virtual Environment**: The tool is designed to run in its own Python virtual environment (`.venv`) managed by the PowerShell scripts
- **Anti-Virus**: Some AV software may flag ISO downloads - add exclusions for the downloads directory if needed
- **Network Usage**: Can download several GB per run - consider metered connections
- **Ventoy Format**: Requires Ventoy USB drive to be properly formatted and detected
- **First Run**: Initial setup may take several minutes as dependencies are installed and aria2c is downloaded

## 📄 License

Distro Hunter is open source software. See the LICENSE file for details.

## 🙏 Acknowledgments

- Thanks to the Ventoy project for making USB multi-boot simple and reliable
- Thanks to all the Linux distributions providing reliable download mirrors
- Thanks to the open-source Python community for libraries like requests, tqdm, and textual
- Special thanks to users who have contributed plugins and feedback

---

*Last updated: $(Get-Date -Format yyyy-MM-dd)*
*Version: See pyproject.toml for current release*