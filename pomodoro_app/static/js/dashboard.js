// pomodoro_app/static/js/dashboard.js
// ONLY handles dashboard-specific functionality like timestamp formatting.
// Chat logic has been removed and is handled by agent_chat.js

document.addEventListener('DOMContentLoaded', function() {
    console.log("Dashboard JS loaded.");

    // --- Timestamp Formatting ---
    const timestampCells = document.querySelectorAll('.local-timestamp');
    timestampCells.forEach(cell => {
      const isoTimestamp = cell.getAttribute('data-timestamp');
      if (isoTimestamp) {
        try {
          const date = new Date(isoTimestamp);
          if (isNaN(date.getTime())) {
               throw new Error("Invalid Date parsed");
          }
          const options = {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit', hour12: true // Example: Use AM/PM
          };
          cell.textContent = date.toLocaleString(undefined, options); // Use browser locale
          cell.title = isoTimestamp; // Keep ISO string in title attribute for clarity
        } catch (e) {
          console.error("Error formatting date:", isoTimestamp, e);
           cell.textContent = isoTimestamp + " (Invalid Date)";
           cell.title = "Error formatting this date";
        }
      } else if (cell.textContent.trim() !== "N/A") {
           cell.textContent = "N/A";
           cell.title = "Timestamp unavailable";
      }
    });

    // --- Chat Agent JavaScript Removed ---
    // All chat functionality is now handled by the global agent_chat.js script,
    // which creates a floating widget.


    // --- Weekly Points Chart ---
    const weekPoints = window.weekPoints || [];
    if (weekPoints.length && window.Chart) {
        const ctx = document.getElementById('sessions-chart').getContext('2d');

        function buildChartColors(theme) {
            const dark = theme === 'dark';
            return {
                line: dark ? '#4dc9f6' : '#007bff',
                text: dark ? '#e9e9e9' : '#212529'
            };
        }

        const labels = weekPoints.map(p => {
            const d = new Date(p.date);
            return d.toLocaleDateString(undefined, { weekday: 'short' });
        });
        const points = weekPoints.map(p => p.points);

        let colors = buildChartColors(document.body.classList.contains('dark-theme') ? 'dark' : 'light');

        const config = {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Points',
                    data: points,
                    borderColor: colors.line,
                    backgroundColor: colors.line,
                    tension: 0.1,
                }]
            },
            options: {
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { color: colors.text } },
                    x: { ticks: { color: colors.text } }
                },
                plugins: { legend: { labels: { color: colors.text } } }
            }
        };

        let chart = new Chart(ctx, config);

        document.body.addEventListener('themechange', (e) => {
            colors = buildChartColors(e.detail);
            chart.options.scales.x.ticks.color = colors.text;
            chart.options.scales.y.ticks.color = colors.text;
            chart.options.plugins.legend.labels.color = colors.text;
            chart.data.datasets[0].borderColor = colors.line;
            chart.data.datasets[0].backgroundColor = colors.line;
            chart.update();
        });
    }

    console.log("Dashboard timestamp formatting applied.");

}); // end DOMContentLoaded
