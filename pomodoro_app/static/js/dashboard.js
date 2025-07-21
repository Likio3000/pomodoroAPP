// static/js/dashboard.js
// Handles timestamp localisation for dashboard tables.

document.addEventListener('DOMContentLoaded', () => {
  console.log('Dashboard JS loaded');

  /* ---------- 1. Local‑time formatting ---------- */
  document.querySelectorAll('.local-timestamp').forEach(cell => {
    const iso = cell.dataset.timestamp;
    if (!iso) return;
    const d = new Date(iso);
    if (Number.isNaN(d)) return;
    cell.textContent = d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  });

  /* ---------- 2. Points‑per‑day chart ---------- */
  buildPointsWeekChart();
});

function buildPointsWeekChart() {
  const canvas = document.getElementById('points-week-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  // Gather session history supplied by Flask → Jinja → JS
  const sessions = window.sessionHistory || [];

  // Prepare buckets for the last 7 days (today – 6)
  const DAY_MS = 24 * 60 * 60 * 1000;
  const now    = new Date();
  const buckets = [];        // [{label:'Mon', iso:'yyyy-mm-dd', points:0}, …]

  // Walk backwards 6 days so graph reads chronologically left→right
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getTime() - i * DAY_MS);
    const iso = d.toISOString().slice(0, 10);              // YYYY‑MM‑DD
    buckets.push({
      label: d.toLocaleDateString(undefined, { weekday: 'short' }),
      iso,
      points: 0
    });
  }

  // Sum points into their day bucket
  sessions.forEach(sess => {
    const pts = Number(sess.points_earned);
    if (!sess.timestamp || !Number.isFinite(pts)) return;

    const isoDay = new Date(sess.timestamp).toISOString().slice(0, 10);
    const bucket = buckets.find(b => b.iso === isoDay);
    if (bucket) bucket.points += pts;     // one, and only one, increment
  });

  const labels = buckets.map(b => b.label);
  const data   = buckets.map(b => b.points);

  new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Points',
        data,
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        // rely on Chart.js automatic colour cycle – looks nice in both themes
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => `${ctx.parsed.y} pts` }
        }
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } }
      }
    }
  });

  /* ---------- 3. Theme‑sync (dark / light) ---------- */
  document.body.addEventListener('themechange', () => Chart.helpers.each(Chart.instances, c => c.resize()));
}
