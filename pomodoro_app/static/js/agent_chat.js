// agent_chat.js
// Handles chat UI, agent selection, audio playback, and chat history persistence
// for the Pomodoro AI assistant using sessionStorage.

// --- AGENT DEFINITIONS ---
const AGENTS = {
    "default": { name: "Assistant", voice: "alloy" },
    "motivator": { name: "Motivator", voice: "nova" },
    "coach": { name: "Coach", voice: "shimmer" }
};

// --- Session Storage Key and In-Memory History ---
const CHAT_HISTORY_KEY = 'pomodoroAgentChatHistory_v1'; // Added versioning
let chatHistory = []; // In-memory representation of the history


// --- UI Construction ---
function createAgentChatBox() {
    // Only create if it doesn't exist
    if (document.getElementById('agent-chatbox')) return;

    const chatBox = document.createElement('div');
    chatBox.id = 'agent-chatbox';
    // Added aria-live for accessibility on status
    chatBox.innerHTML = `
        <div class="agent-chat-header">AI Assistant <span id="agent-status" aria-live="polite"></span></div>
        <div id="agent-chat-log" class="agent-chat-log" aria-live="polite" aria-atomic="false"></div>
        <div class="agent-chat-controls agent-chat-controls-col">
            <div class="agent-chat-row">
                <label for="agent-type-select" class="visually-hidden">Select Agent Personality</label>
                <select id="agent-type-select">
                    ${Object.entries(AGENTS).map(([k, v]) => `<option value="${k}">${v.name}</option>`).join('')}
                </select>
            </div>
            <div class="agent-chat-row agent-chat-input-row">
                <label for="agent-chat-input" class="visually-hidden">Chat Message Input</label>
                <input id="agent-chat-input" type="text" placeholder="Type your message..." autocomplete="off" />
                <button id="agent-chat-send">Send</button>
            </div>
        </div>
        <div class="agent-chat-settings">
            <label for="tts-toggle"><input type="checkbox" id="tts-toggle"> Enable TTS</label>
        </div>
        <audio id="agent-chat-audio" style="display:none;"></audio>
    `;
    document.body.appendChild(chatBox);
    console.log("Agent chatbox created.");
}

// --- Chat Logic & History Management ---

// Helper function to render message without modifying history array or saving
function renderMessageWithoutSaving(text, sender = 'ai') {
    const log = document.getElementById('agent-chat-log');
    if (!log) {
        console.error("Chat log element not found in renderMessageWithoutSaving.");
        return;
    }
    const msg = document.createElement('div');
    msg.className = 'agent-message ' + sender;

    // --- Use the same Markdown/Sanitization logic ---
    const prefix = sender === 'ai' ? '<strong>AI:</strong> ' : '<strong>You:</strong> ';
    msg.innerHTML = prefix; // Set prefix first

    if (sender === 'ai') {
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            try {
                const rawHtml = marked.parse(text, { breaks: true });
                const cleanHtml = DOMPurify.sanitize(rawHtml);
                // Append the sanitized HTML *after* the prefix
                msg.innerHTML += cleanHtml;
            } catch (e) {
                console.error("Error parsing/sanitizing Markdown:", e);
                msg.appendChild(document.createTextNode(text)); // Fallback
            }
        } else {
            console.warn("Marked.js or DOMPurify not loaded. Rendering AI message as plain text.");
            msg.appendChild(document.createTextNode(text)); // Fallback
        }
    } else { // User message
        msg.appendChild(document.createTextNode(text)); // Append user text safely
    }
    // --- End Markdown/Sanitization logic ---

    log.appendChild(msg);
    // Scroll only if the log isn't already scrolled up by the user
    // (Simple check: is scroll position near the bottom?)
    if (log.scrollHeight - log.scrollTop <= log.clientHeight + 50) {
         log.scrollTop = log.scrollHeight;
    }
}


// Modified function to parse Markdown, sanitize, AND SAVE history
function appendAgentMessage(text, sender = 'ai') {
    // 1. Render the message visually using the helper
    renderMessageWithoutSaving(text, sender);

    // 2. Add the new message to the in-memory array
    chatHistory.push({ sender: sender, text: text });

    // 3. Save the updated array to sessionStorage
    try {
        // Limit history size to prevent storage issues (e.g., last 50 messages)
        const maxHistoryLength = 50;
        if (chatHistory.length > maxHistoryLength) {
             chatHistory = chatHistory.slice(-maxHistoryLength); // Keep only the last N messages
        }
        sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
        // console.log(`Chat history saved (${chatHistory.length} messages).`); // Debug
    } catch (e) {
        console.error("Error saving chat history to sessionStorage:", e);
        if (e.name === 'QuotaExceededError') {
             // Simple recovery: try clearing and saving just the last message
             console.warn("SessionStorage quota exceeded. Clearing history and saving last message.");
             chatHistory = chatHistory.slice(-1); // Keep only the last one
             try {
                 sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
             } catch (e2) {
                 console.error("Failed to save even the last message after quota error:", e2);
             }
        }
    }
}

function setAgentStatus(status) {
    const statusEl = document.getElementById('agent-status');
    if (statusEl) { // Check if element exists
        statusEl.textContent = status ? `(${status})` : ''; // Add parentheses for visual separation
    }
}

async function sendAgentMessage() {
    const input = document.getElementById('agent-chat-input');
    const agentTypeSelect = document.getElementById('agent-type-select');
    const ttsToggle = document.getElementById('tts-toggle');
    const sendBtn = document.getElementById('agent-chat-send');

    if (!input || !agentTypeSelect || !ttsToggle || !sendBtn) {
        console.error("Chat input, agent select, TTS toggle, or send button missing.");
        setAgentStatus("UI Error");
        return;
    }

    const agentType = agentTypeSelect.value;
    const message = input.value.trim();
    const isTtsEnabledByUser = ttsToggle.checked;

    if (!message) return;

    appendAgentMessage(message, 'user'); // Adds to UI and saves history
    input.value = ''; // Clear input
    input.disabled = true; // Disable input during processing
    sendBtn.disabled = true; // Disable send button
    setAgentStatus('...'); // Indicate thinking

    // Use dashboard data if available (from dashboard.js context)
    const dashboardData = window.dashboardConfig ? window.dashboardConfig.initialData : {};

    try {
        // Ensure correct API endpoint (might be relative or absolute depending on context)
        // Using a relative URL assumes agent_chat.js is used on pages served from the main blueprint root
        const apiUrl = '/api/chat'; // Or fetch from a config if needed: window.chatConfig.apiUrl

        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({
                prompt: message,
                dashboard_data: dashboardData, // Backend might re-fetch fresh data anyway
                agent_type: agentType,
                tts_enabled: isTtsEnabledByUser
            })
        });

        const data = await response.json(); // Try parsing JSON regardless of status

        if (!response.ok) {
             // Use error from JSON body if available, otherwise use status text
             throw new Error(data.error || `Server error: ${response.status} ${response.statusText}`);
        }

        if (data.response) {
            appendAgentMessage(data.response, 'ai'); // Adds AI response to UI and saves history
            if (data.audio_url) {
                playAgentAudio(data.audio_url); // Play audio if URL provided and TTS toggle is checked
            }
        } else if (data.error) { // Handle specific error message from server JSON even on 2xx response
             appendAgentMessage(`Sorry, there was an error: ${data.error}`, 'ai');
        } else {
            // Handle unexpected success response format
             appendAgentMessage('Sorry, the assistant sent an empty or unexpected response.', 'ai');
        }

    } catch (err) {
        console.error("Error sending/receiving agent message:", err);
        // Provide user feedback about the error
        appendAgentMessage(`Error: ${err.message || 'Could not contact AI service.'}`, 'ai');
    } finally {
        // Always re-enable input and clear status
        input.disabled = false;
        sendBtn.disabled = false;
        setAgentStatus('');
        input.focus(); // Focus input for next message
    }
}


function playAgentAudio(audioUrl) {
    const ttsToggle = document.getElementById('tts-toggle');
    // Check toggle *before* attempting to play
    if (!ttsToggle || !ttsToggle.checked) {
        console.log("TTS is disabled via toggle. Skipping audio playback.");
        return;
    }

    const audio = document.getElementById('agent-chat-audio');
    if (!audio) {
        console.error("Agent chat audio element not found!");
        return;
    }

    // Stop any currently playing audio before starting new one
    if (!audio.paused) {
        audio.pause();
        audio.currentTime = 0;
    }

    audio.src = audioUrl;
    // Removed style.display change

    const playPromise = audio.play();

    if (playPromise !== undefined) {
        playPromise.then(_ => {
            // Automatic playback started!
            console.log('Agent audio playing:', audioUrl);
            audio.onended = () => console.log('Agent audio finished.');
        })
        .catch(error => {
            // Auto-play was prevented
            console.error('Audio play() failed:', error);
            if (error.name === 'NotAllowedError') {
                 setAgentStatus("Audio blocked"); // Inform user subtly
                 console.warn('Audio playback failed. Browser requires user interaction.');
                 // Maybe add a button later to explicitly play the audio if needed
            } else {
                 setAgentStatus("Audio error");
                 console.error('An unexpected error occurred during audio playback.');
            }
        });
    }
     audio.onerror = (e) => {
        console.error('Error loading or playing agent audio:', e);
        setAgentStatus("Audio error");
     };
}

function setupAgentChatEvents() {
    const sendBtn = document.getElementById('agent-chat-send');
    const inputField = document.getElementById('agent-chat-input');

    if (sendBtn) {
        sendBtn.onclick = sendAgentMessage;
    } else {
        console.error("Agent chat send button not found!");
    }

    if (inputField) {
        inputField.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                 e.preventDefault();
                 sendAgentMessage();
            }
        });
    } else {
        console.error("Agent chat input field not found!");
    }
}

// --- Timer Event Hooks (Optional Integration) ---
// Call this from timer logic (timer.js) if needed to populate input
window.triggerAgentEvent = function(eventType) {
    const agentInput = document.getElementById('agent-chat-input');
    if (!agentInput) {
        console.warn("Agent chat UI not ready, cannot trigger event:", eventType);
        return;
    }

    let prompt = '';
    if (eventType === 'timer_start') prompt = "I'm starting a new Pomodoro session! Any tips?";
    else if (eventType === 'timer_complete') prompt = "I just finished a Pomodoro work session!";
    else if (eventType === 'break_start') prompt = "It's break time. How should I recharge effectively?";
    else if (eventType === 'break_end') prompt = "Break's over. Any advice for getting back into focus?";

    if (prompt) {
        agentInput.value = prompt; // Populate input, let user send
        // agentInput.focus(); // Optionally focus
    }
};

// --- Initialization on page load ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("Agent chat DOMContentLoaded. Initializing...");

    // 1. Ensure the chatbox UI exists (create if not)
    createAgentChatBox(); // Safe to call even if it exists

    // 2. Load and Render History from Session Storage
    try {
        const storedHistory = sessionStorage.getItem(CHAT_HISTORY_KEY);
        const log = document.getElementById('agent-chat-log'); // Get log element

        if (storedHistory && log) {
            chatHistory = JSON.parse(storedHistory); // Load into memory
            console.log(`Loaded ${chatHistory.length} messages from sessionStorage.`);

            // Render loaded messages
            chatHistory.forEach(message => {
                renderMessageWithoutSaving(message.text, message.sender);
            });
            // Ensure scroll is at the bottom after loading history
             log.scrollTop = log.scrollHeight;

        } else if (log && log.children.length === 0) { // Add default greeting ONLY if no history AND log is empty
            console.log("No chat history found or log was empty. Adding default greeting.");
             // This call will render AND save the greeting as the first item
            appendAgentMessage("Hello! Ask me about your Pomodoro stats or for productivity tips.", 'ai');
        } else {
             console.log("No chat history found in sessionStorage or log wasn't empty.");
        }
    } catch (e) {
        console.error("Error loading/parsing chat history:", e);
        sessionStorage.removeItem(CHAT_HISTORY_KEY); // Clear potentially corrupted data
        chatHistory = []; // Reset in-memory history
    }

    // 3. Setup Event Listeners
    setupAgentChatEvents();

    // 4. Set Initial TTS Toggle State
    const ttsToggle = document.getElementById('tts-toggle');
    if (ttsToggle) {
        // Default to checked unless global config explicitly disables it
        let defaultTtsState = true;
        // Check if a global config object exists from the main app templates
        if (window.pomodoroConfig && typeof window.pomodoroConfig.ttsGloballyEnabled === 'boolean') {
            defaultTtsState = window.pomodoroConfig.ttsGloballyEnabled;
        } else if (window.dashboardConfig && typeof window.dashboardConfig.ttsGloballyEnabled === 'boolean') {
             defaultTtsState = window.dashboardConfig.ttsGloballyEnabled;
        }
        ttsToggle.checked = defaultTtsState;
        console.log(`Initial TTS toggle state set to: ${defaultTtsState}`);
    } else {
        console.error("TTS toggle element not found!");
    }

    console.log("Agent chat initialization complete.");
});


// --- Minimal styles (ensure these are loaded, e.g., via base CSS or here) ---
// Added visually-hidden class for accessibility labels
if (!document.getElementById('agent-chat-styles')) {
    const style = document.createElement('style');
    style.id = 'agent-chat-styles';
    style.textContent = `
    .visually-hidden {
        position: absolute; width: 1px; height: 1px;
        padding: 0; margin: -1px; overflow: hidden;
        clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
    }
    #agent-chatbox {
        position: fixed; bottom: 20px; right: 20px; width: 350px; z-index: 1050; /* Higher z-index */
        background: #ffffff; border-radius: 10px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        font-family: inherit; border: 1px solid #d0d0d0;
        max-height: calc(100vh - 40px); /* Prevent full screen height */
        display: flex;
        flex-direction: column;
        font-size: 0.95rem; /* Base font size */
        transition: box-shadow 0.3s ease;
    }
    #agent-chatbox:focus-within { /* Highlight when interacting */
        box-shadow: 0 8px 25px rgba(0, 123, 255, 0.2);
    }
    .agent-chat-header {
        padding: 10px 14px; font-weight: 600; color: #333;
        background: #f7f7f9; border-bottom: 1px solid #eee;
        border-radius: 10px 10px 0 0; flex-shrink: 0;
        display: flex; justify-content: space-between; align-items: center;
    }
    #agent-status { font-size: 0.85em; color: #777; font-weight: 500; }
    .agent-chat-log {
        flex-grow: 1; /* Allow log to take available space */
        overflow-y: auto;
        padding: 12px;
        background: #fdfdfd;
        min-height: 150px; /* Ensure minimum height */
        max-height: 350px; /* Limit max height */
    }
    .agent-message { margin-bottom: 8px; padding: 8px 12px; border-radius: 12px; max-width: 88%; word-wrap: break-word; line-height: 1.45; clear: both; box-shadow: 0 1px 2px rgba(0,0,0,0.05);}
    .agent-message.user { background: #007bff; color: white; text-align: left; float: right; border-bottom-right-radius: 4px; margin-left: auto; }
    .agent-message.ai { background: #e9ecef; color: #343a40; text-align: left; float: left; border-bottom-left-radius: 4px; margin-right: auto; }
    .agent-message strong { font-weight: 600; } /* Bolder prefix */
    /* Styling for markdown elements inside AI messages */
    .agent-message.ai p { margin: 0.5em 0; }
    .agent-message.ai ul, .agent-message.ai ol { margin: 0.5em 0 0.5em 1.2em; padding-left: 0.5em; }
    .agent-message.ai li { margin-bottom: 0.3em; }
    .agent-message.ai em { font-style: italic; }
    .agent-message.ai a { color: #0056b3; text-decoration: underline; }
    .agent-message.ai a:hover { color: #003d80; }
    .agent-message.ai code { background-color: #dde1e4; padding: 0.15em 0.4em; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
    .agent-message.ai pre { background-color: #dde1e4; padding: 0.6em; border-radius: 5px; overflow-x: auto; font-family: monospace; font-size: 0.85em; margin: 0.5em 0; }
    .agent-message.ai pre code { background-color: transparent; padding: 0; border-radius: 0; font-size: 1em; }
    .agent-message.ai blockquote { border-left: 3px solid #adb5bd; padding-left: 0.8em; margin: 0.5em 0 0.5em 0.2em; color: #495057; font-style: italic; }
    .agent-chat-controls.agent-chat-controls-col { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-top: 1px solid #eee; flex-shrink: 0; background: #f7f7f9; }
    .agent-chat-row { display: flex; gap: 8px; align-items: center; }
    #agent-type-select { flex-grow: 1; font-size: 0.9em; padding: 6px 8px; border-radius: 5px; border: 1px solid #ccc; background-color: #fff; height: 36px; min-width: 80px; }
    #agent-chat-input { flex-grow: 1; font-size: 1em; border-radius: 5px; border: 1px solid #ccc; padding: 8px 10px; min-width: 0; height: 36px; box-sizing: border-box; }
    #agent-chat-input:disabled { background-color: #e9ecef; cursor: not-allowed; }
    #agent-chat-send { flex-shrink: 0; padding: 0 14px; background: #007bff; color: #fff; border: none; border-radius: 5px; font-weight: 600; cursor: pointer; font-size: 0.95em; height: 36px; transition: background-color 0.2s ease; }
    #agent-chat-send:hover { background: #0056b3; }
    #agent-chat-send:disabled { background: #a0cfff; cursor: not-allowed; }
    .agent-chat-settings { padding: 8px 14px; border-top: 1px solid #eee; text-align: right; flex-shrink: 0; font-size: 0.9em; background: #f7f7f9; border-radius: 0 0 10px 10px; }
    .agent-chat-settings label { color: #555; cursor: pointer; display: inline-flex; align-items: center; }
    .agent-chat-settings input[type="checkbox"] { margin-right: 5px; vertical-align: middle; cursor: pointer; height: 14px; width: 14px; }

    @media (max-width: 400px) { /* Adjustments for very small screens */
        #agent-chatbox { width: calc(100vw - 20px); bottom: 10px; right: 10px; font-size: 0.9rem; }
        .agent-chat-log { max-height: 300px; }
        #agent-chat-send { padding: 0 10px; }
    }
    `;
    // Add styles safely to head
    try {
        document.head.appendChild(style);
    } catch (e) { // Handle environments where document.head might not be standard (less common in browsers)
        console.error("Could not append chat styles to document head:", e);
        try { document.getElementsByTagName('head')[0].appendChild(style); } catch (e2) {} // Fallback
    }
} else {
    // console.log("Agent chat styles already added."); // Optional: Can be noisy
}