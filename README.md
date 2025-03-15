# gpus

A web interface for monitoring NVIDIA GPU status, similar to nvidia-smi but with a clean, intuitive web interface featuring real-time updates and historical data visualization.

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

## License

MIT License
Disclaimer: This was mostly a vibe-coded project. Use at your own risk.