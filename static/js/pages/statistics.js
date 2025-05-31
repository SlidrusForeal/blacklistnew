// Enhanced statistics visualization with Chart.js
(() => {
  'use strict';

  // Configuration
  const CONFIG = {
    colors: {
      font: '#e9ecef',
      border: '#444',
      background: '#2a2a2e',
      chart: {
        primary: '#17a2b8',
        success: '#28a767',
        warning: '#ffc107',
        danger: '#dc3545',
        secondary: '#6c757d'
      }
    },
    chart: {
      animation: {
        duration: 750,
        easing: 'easeOutQuart'
      },
      responsive: true,
      maintainAspectRatio: false
    }
  };

  // Chart instances
  const charts = new Map();

  // Utility functions
  const formatNumber = new Intl.NumberFormat('ru-RU').format;
  
  const createGradient = (ctx, color) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
    gradient.addColorStop(0, `${color}40`);
    gradient.addColorStop(1, `${color}00`);
    return gradient;
  };

  // Setup Chart.js defaults
  const setupChartDefaults = () => {
    if (typeof Chart === 'undefined') {
      throw new Error('Chart.js is not loaded!');
    }

    Chart.defaults.color = CONFIG.colors.font;
    Chart.defaults.borderColor = CONFIG.colors.border;
    Chart.defaults.plugins.legend.labels.color = CONFIG.colors.font;
    Chart.defaults.plugins.tooltip.backgroundColor = CONFIG.colors.background;
    Chart.defaults.plugins.tooltip.titleColor = CONFIG.colors.font;
    Chart.defaults.plugins.tooltip.bodyColor = CONFIG.colors.font;
    Chart.defaults.plugins.tooltip.borderColor = CONFIG.colors.border;
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 4;
  };

  // Create growth chart
  const createGrowthChart = (ctx, data) => {
    if (!ctx || !data.monthlyLabels.length) {
      showNoData(ctx, 'No data available for the growth chart.');
      return;
    }

    const gradient = createGradient(ctx, CONFIG.colors.chart.primary);

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.monthlyLabels,
        datasets: [{
          label: 'Blacklist Additions',
          data: data.monthlyCounts,
          borderColor: CONFIG.colors.chart.primary,
          backgroundColor: gradient,
          borderWidth: 2,
          tension: 0.3,
          fill: true,
          pointBackgroundColor: CONFIG.colors.chart.primary,
          pointBorderColor: CONFIG.colors.background,
          pointBorderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointHoverBorderWidth: 3
        }]
      },
      options: {
        ...CONFIG.chart,
        interaction: {
          mode: 'index',
          intersect: false
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1,
              color: CONFIG.colors.font,
              callback: (value) => formatNumber(value)
            },
            grid: {
              color: CONFIG.colors.border,
              drawBorder: false
            }
          },
          x: {
            ticks: {
              color: CONFIG.colors.font,
              maxRotation: 45,
              minRotation: 45
            },
            grid: {
              color: CONFIG.colors.border,
              drawBorder: false
            }
          }
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: (context) => `Additions: ${formatNumber(context.raw)}`
            }
          }
        }
      }
    });
  };

  // Create reasons chart
  const createReasonsChart = (ctx, data) => {
    if (!ctx || !data.topReasonsLabels.length) {
      showNoData(ctx, 'No data available for top reasons.');
      return;
    }

    const colors = [
      CONFIG.colors.chart.primary,
      CONFIG.colors.chart.success,
      CONFIG.colors.chart.warning,
      CONFIG.colors.chart.danger,
      CONFIG.colors.chart.secondary
    ];

    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.topReasonsLabels,
        datasets: [{
          label: 'Top Reasons',
          data: data.topReasonsCounts,
          backgroundColor: colors.map(color => `${color}CC`),
          borderColor: CONFIG.colors.background,
          borderWidth: 2,
          hoverBackgroundColor: colors.map(color => `${color}FF`),
          hoverBorderColor: CONFIG.colors.font,
          hoverBorderWidth: 2,
          hoverOffset: 8
        }]
      },
      options: {
        ...CONFIG.chart,
        cutout: '60%',
        radius: '90%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              color: CONFIG.colors.font,
              font: {
                size: 12
              },
              padding: 20,
              generateLabels: (chart) => {
                const data = chart.data;
                const total = data.datasets[0].data.reduce((sum, value) => sum + value, 0);
                
                return data.labels.map((label, i) => ({
                  text: `${label} (${Math.round(data.datasets[0].data[i] / total * 100)}%)`,
                  fillStyle: data.datasets[0].backgroundColor[i],
                  strokeStyle: data.datasets[0].borderColor,
                  lineWidth: 1,
                  hidden: isNaN(data.datasets[0].data[i]),
                  index: i
                }));
              }
            }
          },
          tooltip: {
            callbacks: {
              label: (context) => {
                const total = context.dataset.data.reduce((sum, value) => sum + value, 0);
                const value = context.raw;
                const percentage = ((value / total) * 100).toFixed(1);
                return `${context.label}: ${formatNumber(value)} (${percentage}%)`;
              }
            }
          }
        }
      }
    });
  };

  // Show no data message
  const showNoData = (ctx, message) => {
    if (!ctx) return;
    
    const container = ctx.parentElement;
    if (!container) return;

    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';
    container.style.minHeight = '300px';
    
    const messageEl = document.createElement('p');
    messageEl.className = 'text-muted text-center';
    messageEl.style.fontSize = '1.1em';
    messageEl.textContent = message;
    
    container.innerHTML = '';
    container.appendChild(messageEl);
  };

  // Initialize charts
  const initCharts = () => {
    try {
      setupChartDefaults();

      // Growth chart
      const growthCtx = document.getElementById('blacklistGrowthChart')?.getContext('2d');
      if (growthCtx) {
        charts.set('growth', createGrowthChart(growthCtx, window.chartData || {}));
      }

      // Reasons chart
      const reasonsCtx = document.getElementById('topReasonsChart')?.getContext('2d');
      if (reasonsCtx) {
        charts.set('reasons', createReasonsChart(reasonsCtx, window.chartData || {}));
      }

      // Setup resize handler
      const resizeHandler = () => {
        charts.forEach(chart => {
          if (chart) chart.resize();
        });
      };

      window.addEventListener('resize', resizeHandler);

      // Setup theme change handler if needed
      if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
          charts.forEach(chart => {
            if (chart) chart.destroy();
          });
          charts.clear();
          initCharts();
        });
      }

    } catch (error) {
      console.error('Failed to initialize charts:', error);
      document.querySelectorAll('.chart-container').forEach(container => {
        showNoData(container, 'Failed to load charts. Please try again later.');
      });
    }
  };

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCharts);
  } else {
    initCharts();
  }
})(); 