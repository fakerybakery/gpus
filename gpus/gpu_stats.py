"""
Module for collecting GPU statistics using NVIDIA Management Library (NVML)
"""

import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import deque

import pynvml


class GPUStats:
    """Class to collect and manage GPU statistics"""
    
    def __init__(self, history_length=300, history_resolution=1.0):
        """
        Initialize the GPU stats collector
        
        Args:
            history_length: Number of seconds of history to keep
            history_resolution: Resolution of history in seconds
        """
        self.history_length = history_length
        self.history_resolution = history_resolution
        self.max_history_points = int(history_length / history_resolution)
        self.history = {}
        self.last_update_time: Optional[float] = None
        self.initialize_nvml()
        
    def initialize_nvml(self):
        """Initialize NVML library"""
        try:
            pynvml.nvmlInit()
            self.device_count = pynvml.nvmlDeviceGetCount()
            self.initialized = True
        except pynvml.NVMLError as e:
            self.initialized = False
            self.error = str(e)
            self.device_count = 0
    
    def shutdown(self):
        """Shutdown NVML library"""
        if self.initialized:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError:
                pass
    
    def get_device_info(self, device_index: int) -> Dict[str, Any]:
        """
        Get static information about a GPU device
        
        Args:
            device_index: Index of the GPU device
            
        Returns:
            Dictionary containing device information
        """
        if not self.initialized:
            return {"error": self.error}
        
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')
                
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            if isinstance(uuid, bytes):
                uuid = uuid.decode('utf-8')
            
            return {
                "name": name,
                "uuid": uuid,
                "memory_total": pynvml.nvmlDeviceGetMemoryInfo(handle).total,
                "power_limit": pynvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000.0,
                "index": device_index,
            }
        except pynvml.NVMLError as e:
            return {"error": str(e)}
    
    def get_device_stats(self, device_index: int) -> Dict[str, Any]:
        """
        Get current statistics for a GPU device
        
        Args:
            device_index: Index of the GPU device
            
        Returns:
            Dictionary containing current device statistics
        """
        if not self.initialized:
            return {"error": self.error}
        
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            power_usage = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            
            # Get process information
            processes = []
            try:
                for proc in pynvml.nvmlDeviceGetComputeRunningProcesses(handle):
                    try:
                        process_name = pynvml.nvmlSystemGetProcessName(proc.pid)
                        if isinstance(process_name, bytes):
                            process_name = process_name.decode('utf-8')
                    except pynvml.NVMLError:
                        process_name = "Unknown"
                    
                    processes.append({
                        "pid": proc.pid,
                        "memory_used": proc.usedGpuMemory,
                        "name": process_name
                    })
            except pynvml.NVMLError:
                pass
            
            return {
                "timestamp": datetime.now().isoformat(),
                "memory_used": memory.used,
                "memory_free": memory.free,
                "utilization_gpu": utilization.gpu,
                "utilization_memory": utilization.memory,
                "temperature": temperature,
                "power_usage": power_usage,
                "processes": processes
            }
        except pynvml.NVMLError as e:
            return {"error": str(e)}
    
    def get_all_devices_info(self) -> List[Dict[str, Any]]:
        """
        Get static information for all GPU devices
        
        Returns:
            List of dictionaries containing device information
        """
        return [self.get_device_info(i) for i in range(self.device_count)]
    
    def get_all_devices_stats(self) -> List[Dict[str, Any]]:
        """
        Get current statistics for all GPU devices
        
        Returns:
            List of dictionaries containing current device statistics
        """
        return [self.get_device_stats(i) for i in range(self.device_count)]
    
    def update_history(self, force: bool = False):
        """
        Update the history with current statistics
        
        Args:
            force: Force update regardless of time since last update
        """
        current_time = time.time()
        
        # Only update if enough time has passed since the last update or if forced
        if not force and self.last_update_time is not None and (current_time - self.last_update_time) < self.history_resolution:
            return
            
        self.last_update_time = current_time
        stats = self.get_all_devices_stats()
        
        for i, device_stats in enumerate(stats):
            if i not in self.history:
                self.history[i] = {
                    "timestamps": deque(maxlen=self.max_history_points),
                    "utilization_gpu": deque(maxlen=self.max_history_points),
                    "utilization_memory": deque(maxlen=self.max_history_points),
                    "temperature": deque(maxlen=self.max_history_points),
                    "power_usage": deque(maxlen=self.max_history_points),
                    "memory_used": deque(maxlen=self.max_history_points),
                    "memory_percent": deque(maxlen=self.max_history_points)
                }
            
            # Skip if there's an error with this device
            if "error" in device_stats:
                continue
                
            # Calculate memory percentage
            device_info = self.get_device_info(i)
            if "error" not in device_info:
                memory_percent = (device_stats["memory_used"] / device_info["memory_total"]) * 100
            else:
                memory_percent = 0
            
            # Add data to history
            self.history[i]["timestamps"].append(current_time)
            self.history[i]["utilization_gpu"].append(device_stats["utilization_gpu"])
            self.history[i]["utilization_memory"].append(device_stats["utilization_memory"])
            self.history[i]["temperature"].append(device_stats["temperature"])
            self.history[i]["power_usage"].append(device_stats["power_usage"])
            self.history[i]["memory_used"].append(device_stats["memory_used"])
            self.history[i]["memory_percent"].append(memory_percent)
    
    def get_history(self, device_index: int) -> Dict[str, List]:
        """
        Get history for a specific device
        
        Args:
            device_index: Index of the GPU device
            
        Returns:
            Dictionary with history data
        """
        if device_index not in self.history:
            return {
                "timestamps": [],
                "utilization_gpu": [],
                "utilization_memory": [],
                "temperature": [],
                "power_usage": [],
                "memory_used": [],
                "memory_percent": []
            }
        
        # Convert deques to lists for JSON serialization
        return {
            "timestamps": list(self.history[device_index]["timestamps"]),
            "utilization_gpu": list(self.history[device_index]["utilization_gpu"]),
            "utilization_memory": list(self.history[device_index]["utilization_memory"]),
            "temperature": list(self.history[device_index]["temperature"]),
            "power_usage": list(self.history[device_index]["power_usage"]),
            "memory_used": list(self.history[device_index]["memory_used"]),
            "memory_percent": list(self.history[device_index]["memory_percent"])
        } 