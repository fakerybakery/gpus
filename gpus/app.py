"""
Flask web application for GPU monitoring
"""

import json
import threading
import time
import signal
import sys
import eventlet
from typing import Optional, Dict
from datetime import datetime

# Patch eventlet to work with Socket.IO
eventlet.monkey_patch()

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

from gpus.gpu_stats import GPUStats



class GPUMonitorApp:
    """Flask application for GPU monitoring"""

    def __init__(
        self,
        update_interval: float = 2.0,
        history_length: int = 300,
        history_resolution: float = 1.0,
    ):
        """
        Initialize the GPU monitoring application

        Args:
            update_interval: Interval in seconds between updates
            history_length: Number of seconds of history to keep
            history_resolution: Resolution of history in seconds
        """
        self.app = Flask(__name__)
        
        # Configure Socket.IO with improved settings
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode='eventlet',
            ping_timeout=20,
            ping_interval=5,
            max_http_buffer_size=10e6,
        )
        
        self.gpu_stats = GPUStats(
            history_length=history_length, history_resolution=history_resolution
        )
        self.update_interval = update_interval
        self.update_thread: Optional[threading.Thread] = None
        self.running = False
        self.last_update_time = None
        self.update_count = 0
        self.connected_clients: Dict[str, Dict] = {}
        self.client_activity = {}

        # Register routes
        self.register_routes()

        # Register SocketIO events
        self.register_socketio_events()

        # Register signal handlers for graceful shutdown
        self.register_signal_handlers()

    def register_routes(self):
        """Register Flask routes"""

        @self.app.route("/")
        def index():
            return render_template("index.html")

        @self.app.route("/api/devices")
        def get_devices():
            return jsonify(self.gpu_stats.get_all_devices_info())

        @self.app.route("/api/stats")
        def get_stats():
            return jsonify(self.gpu_stats.get_all_devices_stats())

        @self.app.route("/api/history/<int:device_id>")
        def get_history(device_id):
            return jsonify(self.gpu_stats.get_history(device_id))

    def register_socketio_events(self):
        """Register SocketIO event handlers"""

        @self.socketio.on("connect")
        def handle_connect():
            client_id = request.sid
            self.connected_clients[client_id] = {
                'connected_at': datetime.now(),
                'last_activity': datetime.now(),
                'ip': request.remote_addr
            }
            
            # Send initial data on connect
            devices_info = self.gpu_stats.get_all_devices_info()
            self.socketio.emit(
                "devices", json.dumps(devices_info), room=client_id
            )
            
            stats = self.gpu_stats.get_all_devices_stats()
            self.socketio.emit(
                "stats", json.dumps(stats), room=client_id
            )

            # Send history data for each device
            for i in range(self.gpu_stats.device_count):
                history = self.gpu_stats.get_history(i)
                self.socketio.emit(
                    f"history_{i}", json.dumps(history), room=client_id
                )
        
        @self.socketio.on("disconnect")
        def handle_disconnect():
            client_id = request.sid
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
        
        @self.socketio.on_error()
        def handle_error(e):
            print(f"Socket.IO error: {e}")
        
        @self.socketio.on("ping")
        def handle_ping():
            client_id = request.sid
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['last_activity'] = datetime.now()
            return {"status": "ok", "time": time.time()}
        
        @self.socketio.on("heartbeat")
        def handle_heartbeat(data):
            client_id = request.sid
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['last_activity'] = datetime.now()
            return {"status": "ok", "time": time.time(), "clients": len(self.connected_clients)}

    def register_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        signal.signal(signal.SIGTERM, self.handle_shutdown_signal)
        signal.signal(signal.SIGINT, self.handle_shutdown_signal)

    def handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signals"""
        self.stop_update_thread()
        self.gpu_stats.shutdown()
        sys.exit(0)

    def update_loop(self):
        """Background thread for updating GPU statistics"""
        while self.running:
            start_time = time.time()
            
            # Skip updates if no clients are connected
            if not self.connected_clients:
                time.sleep(self.update_interval)
                continue
            
            try:
                # Update GPU statistics and history
                self.gpu_stats.update_history()
                
                # Get updated stats
                stats = self.gpu_stats.get_all_devices_stats()
                
                # Emit updated statistics to connected clients
                client_count = len(self.connected_clients)
                self.socketio.emit(
                    "stats", json.dumps(stats)
                )

                # Emit updated history for each device
                for i in range(self.gpu_stats.device_count):
                    history = self.gpu_stats.get_history(i)
                    history_points = len(history.get('timestamps', []))
                    self.socketio.emit(
                        f"history_{i}", json.dumps(history)
                    )
                
                # Update counters
                self.update_count += 1
                current_time = datetime.now().strftime("%H:%M:%S")
                self.last_update_time = current_time
                
                # Log update summary
                elapsed = time.time() - start_time
                
                # Clean up inactive clients
                self.clean_inactive_clients()
                
                # Sleep until next update
                sleep_time = max(0.1, self.update_interval - elapsed)
                time.sleep(sleep_time)
            except Exception as e:
                time.sleep(1)  # Sleep briefly before retrying
    
    def clean_inactive_clients(self):
        """Remove clients that haven't been active for more than 30 seconds"""
        now = datetime.now()
        inactive_clients = []
        
        for client_id, client_data in self.connected_clients.items():
            last_activity = client_data.get('last_activity', client_data.get('connected_at'))
            if (now - last_activity).total_seconds() > 30:
                inactive_clients.append(client_id)
        
        for client_id in inactive_clients:
            del self.connected_clients[client_id]

    def start_update_thread(self):
        """Start the background update thread"""
        if self.update_thread is None or not self.update_thread.is_alive():
            self.running = True
            self.update_thread = threading.Thread(target=self.update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()


    def stop_update_thread(self):
        """Stop the background update thread"""
        if self.running:
            self.running = False
            if self.update_thread and self.update_thread.is_alive():
                self.update_thread.join(timeout=1.0)

    def run(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
        """
        Run the Flask application

        Args:
            host: Host to bind to
            port: Port to bind to
            debug: Whether to run in debug mode
        """
        print(f"Starting server on {host}:{port} (debug={debug})")
        try:
            # Initialize history before starting
            self.gpu_stats.update_history(force=True)

            # Start the update thread
            self.start_update_thread()

            # Run the Flask application
            self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        finally:
            print("Shutting down server")
            self.stop_update_thread()
            self.gpu_stats.shutdown()
