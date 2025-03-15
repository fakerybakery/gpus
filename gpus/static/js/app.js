// GPU Monitor Client-side Application

// Constants
const TEMPERATURE_THRESHOLDS = {
    COOL: 50,
    WARM: 70,
    HOT: 80,
    CRITICAL: 90
};

// State
const state = {
    devices: [],
    stats: [],
    charts: {},
    connected: false,
    lastUpdate: null
};

// DOM Elements
const elements = {
    gpuCardsContainer: document.getElementById('gpu-cards-container'),
    gpuCardTemplate: document.getElementById('gpu-card-template'),
    noGpuAlert: document.getElementById('no-gpu-alert'),
    errorAlert: document.getElementById('error-alert'),
    updateStatus: document.getElementById('update-status'),
    refreshBtn: document.getElementById('refresh-btn')
};

// Socket.io connection
const socket = io();

// Initialize the application
function init() {
    // Set up event listeners
    elements.refreshBtn.addEventListener('click', refreshData);
    
    // Set up socket.io event handlers
    socket.on('connect', handleSocketConnect);
    socket.on('disconnect', handleSocketDisconnect);
    socket.on('devices', handleDevicesUpdate);
    socket.on('stats', handleStatsUpdate);
    
    // Initial data fetch
    fetchInitialData();
}

// Socket event handlers
function handleSocketConnect() {
    state.connected = true;
    elements.updateStatus.textContent = 'Connected';
    elements.updateStatus.classList.add('connected');
    elements.updateStatus.classList.remove('disconnected');
    elements.errorAlert.classList.add('hidden');
}

function handleSocketDisconnect() {
    state.connected = false;
    elements.updateStatus.textContent = 'Disconnected';
    elements.updateStatus.classList.remove('connected');
    elements.updateStatus.classList.add('disconnected');
    elements.errorAlert.classList.remove('hidden');
}

function handleDevicesUpdate(data) {
    const devices = JSON.parse(data);
    state.devices = devices;
    
    // Check if we have any GPUs
    if (devices.length === 0) {
        elements.noGpuAlert.classList.remove('hidden');
    } else {
        elements.noGpuAlert.classList.add('hidden');
        renderDeviceCards();
        
        // Set up history event handlers for each device
        devices.forEach((device, index) => {
            if (device.error) return;
            
            socket.on(`history_${index}`, (data) => {
                handleHistoryUpdate(index, JSON.parse(data));
            });
        });
    }
}

function handleStatsUpdate(data) {
    const stats = JSON.parse(data);
    state.stats = stats;
    state.lastUpdate = new Date();
    
    // Update the status text
    elements.updateStatus.textContent = `Last update: ${state.lastUpdate.toLocaleTimeString()}`;
    
    // Update the UI with new stats
    updateDeviceStats();
}

function handleHistoryUpdate(deviceIndex, historyData) {
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
    const chart = state.charts[deviceIndex];
    if (!chart) return;
    
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

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', init); 