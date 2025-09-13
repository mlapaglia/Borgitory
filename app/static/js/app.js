// Core Alpine.js App Component
function borgitoryApp() {
    return {
        cloudSyncConfigs: [],
        notificationConfigs: [],
        cleanupConfigs: [],
        checkConfigs: [],
        
        initApp() {
        },
    };
}

// Chart instances (global scope for updates)
let sizeChart = null;
let ratioChart = null;
let fileTypeCountChart = null;
let fileTypeSizeChart = null;

// HTMX Event Listeners
document.body.addEventListener('htmx:afterSwap', function(e) {

    // Chart.js Integration
    // Check if we swapped in chart data
    if (e.target.id === 'statistics-content' || e.target.querySelector('#chart-data')) {
        const chartDataEl = e.target.querySelector('#chart-data') || document.getElementById('chart-data');
        
        if (chartDataEl && chartDataEl.dataset.sizeChart) {
            try {
                const sizeDataRaw = chartDataEl.getAttribute('data-size-chart');
                const ratioDataRaw = chartDataEl.getAttribute('data-ratio-chart');
                const fileTypeCountDataRaw = chartDataEl.getAttribute('data-file-type-count-chart');
                const fileTypeSizeDataRaw = chartDataEl.getAttribute('data-file-type-size-chart');
                
                const sizeData = JSON.parse(sizeDataRaw);
                const ratioData = JSON.parse(ratioDataRaw);
                const fileTypeCountData = JSON.parse(fileTypeCountDataRaw);
                const fileTypeSizeData = JSON.parse(fileTypeSizeDataRaw);
                
                if (sizeChart && ratioChart && fileTypeCountChart && fileTypeSizeChart) {
                    updateCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData);
                } else {
                    createCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData);
                }
            } catch (error) {
                console.error('Error processing chart data:', error);
            }
        }
    }
});

function createCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData) {
    const sizeCtx = document.getElementById('sizeChart');
    const ratioCtx = document.getElementById('ratioChart');
    const fileTypeCountCtx = document.getElementById('fileTypeCountChart');
    const fileTypeSizeCtx = document.getElementById('fileTypeSizeChart');
    
    if (sizeCtx && ratioCtx) {
        // Create Size Chart
        sizeChart = new Chart(sizeCtx, {
            type: 'line',
            data: sizeData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Size (MB)'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Archive Date'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Repository Size Growth'
                    },
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Create Ratio Chart
        ratioChart = new Chart(ratioCtx, {
            type: 'line',
            data: ratioData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Compression Ratio (%)'
                        },
                        min: 0,
                        max: 100
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Deduplication Ratio (%)'
                        },
                        min: 0,
                        max: 100,
                        grid: {
                            drawOnChartArea: false,
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Archive Date'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Compression & Deduplication Efficiency'
                    },
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
        
        // Create File Type Count Chart
        if (fileTypeCountCtx && fileTypeCountData) {
            fileTypeCountChart = new Chart(fileTypeCountCtx, {
                type: 'line',
                data: fileTypeCountData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'File Count'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Archive Date'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
        
        // Create File Type Size Chart
        if (fileTypeSizeCtx && fileTypeSizeData) {
            fileTypeSizeChart = new Chart(fileTypeSizeCtx, {
                type: 'line',
                data: fileTypeSizeData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Size (MB)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Archive Date'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        }
                    }
                }
            });
        }
    }
}

function updateCharts(sizeData, ratioData, fileTypeCountData, fileTypeSizeData) {
    if (sizeChart) {
        sizeChart.data = sizeData;
        sizeChart.update('none'); // No animation for smooth updates
    }
    
    if (ratioChart) {
        ratioChart.data = ratioData;
        ratioChart.update('none');
    }
    
    if (fileTypeCountChart && fileTypeCountData) {
        fileTypeCountChart.data = fileTypeCountData;
        fileTypeCountChart.update('none');
    }
    
    if (fileTypeSizeChart && fileTypeSizeData) {
        fileTypeSizeChart.data = fileTypeSizeData;
        fileTypeSizeChart.update('none');
    }
}

// Dark Mode Functions
function toggleDarkMode() {
    const html = document.documentElement;
    const isDark = html.classList.contains('dark');
    
    if (isDark) {
        html.classList.remove('dark');
        localStorage.setItem('darkMode', 'false');
    } else {
        html.classList.add('dark');
        localStorage.setItem('darkMode', 'true');
    }
}

function initializeDarkMode() {
    const savedMode = localStorage.getItem('darkMode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedMode === 'true' || (savedMode === null && prefersDark)) {
        document.documentElement.classList.add('dark');
    }
}

// Initialize dark mode on page load
document.addEventListener('DOMContentLoaded', initializeDarkMode);