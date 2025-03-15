"""
Flask web application for GPU monitoring
"""

import json
import threading
import time
import signal
import sys
from typing import Optional

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO

from gpus.gpu_stats import GPUStats


class GPUMonitorApp:
    """Flask application for GPU monitoring"""
    
    def __init__(self, update_interval: float = 2.0, history_length: int = 300, history_resolution: float = 1.0):
        """
        Initialize the GPU monitoring application
        
        Args:
            update_interval: Interval in seconds between updates
            history_length: Number of seconds of history to keep
            history_resolution: Resolution of history in seconds
        """
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        self.gpu_stats = GPUStats(history_length=history_length, history_resolution=history_resolution)
        self.update_interval = update_interval
        self.update_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Register routes
        self.register_routes()
        
        # Register SocketIO events
        self.register_socketio_events()
        
        # Register signal handlers for graceful shutdown
        self.register_signal_handlers()
    
    def register_routes(self):
        """Register Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/api/devices')
        def get_devices():
            return jsonify(self.gpu_stats.get_all_devices_info())
        
        @self.app.route('/api/stats')
        def get_stats():
            return jsonify(self.gpu_stats.get_all_devices_stats())
        
        @self.app.route('/api/history/<int:device_id>')
        def get_history(device_id):
            return jsonify(self.gpu_stats.get_history(device_id))
    
    def register_socketio_events(self):
        """Register SocketIO event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect():
            # Send initial data on connect
            self.socketio.emit('devices', json.dumps(self.gpu_stats.get_all_devices_info()))
            self.socketio.emit('stats', json.dumps(self.gpu_stats.get_all_devices_stats()))
            
            # Send history data for each device
            for i in range(self.gpu_stats.device_count):
                self.socketio.emit(f'history_{i}', json.dumps(self.gpu_stats.get_history(i)))
    
    def register_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        signal.signal(signal.SIGTERM, self.handle_shutdown_signal)
        signal.signal(signal.SIGINT, self.handle_shutdown_signal)
    
    def handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signals"""
        print(f"Received signal {signum}, shutting down...")
        self.stop_update_thread()
        self.gpu_stats.shutdown()
        sys.exit(0)
    
    def update_loop(self):
        """Background thread for updating GPU statistics"""
        while self.running:
            # Update GPU statistics and history
            self.gpu_stats.update_history()
            
            # Emit updated statistics to connected clients
            self.socketio.emit('stats', json.dumps(self.gpu_stats.get_all_devices_stats()))
            
            # Emit updated history for each device
            for i in range(self.gpu_stats.device_count):
                self.socketio.emit(f'history_{i}', json.dumps(self.gpu_stats.get_history(i)))
            
            # Sleep until next update
            time.sleep(self.update_interval)
    
    def start_update_thread(self):
        """Start the background update thread"""
        if self.update_thread is None or not self.update_thread.is_alive():
            self.running = True
            self.update_thread = threading.Thread(target=self.update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
    
    def stop_update_thread(self):
        """Stop the background update thread"""
        self.running = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=1.0)
    
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """
        Run the Flask application
        
        Args:
            host: Host to bind to
            port: Port to bind to
            debug: Whether to run in debug mode
        """
        try:
            # Initialize history before starting
            self.gpu_stats.update_history(force=True)
            
            # Start the update thread
            self.start_update_thread()
            
            # Run the Flask application
            self.socketio.run(self.app, host=host, port=port, debug=debug)
        finally:
            self.stop_update_thread()
            self.gpu_stats.shutdown() 