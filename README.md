# Cligram

A powerful CLI-based Telegram client for automated message forwarding and group scanning, built with Python and Telethon.

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

Cligram is designed for small-scale university survey advertising and message distribution campaigns. It provides an intuitive command-line interface for scanning Telegram groups, identifying eligible users, and forwarding messages with intelligent rate limiting and proxy support.

## Features

- **Multiple Operation Modes**: Full automation, scan-only, send-only, and interactive modes
- **Proxy Support**: MTProto and SOCKS5 proxies with automatic failover
- **Beautiful Console Interface**: Rich terminal UI with status indicators and colored logging
- **State Management**: Persistent tracking of messaged users and scanning progress
- **Intelligent Rate Limiting**: Randomized delays with configurable thresholds to avoid flood limits
- **Incremental Scanning**: Resume scanning from where you left off with message window tracking
- **Safe Automation**: Test mode, rapid state saving, and graceful shutdown handling

## Installation

### Requirements

- Python 3.12 or higher
- Telegram API credentials (API ID and Hash from [my.telegram.org](https://my.telegram.org/apps))

### Install

Install with pip

```bash
pip install cligram
```

## Quick Start

### 1. Create Configuration

```bash
# Create a global configuration file, this will be stored in ~/.cligram/config.json
cligram config create --global

# Or create a local configuration file
cligram config create config.json
```

### 2. Add Your Telegram API Credentials

By default, the config create command asks for your API credentials during setup.
But if you skipped that step, you must manually add them.

Open the configuration file and add your API credentials:

```json
{
  "telegram": {
    "api": {
      "id": YOUR_API_ID,
      "hash": "YOUR_API_HASH"
    }
  }
}
```

### 3. Login to Telegram

```bash
cligram session login
```

## Usage

### Scan mode

The scan mode is under a heavy refactor and improvement. I recommend not to use it for now.
But if you want to try it, you must enable verbose logging to see any output.

```bash
cligram -v run
```

I consider finishing it and then writing proper documentation for it in the future.

### Interactive Mode

```bash
# Start interactive session
cligram interactive

# Use specific session
cligram interactive --session my_account
```

### Configuration Management

```bash
# List all configuration values
cligram config list

# Get a specific value
cligram config get telegram.api.id

# Set a configuration value
cligram config set scan.limit 100

# Override config values at runtime
cligram --override "interactive.mode=python" interactive
```

### Session Management

```bash
# Login to a new
cligram session login [session_name]

# List all available sessions
cligram session list

# Logout and delete session (maybe buggy)
cligram -v run --mode logout
```

### Proxy Management

cligram supports both MTProto and SOCKS5 proxies.
It supports 2 custom link formats and standard mtproto proxy links.
You can manage your proxies using the following commands:

```bash
# Add a proxy
cligram proxy add "socks5://user:pass@host:port"
cligram proxy add "mtproto://secret@host:port"

# Add multiple proxies
cligram proxy add "socks5://proxy1:1080" "socks5://proxy2:1080"

# List configured proxies
cligram proxy list

# Test all proxies
cligram proxy test

# Remove a proxy
cligram proxy remove "socks5://host:port"

# Remove all unreachable proxies
cligram proxy remove --unreachable

# Remove all proxies
cligram proxy remove --all
```

## Configuration

### Key Configuration Options

- **`app.delays`**: Configure delay intervals between operations
- **`telegram.api`**: Your Telegram API credentials
- **`telegram.connection`**: Proxy and connection settings
- **`scan.messages.source`**: Source chat for forwarding messages (use `"me"` for Saved Messages)
- **`scan.targets`**: List of group usernames or URLs to scan
- **`scan.limit`**: Maximum messages to scan per group
- **`scan.test`**: Enable test mode (no actual messages sent)
- **`scan.rapid_save`**: Save state after each processed user

### Configuration Locations

Cligram searches for configuration files in the following order:

1. Current working directory: `./config.json`
2. Global configuration: `~/.cligram/config.json`

## State Management

Cligram maintains persistent state in the `data/` directory:

States are automatically saved during operation and backed up after each run.

## Use Cases

- University survey distribution
- Event announcements to group members
- Research participant recruitment
- Community engagement campaigns

**DO NOT USE FOR MASS SPAM OR HARASSMENT PURPOSES.** Misuse may lead to account restrictions.
Also this tool is not optimized for that purpose and may result in poor performance.
User records and built in delays is not designed for high-volume spamming.

## Troubleshooting

### Common Issues

#### "Session not found"

- Run `cligram session login` to create a new session
- Check session file exists in the sessions directory

#### "No working connection available"

- Verify your internet connection
- Test proxies with `cligram proxy test`
- Enable direct connection in config: `"direct": true`

#### "FloodWaitError"

- Telegram rate limit exceeded
- Increase delay intervals in configuration
- Wait for the specified time before retrying

#### "Configuration file not found"

- Create config with `cligram config create`
- Specify config path: `cligram -c /path/to/config.json interactive`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is intended for legitimate use cases such as university surveys and announcements. Users are responsible for complying with Telegram's Terms of Service and applicable laws. Misuse of this tool for spam or harassment is strictly prohibited and may result in account restrictions.

## Credits

- Built with [Telethon](https://github.com/LonamiWebs/Telethon) Telegram client library
- CLI powered by [Typer](https://github.com/tiangolo/typer), a modern and easy to use CLI library
- Beautiful terminal UI with [Rich](https://github.com/Textualize/rich)
