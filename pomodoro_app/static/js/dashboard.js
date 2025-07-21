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


    // --- Sessions Chart ---
    const sessionsData = window.sessionHistory || [];
    if (sessionsData.length && window.Chart) {
        const ctx = document.getElementById('sessions-chart').getContext('2d');

        function buildChartColors(theme) {
            const dark = theme === 'dark';
            return {
                work: dark ? '#4dc9f6' : '#007bff',
                break: dark ? '#a4e786' : '#28a745',
                text: dark ? '#e9e9e9' : '#212529'
            };
        }

        let colors = buildChartColors(document.body.classList.contains('dark-theme') ? 'dark' : 'light');

        const labels = sessionsData.slice().reverse().map(s => {
            const d = new Date(s.timestamp);
            return d.toLocaleDateString();
        });
        const workDur = sessionsData.slice().reverse().map(s => s.work_duration);
        const breakDur = sessionsData.slice().reverse().map(s => s.break_duration);

        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Work (min)',
                        data: workDur,
                        borderColor: colors.work,
                        backgroundColor: colors.work,
                        tension: 0.1
                    },
                    {
                        label: 'Break (min)',
                        data: breakDur,
                        borderColor: colors.break,
                        backgroundColor: colors.break,
                        tension: 0.1
                    }
                ]
            },
            options: {
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { color: colors.text } },
                    x: { ticks: { color: colors.text } }
                },
                plugins: {
                    legend: { labels: { color: colors.text } }
                }
            }
        });

        // Update chart colors when theme changes
        document.body.addEventListener('themechange', (e) => {
            colors = buildChartColors(e.detail);
            chart.options.scales.x.ticks.color = colors.text;
            chart.options.scales.y.ticks.color = colors.text;
            chart.options.plugins.legend.labels.color = colors.text;
            chart.data.datasets[0].borderColor = colors.work;
            chart.data.datasets[0].backgroundColor = colors.work;
            chart.data.datasets[1].borderColor = colors.break;
            chart.data.datasets[1].backgroundColor = colors.break;
            chart.update();
        });
    }

    console.log("Dashboard timestamp formatting applied.");

}); // end DOMContentLoaded