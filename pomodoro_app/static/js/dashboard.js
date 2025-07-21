// static/js/dashboard.js
// Handles timestamp localisation for dashboard tables.

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

  // (Graph functionality removed)
});
