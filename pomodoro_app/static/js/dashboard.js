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

    console.log("Dashboard timestamp formatting applied.");

}); // end DOMContentLoaded