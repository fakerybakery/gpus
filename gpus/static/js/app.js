// GPU Monitor Client-side Application

// Constants
const TEMPERATURE_THRESHOLDS = {
    COOL: 50,
    WARM: 70,
    HOT: 80,
    CRITICAL: 90
};

// Debug flag
const DEBUG = true;

// Debug logging function
function debugLog(...args) {
    if (DEBUG) {
        console.log(`[${new Date().toLocaleTimeString()}]`, ...args);
    }
}

// State
const state = {
    devices: [],
    stats: [],
    charts: {},
    connected: false,
    lastUpdate: null,
    socketEvents: {},
    reconnectAttempts: 0,
    heartbeatInterval: null,
    lastHeartbeat: null
};

// DOM Elements
const elements = {
    gpuCardsContainer: document.getElementById('gpu-cards-container'),
    gpuCardTemplate: document.getElementById('gpu-card-template'),
    noGpuAlert: document.getElementById('no-gpu-alert'),
    errorAlert: document.getElementById('error-alert'),
    updateStatus: document.getElementById('update-status'),
    refreshBtn: document.getElementById('refresh-btn'),
    reconnectBtn: document.getElementById('reconnect-btn')
};

// Socket.io connection with improved configuration
const socket = io({
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    transports: ['websocket', 'polling'],
    upgrade: true,
    forceNew: false,
    autoConnect: true
});

// Initialize the application
function init() {
    debugLog('Initializing application');
    
    // Set up event listeners
    elements.refreshBtn.addEventListener('click', refreshData);
    elements.reconnectBtn.addEventListener('click', manualReconnect);
    
    // Set up socket.io event handlers
    setupSocketHandlers();
    
    // Initial data fetch
    fetchInitialData();
    
    // Set up periodic connection check
    setInterval(checkConnection, 3000);
    
    // Start heartbeat
    startHeartbeat();
    
    // Add window focus/blur event listeners
    window.addEventListener('focus', handleWindowFocus);
    window.addEventListener('blur', handleWindowBlur);
}

// Handle window focus event
function handleWindowFocus() {
    debugLog('Window focused - checking connection');
    if (!state.connected) {
        debugLog('Reconnecting due to window focus');
        manualReconnect();
    } else {
        // Refresh data when window gets focus
        refreshData();
    }
}

// Handle window blur event
function handleWindowBlur() {
    debugLog('Window blurred');
}

// Start heartbeat mechanism
function startHeartbeat() {
    debugLog('Starting heartbeat mechanism');
    
    // Clear any existing interval
    if (state.heartbeatInterval) {
        clearInterval(state.heartbeatInterval);
    }
    
    // Set up new heartbeat interval (every 5 seconds)
    state.heartbeatInterval = setInterval(() => {
        if (state.connected) {
            sendHeartbeat();
        }
    }, 5000);
}

// Send heartbeat to server
function sendHeartbeat() {
    debugLog('Sending heartbeat');
    socket.emit('heartbeat', { timestamp: Date.now() }, (response) => {
        if (response && response.status === 'ok') {
            debugLog('Heartbeat acknowledged');
            state.lastHeartbeat = Date.now();
            state.lastUpdate = new Date(); // Update this to prevent reconnection
        } else {
            debugLog('Heartbeat failed');
            // If heartbeat fails, try to reconnect
            handleConnectionIssue();
        }
    });
}

// Set up all socket event handlers
function setupSocketHandlers() {
    debugLog('Setting up socket event handlers');
    
    // Remove any existing listeners to prevent duplicates
    socket.off('connect');
    socket.off('disconnect');
    socket.off('connect_error');
    socket.off('connect_timeout');
    socket.off('reconnect');
    socket.off('reconnect_attempt');
    socket.off('reconnect_error');
    socket.off('reconnect_failed');
    socket.off('devices');
    socket.off('stats');
    
    // Core connection events
    socket.on('connect', handleSocketConnect);
    socket.on('disconnect', handleSocketDisconnect);
    socket.on('connect_error', (error) => {
        debugLog('Connection error:', error);
        handleConnectionIssue();
    });
    socket.on('connect_timeout', () => {
        debugLog('Connection timeout');
        handleConnectionIssue();
    });
    socket.on('reconnect', (attemptNumber) => {
        debugLog(`Reconnected after ${attemptNumber} attempts`);
        state.reconnectAttempts = 0;
        refreshData(); // Refresh data after reconnection
    });
    socket.on('reconnect_attempt', (attemptNumber) => {
        debugLog(`Reconnection attempt ${attemptNumber}`);
        state.reconnectAttempts = attemptNumber;
    });
    socket.on('reconnect_error', (error) => {
        debugLog('Reconnection error:', error);
    });
    socket.on('reconnect_failed', () => {
        debugLog('Failed to reconnect');
        elements.errorAlert.classList.remove('hidden');
        elements.errorAlert.textContent = 'Failed to reconnect to the server. Please refresh the page.';
    });
    
    // Data events
    socket.on('devices', handleDevicesUpdate);
    socket.on('stats', handleStatsUpdate);
    
    // Track event registrations to avoid duplicates
    state.socketEvents = {
        devices: true,
        stats: true
    };
}

// Check if connection is still working
function checkConnection() {
    const timeSinceLastUpdate = state.lastUpdate ? (new Date() - state.lastUpdate) / 1000 : 0;
    debugLog(`Connection check: Last update was ${timeSinceLastUpdate.toFixed(1)}s ago, connected=${state.connected}`);
    
    // If no updates for more than 8 seconds and we think we're connected, try to reconnect
    if (state.connected && state.lastUpdate && timeSinceLastUpdate > 8) {
        debugLog('No updates received for 8+ seconds, attempting reconnection');
        handleConnectionIssue();
    }
}

// Handle connection issues
function handleConnectionIssue() {
    if (socket.connected) {
        debugLog('Connection issue detected, disconnecting and reconnecting');
        socket.disconnect();
        setTimeout(() => {
            socket.connect();
        }, 1000);
    } else {
        debugLog('Already disconnected, waiting for reconnection');
        // Force a reconnection if we've been disconnected for too long
        if (!state.reconnectAttempts || state.reconnectAttempts > 5) {
            debugLog('Forcing reconnection');
            socket.connect();
        }
    }
}

// Socket event handlers
function handleSocketConnect() {
    debugLog('Connected to server');
    state.connected = true;
    elements.updateStatus.textContent = 'Connected';
    elements.updateStatus.classList.add('connected');
    elements.updateStatus.classList.remove('disconnected');
    elements.errorAlert.classList.add('hidden');
    elements.reconnectBtn.classList.add('hidden');
    
    // Re-register device-specific event handlers if needed
    if (state.devices.length > 0) {
        registerDeviceEventHandlers();
    }
    
    // Send heartbeat immediately after connection
    sendHeartbeat();
}

function handleSocketDisconnect() {
    debugLog('Disconnected from server');
    state.connected = false;
    elements.updateStatus.textContent = 'Disconnected';
    elements.updateStatus.classList.remove('connected');
    elements.updateStatus.classList.add('disconnected');
    elements.errorAlert.classList.remove('hidden');
    elements.errorAlert.textContent = 'Disconnected from server. Attempting to reconnect...';
    elements.reconnectBtn.classList.remove('hidden');
    
    // Try to reconnect automatically
    setTimeout(() => {
        if (!state.connected) {
            debugLog('Auto-reconnecting after disconnect');
            socket.connect();
        }
    }, 2000);
}

function handleDevicesUpdate(data) {
    debugLog('Received devices data');
    const devices = JSON.parse(data);
    state.devices = devices;
    
    // Check if we have any GPUs
    if (devices.length === 0) {
        elements.noGpuAlert.classList.remove('hidden');
    } else {
        elements.noGpuAlert.classList.add('hidden');
        renderDeviceCards();
        registerDeviceEventHandlers();
    }
}

// Register event handlers for each device
function registerDeviceEventHandlers() {
    debugLog('Registering device event handlers');
    
    // Clear any existing handlers by removing and re-adding
    state.devices.forEach((device, index) => {
        if (device.error) return;
        
        const eventName = `history_${index}`;
        
        // Remove existing handler if any
        if (state.socketEvents[eventName]) {
            debugLog(`Removing existing handler for ${eventName}`);
            socket.off(eventName);
        }
        
        // Add new handler
        debugLog(`Adding handler for ${eventName}`);
        socket.on(eventName, (data) => {
            debugLog(`Received history update for device ${index}`);
            handleHistoryUpdate(index, JSON.parse(data));
        });
        
        // Mark as registered
        state.socketEvents[eventName] = true;
    });
}

function handleStatsUpdate(data) {
    debugLog('Received stats update');
    const stats = JSON.parse(data);
    state.stats = stats;
    state.lastUpdate = new Date();
    
    // Update the status text
    elements.updateStatus.textContent = `Last update: ${state.lastUpdate.toLocaleTimeString()}`;
    
    // Update the UI with new stats
    updateDeviceStats();
    debugLog('Stats update complete');
}

function handleHistoryUpdate(deviceIndex, historyData) {
    debugLog(`Processing history update for device ${deviceIndex}: ${historyData.timestamps.length} data points`);
    updateChart(deviceIndex, historyData);
}

// Data fetching
function fetchInitialData() {
    // Fetch devices
    fetch('/api/devices')
        .then(response => response.json())
        .then(data => {
            state.devices = data;
            
            // Check if we have any GPUs
            if (data.length === 0) {
                elements.noGpuAlert.classList.remove('hidden');
            } else {
                elements.noGpuAlert.classList.add('hidden');
                renderDeviceCards();
                
                // Fetch initial stats
                return fetch('/api/stats');
            }
        })
        .then(response => response ? response.json() : null)
        .then(data => {
            if (data) {
                state.stats = data;
                state.lastUpdate = new Date();
                updateDeviceStats();
                
                // Fetch history for each device
                state.devices.forEach((device, index) => {
                    if (device.error) return;
                    
                    fetch(`/api/history/${index}`)
                        .then(response => response.json())
                        .then(historyData => {
                            updateChart(index, historyData);
                        })
                        .catch(error => {
                            console.error(`Error fetching history for device ${index}:`, error);
                        });
                });
            }
        })
        .catch(error => {
            console.error('Error fetching data:', error);
            elements.errorAlert.classList.remove('hidden');
        });
}

function refreshData() {
    fetchInitialData();
}

// UI Rendering
function renderDeviceCards() {
    debugLog('Rendering device cards for', state.devices.length, 'devices');
    // Clear existing cards
    elements.gpuCardsContainer.innerHTML = '';
    
    // Create a card for each device
    state.devices.forEach(device => {
        if (device.error) {
            console.error('Error with device:', device.error);
            return;
        }
        
        // Clone the template
        const template = elements.gpuCardTemplate.content.cloneNode(true);
        const card = template.querySelector('.card');
        
        // Set device info
        card.id = `gpu-card-${device.index}`;
        card.querySelector('.gpu-name').textContent = device.name;
        card.querySelector('.gpu-index').textContent = device.index;
        
        // Initialize the history chart
        initializeChart(card.querySelector('.history-chart'), device.index);
        
        // Add the card to the container
        elements.gpuCardsContainer.appendChild(card);
    });
}

function updateDeviceStats() {
    debugLog('Updating stats for', state.stats.length, 'devices');
    state.stats.forEach((stats, index) => {
        if (stats.error) {
            console.error('Error with stats:', stats.error);
            return;
        }
        
        const card = document.getElementById(`gpu-card-${index}`);
        if (!card) return;
        
        // Update GPU utilization
        const gpuUtil = stats.utilization_gpu;
        updateProgressBar(card.querySelector('.gpu-util-bar'), gpuUtil);
        card.querySelector('.gpu-util-text').textContent = `${gpuUtil}%`;
        
        // Update memory utilization
        const memoryUtil = stats.utilization_memory;
        updateProgressBar(card.querySelector('.memory-util-bar'), memoryUtil);
        card.querySelector('.memory-util-text').textContent = `${memoryUtil}%`;
        
        // Update temperature
        const temperature = stats.temperature;
        const temperatureBar = card.querySelector('.temperature-bar');
        updateProgressBar(temperatureBar, Math.min(100, (temperature / 100) * 100));
        card.querySelector('.temperature-text').textContent = `${temperature}°C`;
        
        // Update temperature bar color
        temperatureBar.classList.remove('temperature-cool', 'temperature-warm', 'temperature-hot', 'temperature-critical');
        if (temperature < TEMPERATURE_THRESHOLDS.COOL) {
            temperatureBar.classList.add('temperature-cool');
        } else if (temperature < TEMPERATURE_THRESHOLDS.WARM) {
            temperatureBar.classList.add('temperature-warm');
        } else if (temperature < TEMPERATURE_THRESHOLDS.HOT) {
            temperatureBar.classList.add('temperature-hot');
        } else {
            temperatureBar.classList.add('temperature-critical');
        }
        
        // Update power usage
        const device = state.devices[index];
        const powerUsage = stats.power_usage;
        const powerLimit = device.power_limit;
        const powerPercent = (powerUsage / powerLimit) * 100;
        updateProgressBar(card.querySelector('.power-bar'), powerPercent);
        card.querySelector('.power-text').textContent = `${powerUsage.toFixed(1)}W / ${powerLimit.toFixed(1)}W`;
        
        // Update memory usage
        const memoryUsed = stats.memory_used;
        const memoryTotal = device.memory_total;
        const memoryFree = stats.memory_free;
        const memoryPercent = (memoryUsed / memoryTotal) * 100;
        
        updateProgressBar(card.querySelector('.memory-used-bar'), memoryPercent);
        card.querySelector('.memory-used-text').textContent = 
            `${formatBytes(memoryUsed)} / ${formatBytes(memoryTotal)}`;
        card.querySelector('.memory-free-text').textContent = 
            `${formatBytes(memoryFree)} free`;
        
        // Update processes table
        updateProcessesTable(card, stats.processes);
    });
    debugLog('Stats update complete');
}

// Helper function to update progress bar without reflow/repaint
function updateProgressBar(element, value) {
    // Only update if the value has changed significantly (avoid minor updates)
    const currentWidth = parseFloat(element.style.width) || 0;
    if (Math.abs(currentWidth - value) >= 1) {
        element.style.width = `${value}%`;
    }
}

function updateProcessesTable(card, processes) {
    const tableBody = card.querySelector('.process-table-body');
    
    // If no processes, show a message
    if (processes.length === 0) {
        if (tableBody.children.length === 1 && 
            tableBody.children[0].children.length === 1 && 
            tableBody.children[0].children[0].colSpan === 3) {
            // Already showing "No processes" message
            return;
        }
        
        tableBody.innerHTML = '<tr><td colspan="3" class="table-center">No processes</td></tr>';
        return;
    }
    
    // Sort processes by memory usage (descending)
    processes.sort((a, b) => b.memory_used - a.memory_used);
    
    // Check if we need to update the table
    let needsUpdate = processes.length !== tableBody.children.length;
    
    if (!needsUpdate) {
        // Check if any process has changed
        for (let i = 0; i < processes.length; i++) {
            const row = tableBody.children[i];
            const proc = processes[i];
            
            if (parseInt(row.children[0].textContent) !== proc.pid ||
                row.children[1].textContent !== proc.name ||
                row.children[2].textContent !== formatBytes(proc.memory_used)) {
                needsUpdate = true;
                break;
            }
        }
    }
    
    // Only update if necessary
    if (needsUpdate) {
        // Clear existing rows
        tableBody.innerHTML = '';
        
        // Add rows for each process
        processes.forEach(process => {
            const row = document.createElement('tr');
            
            const pidCell = document.createElement('td');
            pidCell.textContent = process.pid;
            
            const nameCell = document.createElement('td');
            nameCell.textContent = process.name;
            
            const memoryCell = document.createElement('td');
            memoryCell.textContent = formatBytes(process.memory_used);
            
            row.appendChild(pidCell);
            row.appendChild(nameCell);
            row.appendChild(memoryCell);
            
            tableBody.appendChild(row);
        });
    }
}

// Chart functions
function initializeChart(canvas, deviceIndex) {
    const ctx = canvas.getContext('2d');
    
    // Create the chart
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'GPU',
                    data: [],
                    borderColor: 'var(--primary-color)',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    tension: 0.2,
                    fill: true,
                    pointRadius: 0
                },
                {
                    label: 'Memory',
                    data: [],
                    borderColor: 'var(--secondary-color)',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    borderWidth: 2,
                    tension: 0.2,
                    fill: true,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    display: false
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: value => `${value}%`
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            }
        }
    });
    
    // Store the chart in state
    state.charts[deviceIndex] = chart;
}

function updateChart(deviceIndex, historyData) {
    debugLog(`Updating chart for device ${deviceIndex} with ${historyData.timestamps.length} data points`);
    const chart = state.charts[deviceIndex];
    if (!chart) {
        debugLog(`No chart found for device ${deviceIndex}`);
        return;
    }
    
    // Format timestamps for display
    const labels = historyData.timestamps.map(timestamp => {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString();
    });
    
    // Update the chart data
    chart.data.labels = labels;
    chart.data.datasets[0].data = historyData.utilization_gpu;
    chart.data.datasets[1].data = historyData.utilization_memory;
    
    // Update the chart without animation
    chart.update('none'); // Use 'none' mode to prevent any animations
    debugLog(`Chart update complete for device ${deviceIndex}`);
}

// Utility functions
function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Ping the server to keep connection alive
function pingServer() {
    if (state.connected) {
        debugLog('Pinging server to keep connection alive');
        socket.emit('ping', {}, (response) => {
            if (response && response.status === 'ok') {
                debugLog('Ping successful, server responded');
                // Update last update time to prevent unnecessary reconnection
                state.lastUpdate = new Date();
            } else {
                debugLog('Ping failed or no response');
                handleConnectionIssue();
            }
        });
    }
}

// Manual reconnection
function manualReconnect() {
    debugLog('Manual reconnection requested');
    elements.reconnectBtn.disabled = true;
    elements.reconnectBtn.textContent = 'Reconnecting...';
    
    // Force disconnect and reconnect
    if (socket.connected) {
        socket.disconnect();
    }
    
    // Clear any existing socket event handlers
    setupSocketHandlers();
    
    setTimeout(() => {
        socket.connect();
        setTimeout(() => {
            elements.reconnectBtn.disabled = false;
            elements.reconnectBtn.textContent = 'Reconnect';
        }, 2000);
    }, 1000);
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', init); 