// pomodoro_app/static/js/dashboard.js

// Wait for the DOM to be fully loaded before running scripts
document.addEventListener('DOMContentLoaded', function() {

    // --- Timestamp Formatting ---
    const timestampCells = document.querySelectorAll('.local-timestamp');
    timestampCells.forEach(cell => {
      const isoTimestamp = cell.getAttribute('data-timestamp');
      if (isoTimestamp) {
        try {
          // Parse the ISO 8601 timestamp
          const date = new Date(isoTimestamp);
  
          // Check if the date is valid after parsing
          if (isNaN(date.getTime())) {
               console.error("Invalid Date parsed from timestamp:", isoTimestamp);
               throw new Error("Invalid Date parsed");
          }
  
          // Format the date using the user's locale settings
          const options = {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit',
            // timeZoneName: 'short' // Optional: show timezone abbreviation
          };
          // 'undefined' uses the browser's default locale and timezone
          cell.textContent = date.toLocaleString(undefined, options);
  
        } catch (e) {
          console.error("Error formatting date:", isoTimestamp, e);
          // Keep the original ISO timestamp or show an error message
           cell.textContent = isoTimestamp + " (Error formatting)";
        }
      } else if (cell.textContent.trim() !== "N/A") { // Only update if not already N/A
          // Handle cases where data-timestamp might be missing or empty
           cell.textContent = "N/A";
      }
    });
  
    // --- Chat Agent JavaScript ---
    // Access configuration passed from the template via the global window object
    const chatConfig = window.dashboardConfig || {}; // Use empty object as fallback
    const chatEnabled = chatConfig.chatEnabled;
    const apiChatUrl = chatConfig.apiChatUrl;
  
    if (chatEnabled && apiChatUrl) { // Only proceed if chat is enabled AND URL is provided
        const chatLog = document.getElementById('chat-log');
        const chatInput = document.getElementById('chat-input');
        const chatSendBtn = document.getElementById('chat-send-btn');
        const chatStatus = document.getElementById('chat-status');
        const dashboardDataDiv = document.getElementById('dashboard-data'); // Get the div holding all data attributes
  
        // Check if essential elements exist
        if (!chatLog || !chatInput || !chatSendBtn || !chatStatus || !dashboardDataDiv) {
            console.error("Chat UI elements not found. Chat functionality may be broken.");
            // Optionally disable chat input visually if elements are missing
            if(chatInput) chatInput.disabled = true;
            if(chatSendBtn) chatSendBtn.disabled = true;
            if(chatStatus) chatStatus.textContent = "Chat UI Error.";
            return; // Stop chat script execution
        }
  
        function addChatMessage(sender, message) {
            const messageDiv = document.createElement('div');
            messageDiv.classList.add('message', sender); // 'user' or 'ai'
            // Basic sanitization: Use textContent to prevent HTML injection
            messageDiv.textContent = message; // Safely sets text content
  
            chatLog.appendChild(messageDiv);
            // Scroll to the bottom smoothly
            chatLog.scrollTo({ top: chatLog.scrollHeight, behavior: 'smooth' });
        }
  
        async function sendChatMessage() {
            const userPrompt = chatInput.value.trim();
            if (!userPrompt) return; // Do nothing if input is empty
  
            // Disable input while processing
            chatInput.disabled = true;
            chatSendBtn.disabled = true;
            chatStatus.textContent = 'Thinking...';
            addChatMessage('user', userPrompt);
            chatInput.value = ''; // Clear input field immediately
  
            // --- *** Get ALL Dashboard Data from data attributes *** ---
            // Read all relevant data attributes from the dashboardDataDiv
            const dashboardData = {
                total_focus: dashboardDataDiv.dataset.totalFocus || '0',
                total_break: dashboardDataDiv.dataset.totalBreak || '0',
                total_sessions: dashboardDataDiv.dataset.totalSessions || '0',
                today_focus: dashboardDataDiv.dataset.todayFocus || '0',       // Added
                today_sessions: dashboardDataDiv.dataset.todaySessions || '0', // Added
                week_focus: dashboardDataDiv.dataset.weekFocus || '0',         // Added
                week_sessions: dashboardDataDiv.dataset.weekSessions || '0'    // Added
            };
            // --------------------------------------------------------------
  
            try {
                // Use the URL passed from the template
                const response = await fetch(apiChatUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        prompt: userPrompt,
                        dashboard_data: dashboardData // Send the enhanced data object
                    })
                });
  
                // Re-enable inputs once response processing starts
                chatInput.disabled = false;
                chatSendBtn.disabled = false;
                chatStatus.textContent = ''; // Clear status
  
                if (!response.ok) {
                    let errorMsg = `HTTP error! Status: ${response.status}`;
                    try {
                         const errorData = await response.json();
                         errorMsg = errorData.error || errorMsg; // Use server error if available
                    } catch (e) {
                         console.warn("Could not parse error response JSON.");
                    }
                    throw new Error(errorMsg); // Propagate error to be caught below
                }
  
                const data = await response.json();
                if (data.response) {
                    addChatMessage('ai', data.response);
                } else if (data.error) {
                     // Handle errors explicitly sent in JSON structure
                     console.error("API returned error in JSON:", data.error);
                     addChatMessage('ai', `Sorry, I encountered an error: ${data.error}`);
                     chatStatus.textContent = 'Error occurred.';
                } else {
                    // Response OK but unexpected format
                    console.error("Unexpected response format:", data);
                    addChatMessage('ai', `Sorry, I received an unexpected response from the server.`);
                    chatStatus.textContent = 'Error occurred.';
                }
  
            } catch (error) {
                console.error("Chat API call failed:", error);
                addChatMessage('ai', `Sorry, I couldn't connect or process your request: ${error.message}`);
                // Ensure inputs are re-enabled in case of fetch/network error
                chatInput.disabled = false;
                chatSendBtn.disabled = false;
                chatStatus.textContent = 'Connection error.';
            } finally {
                 chatInput.focus(); // Put focus back to input field for convenience
            }
        }
  
        // Event Listeners for Chat
        chatSendBtn.addEventListener('click', sendChatMessage);
  
        chatInput.addEventListener('keypress', function(event) {
            // Send message on Enter key press, unless Shift+Enter is used
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault(); // Prevent default newline/submit behavior
                sendChatMessage();
            }
        });
  
    } else {
        // Optional: Log if chat is disabled or URL is missing
        if (!chatEnabled) console.log("Chat feature is disabled via config.");
        if (!apiChatUrl) console.error("Chat API URL is missing. Chat cannot function.");
        // Optionally disable input elements if chat is meant to be enabled but URL is missing
        if (chatEnabled && !apiChatUrl) {
            const chatInput = document.getElementById('chat-input');
            const chatSendBtn = document.getElementById('chat-send-btn');
            if(chatInput) chatInput.disabled = true;
            if(chatSendBtn) chatSendBtn.disabled = true;
            const chatStatus = document.getElementById('chat-status');
            if(chatStatus) chatStatus.textContent = "Chat config error.";
        }
    }
  
  }); // end DOMContentLoaded