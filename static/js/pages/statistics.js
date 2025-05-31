document.addEventListener('DOMContentLoaded', function() {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js is not loaded!');
        return;
    }

    const defaultFontColor = '#e9ecef';
    const defaultBorderColor = '#444';

    Chart.defaults.color = defaultFontColor;
    Chart.defaults.borderColor = defaultBorderColor;
    Chart.defaults.plugins.legend.labels.color = defaultFontColor;

    // 1. Blacklist Growth Chart (Line Chart)
    const blacklistGrowthCtx = document.getElementById('blacklistGrowthChart');
    if (blacklistGrowthCtx && chartData.monthlyLabels.length > 0) {
        new Chart(blacklistGrowthCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: chartData.monthlyLabels,
                datasets: [{
                    label: 'Количество добавлений в ЧС',
                    data: chartData.monthlyCounts,
                    borderColor: '#17a2b8',
                    backgroundColor: 'rgba(23, 162, 184, 0.2)',
                    tension: 0.1,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1, color: defaultFontColor },
                        grid: { color: defaultBorderColor }
                    },
                    x: {
                         ticks: { color: defaultFontColor },
                         grid: { color: defaultBorderColor }
                    }
                }
            }
        });
    } else if (blacklistGrowthCtx) {
        blacklistGrowthCtx.parentElement.innerHTML += '<p class="text-muted text-center">Данных для графика роста ЧС пока нет.</p>';
    } else {
        console.error("Element with ID 'blacklistGrowthChart' not found.");
    }

    // 2. Top Reasons Chart (Doughnut Chart)
    const topReasonsCtx = document.getElementById('topReasonsChart');
    if (topReasonsCtx && chartData.topReasonsLabels.length > 0) {
        new Chart(topReasonsCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: chartData.topReasonsLabels,
                datasets: [{
                    label: 'Топ причин',
                    data: chartData.topReasonsCounts,
                    backgroundColor: [
                        'rgba(23, 162, 184, 0.8)',  // info
                        'rgba(40, 167, 69, 0.8)',   // success
                        'rgba(255, 193, 7, 0.8)',    // warning
                        'rgba(220, 53, 69, 0.8)',    // danger
                        'rgba(108, 117, 125, 0.8)' // secondary
                    ],
                    borderColor: '#2a2a2e', 
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: defaultFontColor,
                            font: {
                                size: 12
                            }
                        }
                    }
                }
            }
        });
    } else if (topReasonsCtx) {
        topReasonsCtx.parentElement.innerHTML += '<p class="text-muted text-center">Нет данных для отображения топ причин.</p>';
    } else {
        console.error("Element with ID 'topReasonsChart' not found.");
    }
}); 