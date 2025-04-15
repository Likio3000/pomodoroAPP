// agent_chat.js
// Handles chat UI, agent selection, and audio playback for the Pomodoro AI assistant

// --- AGENT DEFINITIONS ---
// To add or edit agents, modify the AGENTS object below.
// Each agent has a key, a display name, and a TTS voice.
const AGENTS = {
    "default": { name: "Assistant", voice: "alloy" },
    "motivator": { name: "Motivator", voice: "nova" },
    "coach": { name: "Coach", voice: "shimmer" }
};

// --- UI Construction ---
function createAgentChatBox() {
    const chatBox = document.createElement('div');
    chatBox.id = 'agent-chatbox';
    chatBox.innerHTML = `
        <div class="agent-chat-header">AI Assistant <span id="agent-status"></span></div>
        <div id="agent-chat-log" class="agent-chat-log"></div>
        <div class="agent-chat-controls agent-chat-controls-col">
            <div class="agent-chat-row">
                <select id="agent-type-select">
                    ${Object.entries(AGENTS).map(([k, v]) => `<option value="${k}">${v.name}</option>`).join('')}
                </select>
            </div>
            <div class="agent-chat-row agent-chat-input-row">
                <input id="agent-chat-input" type="text" placeholder="Type your message..." autocomplete="off" />
                <button id="agent-chat-send">Send</button>
            </div>
        </div>
        <div class="agent-chat-settings" style="padding: 8px; border-top: 1px solid #eee; text-align: right;">
            <label><input type="checkbox" id="tts-toggle"> Enable TTS</label>
        </div>
        <audio id="agent-chat-audio" style="display:none;"></audio>
    `;
    document.body.appendChild(chatBox);
}

// --- Chat Logic ---
// *** MODIFIED function to parse Markdown and sanitize ***
function appendAgentMessage(text, sender = 'ai') {
    const log = document.getElementById('agent-chat-log');
    const msg = document.createElement('div');
    msg.className = 'agent-message ' + sender;

    if (sender === 'ai') {
        // Render Markdown for AI responses, sanitize HTML
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') { // Check both libs
            try {
                // Parse Markdown to HTML, enabling line breaks
                const rawHtml = marked.parse(text, { breaks: true });
                // Sanitize the generated HTML to prevent XSS
                const cleanHtml = DOMPurify.sanitize(rawHtml);
                // Set the innerHTML safely
                msg.innerHTML = `<strong>AI:</strong> ` + cleanHtml;
            } catch (e) {
                console.error("Error parsing/sanitizing Markdown in agent chat:", e);
                // Fallback to textContent on error for security
                msg.innerHTML = `<strong>AI:</strong> `; // Add prefix
                msg.appendChild(document.createTextNode(text)); // Append text safely
            }
        } else {
            console.warn("Marked.js or DOMPurify not loaded for agent chat. Rendering AI message as plain text.");
            // Fallback if libraries aren't loaded
            msg.innerHTML = `<strong>AI:</strong> `; // Add prefix
            msg.appendChild(document.createTextNode(text)); // Append text safely
        }
    } else {
        // User message: ALWAYS use text node for security
        msg.innerHTML = `<strong>You:</strong> `; // Add prefix
        msg.appendChild(document.createTextNode(text));
    }

    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
}
// *** END MODIFIED function ***

function setAgentStatus(status) {
    const statusEl = document.getElementById('agent-status');
    if (statusEl) { // Check if element exists
        statusEl.textContent = status;
    }
}

async function sendAgentMessage() {
    const input = document.getElementById('agent-chat-input');
    const agentTypeSelect = document.getElementById('agent-type-select');
    if (!input || !agentTypeSelect) {
        console.error("Chat input or agent select missing.");
        return;
    }
    const agentType = agentTypeSelect.value;
    const message = input.value.trim();

    if (!message) return;

    appendAgentMessage(message, 'user'); // Uses the updated function
    input.value = '';
    setAgentStatus('...');

    // Optionally, collect dashboard data from your app (dummy for now)
    const dashboardData = window.getDashboardData ? window.getDashboardData() : {};

    try {
        const response = await fetch('/api/chat', { // Ensure this URL is correct for your app context
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: message,
                dashboard_data: dashboardData,
                agent_type: agentType
            })
        });
        const data = await response.json();
        if (data.response) {
            appendAgentMessage(data.response, 'ai'); // Uses the updated function
            if (data.audio_url) {
                playAgentAudio(data.audio_url);
            }
        } else if (data.error) { // Handle specific error from server JSON
             appendAgentMessage(`Sorry, there was an error: ${data.error}`, 'ai');
        } else {
            appendAgentMessage('Sorry, the assistant is unavailable or sent an empty response.', 'ai'); // Uses the updated function
        }
    } catch (err) {
        console.error("Error sending agent message:", err);
        appendAgentMessage(`Error contacting AI service: ${err.message}`, 'ai'); // Uses the updated function
    }
    setAgentStatus('');
}

function playAgentAudio(audioUrl) {
    // Check if TTS is enabled via the toggle before playing
    const ttsToggle = document.getElementById('tts-toggle');
    if (!ttsToggle || !ttsToggle.checked) {
        console.log("TTS is disabled via toggle. Skipping audio playback.");
        return;
    }
    const audio = document.getElementById('agent-chat-audio');
    if (!audio) {
        console.error("Agent chat audio element not found!");
        return;
    }
    audio.src = audioUrl;
    audio.style.display = 'block'; // Make visible for debugging if needed, usually hidden
    audio.onplay = () => console.log('Agent audio playing:', audioUrl);
    audio.onerror = (e) => {
        console.error('Error playing agent audio:', e);
        alert('Could not play agent audio. Check browser console for details.');
    };
    audio.play().catch(err => {
        console.error('Audio play() failed:', err);
        // Provide more user-friendly feedback if possible
        if (err.name === 'NotAllowedError') {
            alert('Audio playback failed. Browsers often require user interaction (like a click) before playing audio. Please click anywhere on the page and try sending the message again.');
        } else {
            alert('Audio playback failed. Check browser console for details.');
        }
    });
}

function setupAgentChatEvents() {
    // Ensure elements exist before adding listeners
    const sendBtn = document.getElementById('agent-chat-send');
    const inputField = document.getElementById('agent-chat-input');

    if (sendBtn) {
        sendBtn.onclick = sendAgentMessage;
    } else {
        console.error("Agent chat send button not found!");
    }

    if (inputField) {
        inputField.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) { // Send on Enter, not Shift+Enter
                 e.preventDefault(); // Prevent default newline/form submission
                 sendAgentMessage();
            }
        });
    } else {
        console.error("Agent chat input field not found!");
    }
}

// --- Timer Event Hooks ---
// Call this from your timer logic to trigger agent messages
window.triggerAgentEvent = function(eventType) {
    // Ensure UI elements are ready before triggering
    const agentSelect = document.getElementById('agent-type-select');
    const agentInput = document.getElementById('agent-chat-input');

    if (!agentSelect || !agentInput) {
        console.warn("Agent chat UI not ready, cannot trigger event:", eventType);
        return;
    }

    const agentType = agentSelect.value;
    let prompt = '';
    if (eventType === 'timer_start') prompt = "I'm starting a new Pomodoro session! Any tips?";
    else if (eventType === 'timer_complete') prompt = "I just finished a Pomodoro!";
    else if (eventType === 'break_start') prompt = "It's break time. How should I recharge?";
    else if (eventType === 'break_end') prompt = "Break's over. Any advice for getting back to work?";

    if (prompt) {
        agentInput.value = prompt;
        sendAgentMessage();
    }
};

// --- Initialize on page load ---
document.addEventListener('DOMContentLoaded', function() {
    // Check if the chatbox container already exists (e.g., from dashboard.js)
    // Only create if it doesn't exist - avoids duplicate chat boxes if scripts run on same page
    if (!document.getElementById('agent-chatbox')) {
         createAgentChatBox();
         setupAgentChatEvents();
    } else {
        console.log("Agent chatbox already exists, reusing existing elements.");
        // If reusing, make sure events are attached (might need adjustment if conflicts arise)
        // Ensure listeners are attached even if box exists
        setupAgentChatEvents();
    }
});

// --- Minimal styles (could move to CSS file) ---
// Avoid adding style if it already exists (e.g., from dashboard.js or another instance)
if (!document.getElementById('agent-chat-styles')) {
    const style = document.createElement('style');
    style.id = 'agent-chat-styles'; // Add ID to check for existence
    style.textContent = `
    #agent-chatbox {
        position: fixed; bottom: 24px; right: 24px; width: 340px; z-index: 9999;
        background: #fff; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.15);
        font-family: inherit; border: 1px solid #e0e0e0;
        max-height: calc(100vh - 48px); /* Prevent overflow on small screens */
        display: flex; /* Use flex for better height management */
        flex-direction: column;
    }
    .agent-chat-header { padding: 12px; font-weight: bold; background: #f7f7fa; border-bottom: 1px solid #eee; border-radius: 12px 12px 0 0; flex-shrink: 0; }
    #agent-status { float: right; font-size: 0.9em; color: #888; }
    .agent-chat-log {
        /* max-height: 180px; /* Removed fixed max-height */
        flex-grow: 1; /* Allow log to take available space */
        overflow-y: auto;
        padding: 10px;
        background: #fafbfc;
    }
    .agent-message { margin-bottom: 7px; padding: 7px 10px; border-radius: 8px; font-size: 0.98em; max-width: 90%; word-wrap: break-word; line-height: 1.4; clear: both; }
    .agent-message.user { background: #e6f0fa; text-align: left; float: right; border-bottom-right-radius: 2px; margin-left: auto; } /* Adjusted for float */
    .agent-message.ai { background: #f1f1f1; text-align: left; float: left; border-bottom-left-radius: 2px; margin-right: auto; } /* Adjusted for float */
    /* Styling for markdown elements inside AI messages */
    .agent-message.ai p { margin: 0.5em 0; }
    .agent-message.ai ul, .agent-message.ai ol { margin: 0.5em 0 0.5em 1.2em; padding-left: 0.5em; }
    .agent-message.ai li { margin-bottom: 0.2em; }
    .agent-message.ai strong { font-weight: bold; }
    .agent-message.ai em { font-style: italic; }
    .agent-message.ai a { color: #007bff; text-decoration: underline; } /* Style links */
    .agent-message.ai a:hover { color: #0056b3; }
    .agent-message.ai code { background-color: #eee; padding: 0.1em 0.3em; border-radius: 3px; font-family: monospace; font-size: 0.95em; }
    .agent-message.ai pre { background-color: #eee; padding: 0.5em; border-radius: 4px; overflow-x: auto; font-family: monospace; font-size: 0.9em; }
    .agent-message.ai pre code { background-color: transparent; padding: 0; border-radius: 0; }
    .agent-message.ai blockquote { border-left: 3px solid #ccc; padding-left: 0.8em; margin-left: 0.2em; color: #555; }
    .agent-chat-controls.agent-chat-controls-col { display: flex; flex-direction: column; gap: 7px; padding: 10px; border-top: 1px solid #eee; flex-shrink: 0; }
    .agent-chat-row { display: flex; gap: 6px; align-items: center; /* Align items vertically */ }
    .agent-chat-input-row { margin-top: 2px; }
    #agent-type-select { flex: 1 1 auto; font-size: 0.95em; padding: 5px; border-radius: 4px; border: 1px solid #ccc; background-color: #fff; height: 34px; /* Match button height approx */ }
    #agent-chat-input { flex: 1 1 100%; font-size: 1em; border-radius: 5px; border: 1px solid #ccc; padding: 7px 10px; min-width: 0; height: 34px; box-sizing: border-box; }
    #agent-chat-send { flex: 0 0 auto; padding: 7px 12px; background: #007bff; color: #fff; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; margin-left: 7px; font-size: 0.95em; height: 34px; }
    #agent-chat-send:hover { background: #0056b3; }
    .agent-chat-settings { padding: 8px; border-top: 1px solid #eee; text-align: right; flex-shrink: 0; font-size: 0.9em; background: #f7f7fa; border-radius: 0 0 12px 12px; }
    .agent-chat-settings label { color: #555; cursor: pointer; }
    .agent-chat-settings input[type="checkbox"] { margin-right: 4px; vertical-align: middle; cursor: pointer; }
    `;
    document.head.appendChild(style);
} else {
    console.log("Agent chat styles already added.");
}