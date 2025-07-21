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
    if (sessionsData.length && window.Chartist) {

        function buildChartColors(theme) {
            const dark = theme === 'dark';
            return {
                work: dark ? '#4dc9f6' : '#007bff',
                break: dark ? '#a4e786' : '#28a745',
                text: dark ? '#e9e9e9' : '#212529'
            };
        }

        let colors = buildChartColors(document.body.classList.contains('dark-theme') ? 'dark' : 'light');

        const reversed = sessionsData.slice().reverse();
        const labels = reversed.map(s => {
            const d = new Date(s.timestamp);
            return d.toLocaleDateString();
        });
        const workDur = reversed.map(s => s.work_duration);
        const breakDur = reversed.map(s => s.break_duration);

        const chartContainer = '#sessions-chart';

        function drawChart(theme) {
            colors = buildChartColors(theme);
            const data = { labels: labels, series: [workDur, breakDur] };
            const options = {
                fullWidth: true,
                chartPadding: { right: 40 },
                axisY: { onlyInteger: true }
            };
            const chart = new Chartist.Line(chartContainer, data, options);
            chart.on('created', () => {
                document.querySelectorAll('#sessions-chart .ct-series-a .ct-line, #sessions-chart .ct-series-a .ct-point')
                    .forEach(el => el.style.stroke = colors.work);
                document.querySelectorAll('#sessions-chart .ct-series-b .ct-line, #sessions-chart .ct-series-b .ct-point')
                    .forEach(el => el.style.stroke = colors.break);
                document.querySelectorAll('#sessions-chart .ct-label')
                    .forEach(el => el.style.color = colors.text);
            });
            return chart;
        }

        let chart = drawChart(document.body.classList.contains('dark-theme') ? 'dark' : 'light');

        // Redraw chart when theme changes
        document.body.addEventListener('themechange', (e) => {
            chart = drawChart(e.detail);
        });
    }

    console.log("Dashboard timestamp formatting applied.");

}); // end DOMContentLoaded
