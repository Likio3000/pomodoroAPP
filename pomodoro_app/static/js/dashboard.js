// static/js/dashboard.js
// Handles timestamp localisation and draws two Chart.js charts.

document.addEventListener('DOMContentLoaded', () => {
  console.log('Dashboard JS loaded');

  /* ---------- 1. Local‑time formatting ---------- */
  document.querySelectorAll('.local-timestamp').forEach(cell => {
    const iso = cell.dataset.timestamp;
    if (!iso) return;
    const d   = new Date(iso);
    if (Number.isNaN(d)) return;
    cell.textContent = d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit'
    });
  });

  /* ---------- 2. Weekly points line chart ---------- */
  const weekPoints = window.weekPoints || [];               // [{date, points}, …]
  if (weekPoints.length && window.Chart) {
    const ctx     = document.getElementById('sessions-chart').getContext('2d');
    const labels  = weekPoints.map(p =>
      new Date(p.date).toLocaleDateString(undefined, { weekday: 'short' })
    );
    const data    = weekPoints.map(p => p.points);

    const themeColors = t =>
      t === 'dark'
        ? { line: '#4dc9f6', text: '#e9e9e9' }
        : { line: '#007bff', text: '#212529' };

    const colors = themeColors(document.body.classList.contains('dark-theme') ? 'dark' : 'light');

    const pointsChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Points',
          data,
          borderColor: colors.line,
          backgroundColor: colors.line,
          tension: 0.25,
          fill: false
        }]
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: colors.text } },
          y: { beginAtZero: true, ticks: { color: colors.text } }
        },
        plugins: {
          legend: { labels: { color: colors.text } },
          tooltip: { intersect: false }
        }
      }
    });

    // live‑update colours when user toggles theme
    document.body.addEventListener('themechange', e => {
      const c = themeColors(e.detail);
      const ds = pointsChart.data.datasets[0];
      ds.borderColor = ds.backgroundColor = c.line;
      pointsChart.options.scales.x.ticks.color           = c.text;
      pointsChart.options.scales.y.ticks.color           = c.text;
      pointsChart.options.plugins.legend.labels.color    = c.text;
      pointsChart.update();
    });
  }

  /* ---------- 3. Session history bar chart (optional) ---------- */
  // If you still want a second chart, either:
  //  - load Chart.js again with a different canvas, OR
  //  - keep Chartist, but then ALSO load its CSS+JS in the template
});
