# GPUs

![PyPI - Downloads](https://img.shields.io/pypi/dm/gpus) ![GitHub License](https://img.shields.io/github/license/fakerybakery/gpus) ![GitHub commit activity](https://img.shields.io/github/commit-activity/m/fakerybakery/gpus)


A real-time web interface for monitoring NVIDIA GPUs.

```bash
pip install gpus
gpus start
```

![gpus_demo](https://github.com/user-attachments/assets/4f92d8b0-2937-4cdd-947f-9366d11370a1)

## Features

- Real-time monitoring of NVIDIA GPU statistics
- Clean, modern, responsive web interface
- Historical utilization graphs
- Process monitoring
- Command-line interface
- Background server mode

## Requirements

- Python 3.6+
- NVIDIA GPU with installed drivers
- NVIDIA Management Library (NVML)

## Installation

```bash
pip install gpus
```

## Usage

### Starting the Web Interface

```bash
# Start the web interface in the foreground (default port 5000)
gpus

# Specify a different port
gpus --port 8080
# or with the short option
gpus -P 8080

# Specify update interval (in seconds)
gpus --update-interval 2.0
# or with the short option
gpus -U 2.0

# Specify history length (in seconds)
gpus --history-length 600
# or with the short option
gpus -L 600

# Specify history resolution (in seconds)
gpus --history-resolution 1.0
# or with the short option
gpus -R 1.0
```

Then open your web browser and navigate to `http://localhost:5000` (or the port you specified).

### Managing Background Server

You can run the server in the background and manage it with subcommands:

```bash
# Start the server in the background
gpus start

# Check if the server is running
gpus status

# Stop the background server
gpus stop
```

The background server uses the same command-line options as the foreground server:

```bash
# Start the background server on a specific port
gpus -P 8080 start
```

### Using as a Python Package

```python
from gpus.app import GPUMonitorApp

# Create the application
app = GPUMonitorApp(
    update_interval=2.0,
    history_length=300,
    history_resolution=1.0
)

# Run the application
app.run(host='0.0.0.0', port=5000)
```

## Cloud

GPUs Cloud is a free cloud service that allows you to easily manage your GPUs on-the-go. Remotely monitor your GPUs from anywhere & get notified when your training runs fail (coming soon).

> [!WARNING]
> GPUs Cloud is currently in a limited beta stage. If you want early access (highly unstable), please [DM me on X](https://x.com/realmrfakename) for an invite code. Expect some bugs, limited features, and high downtime.

### Getting Started

Sign up for a free account (using Hugging Face login) on the [GPUs Cloud website](https://gpus.mrfake.name). Enter your invite code and add a device. Then run the following command to login:

```bash
gpus cloud login
```

To start sending GPU metrics to the cloud (in the background), run the following command:

```bash
gpus cloud start
```

To stop sending GPU metrics to the cloud, run the following command:

```bash
gpus cloud stop
```

To check the status of the cloud client, run the following command:

```bash
gpus cloud status
```

To send metrics to the cloud (in the foreground), run the following command:

```bash
gpus cloud
```

To logout of the cloud, run the following command:

```bash
gpus cloud logout
```

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/fakerybakery/gpus
cd gpus

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .
```

## Debugging

If you encounter issues, please check the logs in the `~/.gpus` directory. If the problem persists, please [create an issue](https://github.com/fakerybakery/gpus/issues) on GitHub.

Note that GPUs has not been tested on Windows. Use at your own risk.

## License

BSD-3-Clause
