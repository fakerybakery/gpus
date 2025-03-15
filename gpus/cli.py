"""
Command-line interface for GPU monitoring web application
"""

import os
import sys
import signal
import click
import psutil
import time
import socket
import json
from pathlib import Path

from gpus.app import GPUMonitorApp


# Constants for server management
PID_FILE = Path(os.path.expanduser("~/.gpus/gpus.pid"))
CONFIG_FILE = Path(os.path.expanduser("~/.gpus/config.json"))


@click.group(invoke_without_command=True)
@click.option('--host', '-H', default='0.0.0.0', help='Host to bind to')
@click.option('--port', '-P', default=5000, help='Port to bind to')
@click.option('--update-interval', '-U', default=2.0, help='Update interval in seconds')
@click.option('--history-length', '-L', default=300, help='History length in seconds')
@click.option('--history-resolution', '-R', default=1.0, help='Resolution of history in seconds')
@click.option('--debug/--no-debug', default=False, help='Enable debug mode')
@click.pass_context
def cli(ctx, host, port, update_interval, history_length, history_resolution, debug):
    """GPU Monitoring Web Interface
    
    Run without subcommands to start the server in the foreground.
    Use subcommands to manage a background server:
    
    \b
    gpus start    # Start server in background
    gpus stop     # Stop background server
    gpus status   # Check if server is running
    """
    # Store options in context
    ctx.ensure_object(dict)
    ctx.obj['host'] = host
    ctx.obj['port'] = port
    ctx.obj['update_interval'] = update_interval
    ctx.obj['history_length'] = history_length
    ctx.obj['history_resolution'] = history_resolution
    ctx.obj['debug'] = debug
    
    # If no subcommand is specified, run the server in the foreground
    if ctx.invoked_subcommand is None:
        run_server(host, port, update_interval, history_length, history_resolution, debug)


@cli.command()
@click.pass_context
def start(ctx):
    """Start the GPU monitoring server in the background"""
    # Check if server is already running
    if is_server_running():
        pid = get_server_pid()
        click.echo(f"Server is already running (PID: {pid})")
        return
    
    # Create directory for pid file if it doesn't exist
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Store configuration
    config = {
        'host': ctx.obj['host'],
        'port': ctx.obj['port'],
        'update_interval': ctx.obj['update_interval'],
        'history_length': ctx.obj['history_length'],
        'history_resolution': ctx.obj['history_resolution'],
        'debug': ctx.obj['debug']
    }
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    
    # Start the server as a separate process
    if os.name == 'posix':  # Unix/Linux/MacOS
        # Use double fork to detach from terminal
        pid = os.fork()
        if pid > 0:
            # Parent process, wait for child to exit
            os.waitpid(pid, 0)
            # Check if server started successfully
            time.sleep(1)
            if is_server_running():
                server_pid = get_server_pid()
                click.echo(f"Server started in background (PID: {server_pid})")
                click.echo(f"Access the web interface at http://{ctx.obj['host']}:{ctx.obj['port']}")
            else:
                click.echo("Failed to start server")
            return
        
        # First child process
        os.setsid()  # Become session leader
        pid = os.fork()
        if pid > 0:
            # Exit first child
            sys.exit(0)
        
        # Second child process (daemon)
        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        with open(os.devnull, 'r') as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
        with open(os.devnull, 'a+') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())
        
        # Write PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        
        # Run the server
        run_server(
            ctx.obj['host'],
            ctx.obj['port'],
            ctx.obj['update_interval'],
            ctx.obj['history_length'],
            ctx.obj['history_resolution'],
            ctx.obj['debug']
        )
    else:  # Windows
        click.echo("Background server not supported on Windows. Please run 'gpus' without subcommands.")


@cli.command()
def stop():
    """Stop the background GPU monitoring server"""
    if not is_server_running():
        click.echo("No server is running")
        return
    
    pid = get_server_pid()
    try:
        # Send SIGTERM to the process
        os.kill(pid, signal.SIGTERM)
        
        # Wait for process to terminate
        for _ in range(10):  # Wait up to 5 seconds
            if not is_pid_running(pid):
                break
            time.sleep(0.5)
        
        # If process is still running, force kill
        if is_pid_running(pid):
            os.kill(pid, signal.SIGKILL)
            click.echo(f"Server (PID: {pid}) forcefully terminated")
        else:
            click.echo(f"Server (PID: {pid}) stopped")
        
        # Remove PID file
        PID_FILE.unlink(missing_ok=True)
    except OSError as e:
        click.echo(f"Error stopping server: {e}")
        # Clean up PID file if process doesn't exist
        if not is_pid_running(pid):
            PID_FILE.unlink(missing_ok=True)
            click.echo("Removed stale PID file")


@cli.command()
def status():
    """Check if the GPU monitoring server is running"""
    if is_server_running():
        pid = get_server_pid()
        
        # Get server info from config file
        config = {}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                pass
        
        host = config.get('host', '0.0.0.0')
        port = config.get('port', 5000)
        
        click.echo(f"Server is running (PID: {pid})")
        click.echo(f"Access the web interface at http://{host}:{port}")
        
        # Check if port is actually in use
        if is_port_in_use(port):
            click.echo(f"Port {port} is active")
        else:
            click.echo(f"Warning: Port {port} is not active, server may not be responding")
    else:
        click.echo("No server is running")


def run_server(host, port, update_interval, history_length, history_resolution, debug):
    """Run the GPU monitoring server"""
    click.echo(f"Starting GPU monitoring web server on {host}:{port}")
    app = GPUMonitorApp(
        update_interval=update_interval,
        history_length=history_length,
        history_resolution=history_resolution
    )
    app.run(host=host, port=port, debug=debug)


def is_server_running():
    """Check if the server is running"""
    if not PID_FILE.exists():
        return False
    
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        return is_pid_running(pid)
    except (ValueError, IOError):
        return False


def get_server_pid():
    """Get the PID of the running server"""
    if not PID_FILE.exists():
        return None
    
    try:
        with open(PID_FILE, 'r') as f:
            return int(f.read().strip())
    except (ValueError, IOError):
        return None


def is_pid_running(pid):
    """Check if a process with the given PID is running"""
    try:
        # Check if process exists
        process = psutil.Process(pid)
        return process.is_running()
    except psutil.NoSuchProcess:
        return False


def is_port_in_use(port, host='127.0.0.1'):
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            s.connect((host, port))
            return True
        except (socket.error, socket.timeout):
            return False


if __name__ == '__main__':
    cli() 