"""
Cloud client for sending GPU statistics to the GPUs Cloud service
"""

import json
import os
import platform
import subprocess
import re
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
import signal
import sys

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint

from gpus.gpu_stats import GPUStats

# Constants
CONFIG_DIR = Path(os.path.expanduser("~/.gpus"))
TOKEN_FILE = CONFIG_DIR / "cloud_token.json"
PID_FILE = CONFIG_DIR / "cloud_client.pid"
SERVER_URL = "https://gpus.mrfake.name/api"

console = Console()


def get_system_info():
    """Get system information to report to server"""
    info = {
        "os_type": platform.system(),
        "os_version": platform.version(),
        "hostname": platform.node(),
        "cpu_info": platform.processor()
    }
    return info


def get_driver_and_cuda_version():
    """Get NVIDIA driver and CUDA version"""
    driver_version = None
    cuda_version = None
    
    try:
        # Get driver version
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]).decode('utf-8')
        if output.strip():
            driver_version = output.strip().split('\n')[0]
        
        # Get CUDA version
        output = subprocess.check_output(["nvidia-smi", "--query", "--display=COMPUTE"]).decode('utf-8')
        cuda_match = re.search(r'CUDA Version\s+:\s+([\d\.]+)', output)
        if cuda_match:
            cuda_version = cuda_match.group(1).strip()
    except Exception:
        pass
    
    return driver_version, cuda_version


class CloudClient:
    """Client for interacting with the GPUs Cloud service"""
    
    def __init__(self, server_url=None, update_interval=5.0):
        """
        Initialize the cloud client
        
        Args:
            server_url: URL of the GPUs Cloud server
            update_interval: Interval in seconds between metric updates
        """
        self.server_url = server_url or SERVER_URL
        self.update_interval = update_interval
        self.access_token = None
        self.device_id = None
        self.gpu_stats = GPUStats()
        self.running = False
        self.update_thread = None
        self.connected = False
        self.last_heartbeat_time = None
        self.heartbeat_interval = 60  # Send heartbeat every 60 seconds
        self.foreground_mode = False  # Track if running in foreground mode
        
        # Load the access token if it exists
        self._load_token()
    
    def _load_token(self):
        """Load the access token from file"""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.device_id = data.get('device_id')
                    return True
            except (json.JSONDecodeError, IOError) as e:
                console.print(f"[yellow]Warning: Failed to load token file: {e}[/yellow]")
        return False
    
    def _save_token(self, access_token, device_id):
        """Save the access token to file"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    'access_token': access_token,
                    'device_id': device_id,
                    'created_at': datetime.now().isoformat()
                }, f)
            # Set appropriate permissions (read/write for owner only)
            os.chmod(TOKEN_FILE, 0o600)
            return True
        except IOError as e:
            console.print(f"[red]Error saving token file: {e}[/red]")
            return False
    
    def logout(self):
        """
        Logout from the GPUs Cloud service by deleting the token file
        
        Returns:
            bool: True if logout was successful, False otherwise
        """
        # Check if a cloud client is running
        if is_cloud_client_running():
            rprint("[red]Error: Cloud client is currently running. Please stop it first with 'gpus cloud stop'[/red]")
            return False
        
        # Check if token file exists
        if not TOKEN_FILE.exists():
            rprint("[yellow]You are not currently logged in[/yellow]")
            return False
        
        # Get device ID for confirmation message
        device_id = None
        try:
            with open(TOKEN_FILE, 'r') as f:
                data = json.load(f)
                device_id = data.get('device_id')
        except:
            pass
        
        # Confirm logout
        if device_id:
            confirmed = Confirm.ask(f"Are you sure you want to logout device [bold]{device_id}[/bold]?")
        else:
            confirmed = Confirm.ask("Are you sure you want to logout?")
        
        if not confirmed:
            rprint("[yellow]Logout canceled[/yellow]")
            return False
        
        # Delete token file
        try:
            TOKEN_FILE.unlink(missing_ok=True)
            self.access_token = None
            self.device_id = None
            rprint("[green]✓[/green] Successfully logged out")
            return True
        except Exception as e:
            rprint(f"[red]Error during logout: {e}[/red]")
            return False
    
    def is_authenticated(self):
        """Check if the client is authenticated"""
        return self.access_token is not None
    
    def login(self, pairing_code=None):
        """
        Login to the GPUs Cloud service using a pairing code
        
        Args:
            pairing_code: Pairing code provided by the GPUs Cloud service
        
        Returns:
            bool: True if login was successful, False otherwise
        """
        # Get pairing code from user if not provided
        if not pairing_code:
            rprint(Panel.fit(
                "[bold]Device Pairing[/bold]\n\nPlease enter the pairing code from the GPUs Cloud web interface.",
                title="GPUs Cloud",
                border_style="blue"
            ))
            pairing_code = Prompt.ask("Pairing code")
        
        # Get system information
        system_info = get_system_info()
        driver_version, cuda_version = get_driver_and_cuda_version()
        if driver_version:
            system_info["driver_version"] = driver_version
        if cuda_version:
            system_info["cuda_version"] = cuda_version
        
        # Add GPU information to system info
        gpu_info = self.gpu_stats.get_all_devices_info()
        system_info["gpu_count"] = len(gpu_info)
        system_info["gpus"] = gpu_info
        
        with console.status("[bold blue]Verifying pairing code...[/bold blue]", spinner="dots"):
            try:
                response = requests.post(
                    f"{self.server_url}/devices/verify-pairing",
                    json={
                        "pairing_code": pairing_code,
                        "system_info": system_info
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.access_token = data.get('access_token')
                    self.device_id = data.get('device_id')
                    
                    if self._save_token(self.access_token, self.device_id):
                        rprint("[bold green]✓[/bold green] Device paired successfully!")
                        return True
                    else:
                        rprint("[bold red]✗[/bold red] Failed to save access token")
                        return False
                else:
                    rprint(f"[bold red]✗[/bold red] Pairing failed: {response.text}")
                    return False
            
            except requests.RequestException as e:
                rprint(f"[bold red]✗[/bold red] Connection error: {e}")
                return False
    
    def _format_gpu_data_for_api(self, gpu_stats, gpu_info):
        """Format GPU data for the API"""
        result = []
        
        for i, stats in enumerate(gpu_stats):
            if "error" in stats:
                continue
            
            info = next((g for g in gpu_info if g.get("index") == i), {})
            
            gpu_data = {
                "gpu_id": str(i),
                "name": info.get("name", "Unknown GPU"),
                "uuid": info.get("uuid", f"GPU-{i}"),
                "memory_total": info.get("memory_total", 0),
                "memory_used": stats.get("memory_used", 0),
                "memory_free": stats.get("memory_free", 0),
                "utilization_gpu": stats.get("utilization_gpu", 0),
                "utilization_memory": stats.get("utilization_memory", 0),
                "temperature": stats.get("temperature", 0),
                "power_usage": stats.get("power_usage", 0),
            }
            
            # Add driver and CUDA version
            driver_version, cuda_version = get_driver_and_cuda_version()
            if driver_version:
                gpu_data["driver_version"] = driver_version
            if cuda_version:
                gpu_data["cuda_version"] = cuda_version
            
            # Add process information if available
            if "processes" in stats:
                gpu_data["processes"] = stats["processes"]
            
            # Add additional info
            gpu_data["additional_info"] = {}
            
            result.append(gpu_data)
        
        return result
    
    def send_heartbeat(self):
        """Send a heartbeat to the server"""
        if not self.is_authenticated():
            self._log_error("Not authenticated, cannot send heartbeat")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # Get GPU info for the heartbeat
            gpu_stats = self.gpu_stats.get_all_devices_stats()
            gpu_info = self.gpu_stats.get_all_devices_info()
            
            gpu_data = self._format_gpu_data_for_api(gpu_stats, gpu_info)
            
            response = requests.post(
                f"{self.server_url}/devices/heartbeat",
                headers=headers,
                json={"gpus": gpu_data},
                timeout=10
            )
            
            if response.status_code == 200:
                self.last_heartbeat_time = time.time()
                self.connected = True
                return True
            elif response.status_code == 401:
                # Invalid token
                error_msg = "Authentication failed (401): Token rejected by server"
                self._log_error(error_msg)
                self.connected = False
                
                # Try to refresh the token by re-reading from file
                # This is useful if the token was updated elsewhere
                if self._load_token():
                    self._log_info("Reloaded token from file, will retry on next cycle")
                
                return False
            else:
                # Other error
                error_msg = f"Server error ({response.status_code}): {response.text}"
                self._log_error(error_msg)
                self.connected = False
                return False
        
        except requests.RequestException as e:
            error_msg = f"Connection error: {e}"
            self._log_error(error_msg)
            self.connected = False
            return False
    
    def send_metrics(self):
        """Send GPU metrics to the server"""
        if not self.is_authenticated():
            self._log_error("Not authenticated, cannot send metrics")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            # Get GPU info for the metrics
            gpu_stats = self.gpu_stats.get_all_devices_stats()
            gpu_info = self.gpu_stats.get_all_devices_info()
            
            gpu_data = self._format_gpu_data_for_api(gpu_stats, gpu_info)
            
            if not gpu_data:
                self._log_error("No GPU data available to send")
                return False
            
            response = requests.post(
                f"{self.server_url}/devices/metrics",
                headers=headers,
                json={"gpus": gpu_data},
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                # Invalid token
                error_msg = "Authentication failed (401): Token rejected by server"
                self._log_error(error_msg)
                
                # Try to refresh the token by re-reading from file
                # This is useful if the token was updated elsewhere
                if self._load_token():
                    self._log_info("Reloaded token from file, will retry on next cycle")
                
                return False
            else:
                # Other error
                error_msg = f"Server error ({response.status_code}): {response.text if hasattr(response, 'text') else 'Unknown error'}"
                self._log_error(error_msg)
                return False
        
        except requests.RequestException as e:
            error_msg = f"Connection error: {e}"
            self._log_error(error_msg)
            return False
    
    def update_loop(self):
        """Background thread for updating GPU statistics"""
        last_heartbeat_time = 0
        consecutive_failures = 0
        last_success_time = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Send metrics
                metrics_success = self.send_metrics()
                
                if metrics_success:
                    # Reset failure counter on success
                    consecutive_failures = 0
                    last_success_time = current_time
                    self.connected = True
                else:
                    # Increment failure counter
                    consecutive_failures += 1
                    
                    # Log the failure
                    error_msg = f"Failed to send metrics (attempt {consecutive_failures})"
                    self._log_error(error_msg)
                    
                    # If we've had too many failures, try to send a heartbeat
                    # to verify the connection is still valid
                    if consecutive_failures % 5 == 0:
                        if self.send_heartbeat():
                            self._log_info(f"Heartbeat successful after {consecutive_failures} failed metric sends")
                        else:
                            self._log_error(f"Connection appears to be down after {consecutive_failures} failed attempts")
                            self.connected = False
                
                # Send heartbeat if needed
                if current_time - last_heartbeat_time >= self.heartbeat_interval:
                    if self.send_heartbeat():
                        last_heartbeat_time = current_time
                        self.connected = True
                    else:
                        self.connected = False
                
                # Implement backoff for repeated failures
                # Start with normal interval and increase gradually
                sleep_time = self.update_interval
                if consecutive_failures > 0:
                    # Calculate backoff, but cap it to avoid extremely long waits
                    # This creates a gentle backoff curve: normal interval → 2x → 3x → 4x → max 5x
                    backoff_factor = min(5, 1 + consecutive_failures / 2)
                    sleep_time = self.update_interval * backoff_factor
                    
                    # If we've been failing for a while, log it clearly
                    if current_time - last_success_time > 300:  # More than 5 minutes of failure
                        minutes = int((current_time - last_success_time) / 60)
                        self._log_error(f"Unable to send metrics for {minutes} minutes. Will keep trying.")
                
                # Sleep until next update
                time.sleep(sleep_time)
            
            except Exception as e:
                # Log error and continue
                error_msg = f"Error in update loop: {e}"
                self._log_error(error_msg)
                time.sleep(5)  # Back off a bit on error
    
    def start_monitoring(self, foreground=True):
        """
        Start monitoring and sending GPU metrics
        
        Args:
            foreground: If True, run in foreground, otherwise run in background
        """
        if not self.is_authenticated():
            if not self.login():
                return False
        
        if foreground:
            return self._start_foreground_monitoring()
        else:
            return self._start_background_monitoring()
    
    def _start_foreground_monitoring(self):
        """Start monitoring in the foreground"""
        if self.running:
            rprint("[yellow]Monitoring already running[/yellow]")
            return True
        
        # Set foreground mode flag
        self.foreground_mode = True
        
        # Initialize and start the update thread
        self.running = True
        self.update_thread = threading.Thread(target=self.update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Display status table
        rprint(Panel.fit(
            "[bold]GPU Monitoring Started[/bold]\n\nSending metrics to GPUs Cloud service.\nPress Ctrl+C to stop.",
            title="GPUs Cloud",
            border_style="green"
        ))
        
        try:
            # Show live status
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Monitoring GPUs...[/bold blue]"),
                transient=False,
            ) as progress:
                task = progress.add_task("", total=None)
                
                while self.running:
                    # Update the status with connection info
                    status = "[green]Connected[/green]" if self.connected else "[yellow]Connecting...[/yellow]"
                    progress.update(task, description=f"[bold blue]Monitoring GPUs...[/bold blue] Status: {status}")
                    time.sleep(1)
        
        except KeyboardInterrupt:
            rprint("\n[yellow]Stopping monitoring...[/yellow]")
            self.stop_monitoring()
            rprint("[green]Monitoring stopped[/green]")
        
        return True
    
    def _start_background_monitoring(self):
        """Start monitoring in the background as a daemon"""
        # Check if already running
        if is_cloud_client_running():
            pid = get_cloud_client_pid()
            rprint(f"[yellow]Cloud client already running (PID: {pid})[/yellow]")
            return True
        
        # Create directory for pid file if it doesn't exist
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Start as a daemon process
        if os.name == "posix":  # Unix/Linux/MacOS
            # Use double fork to detach from terminal
            pid = os.fork()
            if pid > 0:
                # Parent process, wait for child to exit
                os.waitpid(pid, 0)
                # Check if client started successfully
                time.sleep(1)
                if is_cloud_client_running():
                    pid = get_cloud_client_pid()
                    rprint(f"[green]Cloud client started in background (PID: {pid})[/green]")
                else:
                    rprint("[red]Failed to start cloud client[/red]")
                return True
            
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
            with open(os.devnull, "r") as f:
                os.dup2(f.fileno(), sys.stdin.fileno())
            
            # Redirect stdout and stderr to a log file instead of /dev/null
            log_file = CONFIG_DIR / "cloud_client.log"
            with open(log_file, "a+") as f:
                os.dup2(f.fileno(), sys.stdout.fileno())
                os.dup2(f.fileno(), sys.stderr.fileno())
            
            # Write PID file
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
            
            # Set background mode flag
            self.foreground_mode = False
            
            # Log startup
            print(f"--- Cloud client started at {datetime.now().isoformat()} ---")
            
            # Make sure GPU stats is initialized
            self.gpu_stats = GPUStats()
            
            # Set running flag and run the monitoring loop directly
            try:
                # Send initial heartbeat to verify connection
                if self.send_heartbeat():
                    print(f"Initial heartbeat sent successfully at {datetime.now().isoformat()}")
                else:
                    print(f"Failed to send initial heartbeat at {datetime.now().isoformat()}")
                
                # Set running flag and start the monitoring loop
                self.running = True
                print(f"Starting update loop at {datetime.now().isoformat()}")
                self.update_loop()  # This will run indefinitely
            except Exception as e:
                print(f"Error in background process: {e}")
            finally:
                print(f"Cloud client exiting at {datetime.now().isoformat()}")
                if os.path.exists(PID_FILE):
                    os.unlink(PID_FILE)
                sys.exit(0)
        
        else:  # Windows
            rprint("[red]Background monitoring not supported on Windows.[/red]")
            rprint("[yellow]Please use 'gpus cloud' without 'start' to run in the foreground.[/yellow]")
            return False
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2.0)
        self.gpu_stats.shutdown()

    def _log_error(self, error_msg, print_to_console=None):
        """
        Log an error message
        
        Args:
            error_msg: The error message to log
            print_to_console: Whether to print to console (defaults to foreground_mode)
        """
        # Log to file
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_DIR / "cloud_error.log", "a") as f:
            f.write(f"{datetime.now().isoformat()}: {error_msg}\n")
        
        # Print to console if in foreground mode or explicitly requested
        if print_to_console is None:
            print_to_console = self.foreground_mode
            
        if print_to_console:
            print(f"[Error] {error_msg}")
    
    def _log_info(self, info_msg, print_to_console=None):
        """
        Log an info message
        
        Args:
            info_msg: The info message to log
            print_to_console: Whether to print to console (defaults to foreground_mode)
        """
        # Log to file
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_DIR / "cloud_client.log", "a") as f:
            f.write(f"{datetime.now().isoformat()}: {info_msg}\n")
        
        # Print to console if in foreground mode or explicitly requested
        if print_to_console is None:
            print_to_console = self.foreground_mode
            
        if print_to_console:
            print(f"[Info] {info_msg}")


def is_cloud_client_running():
    """Check if the cloud client is running"""
    if not PID_FILE.exists():
        return False
    
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        
        # Check if process is running
        return is_pid_running(pid)
    except (ValueError, IOError):
        return False


def get_cloud_client_pid():
    """Get the PID of the running cloud client"""
    if not PID_FILE.exists():
        return None
    
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except (ValueError, IOError):
        return None


def is_pid_running(pid):
    """Check if a process with the given PID is running"""
    try:
        os.kill(pid, 0)  # Send signal 0 to check process existence
        return True
    except OSError:
        return False


def stop_cloud_client():
    """Stop the background cloud client"""
    if not is_cloud_client_running():
        rprint("[yellow]No cloud client is running[/yellow]")
        return False
    
    pid = get_cloud_client_pid()
    
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
            rprint(f"[yellow]Cloud client (PID: {pid}) forcefully terminated[/yellow]")
        else:
            rprint(f"[green]Cloud client (PID: {pid}) stopped[/green]")
        
        # Remove PID file
        PID_FILE.unlink(missing_ok=True)
        return True
    
    except OSError as e:
        rprint(f"[red]Error stopping cloud client: {e}[/red]")
        
        # Clean up PID file if process doesn't exist
        if not is_pid_running(pid):
            PID_FILE.unlink(missing_ok=True)
            rprint("[yellow]Removed stale PID file[/yellow]")
        
        return False


def cloud_status():
    """Check if the GPU cloud client is running"""
    if is_cloud_client_running():
        pid = get_cloud_client_pid()
        
        # Check if token exists
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r") as f:
                    data = json.load(f)
                    device_id = data.get("device_id")
                    created_at = data.get("created_at")
                
                # Check the log file for recent activity
                log_file = CONFIG_DIR / "cloud_client.log"
                log_info = ""
                if log_file.exists():
                    try:
                        # Get last few lines of log file to check activity
                        with open(log_file, "r") as f:
                            lines = f.readlines()
                            last_lines = lines[-5:] if len(lines) > 5 else lines
                            if last_lines:
                                last_log_time = last_lines[-1].split(" - ")[0] if " - " in last_lines[-1] else "Unknown"
                                log_info = f"\nLast activity: {last_log_time}"
                    except:
                        pass
                
                # Check for recent errors
                error_log = CONFIG_DIR / "cloud_error.log"
                error_info = ""
                if error_log.exists():
                    try:
                        # Check if the error log file has been modified in the last hour
                        mtime = os.path.getmtime(error_log)
                        if time.time() - mtime < 3600:  # Last hour
                            with open(error_log, "r") as f:
                                lines = f.readlines()
                                recent_errors = lines[-3:] if len(lines) > 3 else lines
                                if recent_errors:
                                    error_info = "\n[red]Recent errors:[/red]"
                                    for err in recent_errors:
                                        # Truncate very long error messages
                                        error_msg = err.strip()
                                        if len(error_msg) > 100:
                                            error_msg = error_msg[:97] + "..."
                                        error_info += f"\n- {error_msg}"
                    except:
                        pass
                
                table = Table(title="GPUs Cloud Client Status")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")
                
                table.add_row("Status", "[bold green]Running[/bold green]")
                table.add_row("PID", str(pid))
                table.add_row("Device ID", device_id or "Unknown")
                table.add_row("Paired At", created_at or "Unknown")
                if log_info:
                    table.add_row("Log Info", log_info)
                
                rprint(table)
                
                # Print errors separately for better formatting
                if error_info:
                    rprint(Panel.fit(
                        error_info,
                        title="Error Information",
                        border_style="red"
                    ))
                
                return True
            
            except (ValueError, IOError, json.JSONDecodeError):
                rprint(f"[yellow]Cloud client is running (PID: {pid}) but token file is invalid[/yellow]")
                return True
        else:
            rprint(f"[yellow]Cloud client is running (PID: {pid}) but no token file found[/yellow]")
            return True
    else:
        # Check if token exists but client not running
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r") as f:
                    data = json.load(f)
                    device_id = data.get("device_id")
                
                rprint("[yellow]Cloud client is not running, but device is paired[/yellow]")
                rprint(f"Device ID: {device_id}")
                rprint("Run 'gpus cloud start' to start monitoring in the background")
                
                # Check for recent errors that might explain why the client stopped
                error_log = CONFIG_DIR / "cloud_error.log"
                if error_log.exists():
                    try:
                        # Only show errors if they're recent (last 24 hours)
                        mtime = os.path.getmtime(error_log)
                        if time.time() - mtime < 86400:  # Last 24 hours
                            with open(error_log, "r") as f:
                                lines = f.readlines()
                                if lines:
                                    last_errors = lines[-3:] if len(lines) > 3 else lines
                                    rprint("\n[red]Last errors before client stopped:[/red]")
                                    for err in last_errors:
                                        rprint(f"- {err.strip()}")
                    except:
                        pass
                
                return False
            
            except (ValueError, IOError, json.JSONDecodeError):
                rprint("[red]Cloud client is not running and token file is invalid[/red]")
                return False
        else:
            rprint("[yellow]Cloud client is not running and device is not paired[/yellow]")
            rprint("Run 'gpus cloud login' to pair your device")
            return False 