// pomodoro_app/static/js/agent_chat.js
// Handles chat UI, agent selection, audio playback, and chat history persistence
// for the Pomodoro AI assistant using sessionStorage.

// --- CSRF Token ---
let chatCsrfToken = null;
const chatCsrfMetaTag = document.querySelector('meta[name=csrf-token]');
if (chatCsrfMetaTag) {
    chatCsrfToken = chatCsrfMetaTag.content;
    console.log("Agent Chat: CSRF token found.");
} else {
    console.error("Agent Chat: CSRF meta tag not found! Chat API calls will fail.");
}

// --- AGENT DEFINITIONS ---
const AGENTS = {
    "default": { name: "Assistant", voice: "alloy" },
    "motivator": { name: "Motivator", voice: "nova" },
    "coach": { name: "Coach", voice: "shimmer" }
};

// --- STORAGE KEYS ---
const CHAT_HISTORY_KEY = 'pomodoroAgentChatHistory_v1'; // Versioned chat history key
const AGENT_SELECTION_KEY = 'pomodoroAgentSelected_v1'; // Versioned key for selected agent
const CHAT_COLLAPSE_KEY = 'agentChatCollapsed_v1'; // Persistent collapsed state

let chatHistory = []; // In-memory representation of the history

// --- UI Construction ---
function createAgentChatBox() {
    if (document.getElementById('agent-chatbox')) return;

    const chatBox = document.createElement('div');
    chatBox.id = 'agent-chatbox';
    // Simplified HTML - no inline notice needed here anymore
    chatBox.innerHTML = `
        <div id="agent-chat-header" class="agent-chat-header" tabindex="0" role="button" aria-expanded="true">
            AI Assistant <span id="agent-status" aria-live="polite"></span>
            <span aria-hidden="true" id="agent-chat-toggle">–</span>
        </div>
        <div id="agent-chat-body">
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
        </div>
        <audio id="agent-chat-audio" style="display:none;"></audio>
    `;

    document.body.appendChild(chatBox);

    const collapsed = localStorage.getItem(CHAT_COLLAPSE_KEY) === '1';
    setCollapsed(collapsed);

    const header = document.getElementById('agent-chat-header');
    if (header) {
        header.addEventListener('click', toggleCollapsed);
        header.addEventListener('keydown', e => { if(e.key==='Enter'||e.key===' '){ e.preventDefault(); toggleCollapsed(); }});
    }

    console.log("Agent chatbox created (UI always enabled).");
}

function setCollapsed(collapsed) {
    const box = document.getElementById('agent-chatbox');
    const toggle = document.getElementById('agent-chat-toggle');
    if (!box) return;
    if (collapsed) {
        box.classList.add('agent-chat-collapsed');
        if (toggle) toggle.textContent = '+';
        box.setAttribute('aria-expanded', 'false');
        localStorage.setItem(CHAT_COLLAPSE_KEY, '1');
    } else {
        box.classList.remove('agent-chat-collapsed');
        if (toggle) toggle.textContent = '–';
        box.setAttribute('aria-expanded', 'true');
        localStorage.setItem(CHAT_COLLAPSE_KEY, '0');
    }
}

function toggleCollapsed() {
    const box = document.getElementById('agent-chatbox');
    setCollapsed(!box.classList.contains('agent-chat-collapsed'));
}

// --- Chat Logic & History Management ---
function renderMessageWithoutSaving(text, sender = 'ai') {
    const log = document.getElementById('agent-chat-log');
    if (!log) return;
    const msg = document.createElement('div');
    msg.className = 'agent-message ' + sender;
    const prefix = sender === 'ai' ? '<strong>AI:</strong> ' : '<strong>You:</strong> ';
    msg.innerHTML = prefix;

    if (sender === 'ai') {
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            try {
                const rawHtml = marked.parse(text, { breaks: true });
                const cleanHtml = DOMPurify.sanitize(rawHtml);
                msg.innerHTML += cleanHtml;
            } catch (e) {
                msg.appendChild(document.createTextNode(text));
            }
        } else {
            msg.appendChild(document.createTextNode(text));
        }
    } else {
        msg.appendChild(document.createTextNode(text));
    }
    log.appendChild(msg);
    if (log.scrollHeight - log.scrollTop <= log.clientHeight + 50) {
         log.scrollTop = log.scrollHeight;
    }
}

function appendAgentMessage(text, sender = 'ai') {
    renderMessageWithoutSaving(text, sender);
    chatHistory.push({ sender, text });
    try {
        const maxHistoryLength = 50;
        if (chatHistory.length > maxHistoryLength) {
             chatHistory = chatHistory.slice(-maxHistoryLength);
        }
        sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
    } catch (e) {
        console.error("Error saving chat history:", e);
    }
}

function setAgentStatus(status) {
    const statusEl = document.getElementById('agent-status');
    if (statusEl) statusEl.textContent = status ? `(${status})` : '';
}


async function sendAgentMessage() {
    // Still check for CSRF token
    if (!chatCsrfToken) {
        console.error("Agent Chat: Cannot send message, CSRF token missing.");
        appendAgentMessage("Error: Missing security token. Please refresh the page.", 'ai');
        setAgentStatus('Error');
        return;
    }

    const input = document.getElementById('agent-chat-input');
    const agentTypeSelect = document.getElementById('agent-type-select');
    const ttsToggle = document.getElementById('tts-toggle');
    const sendBtn = document.getElementById('agent-chat-send');
    if (!input || !agentTypeSelect || !ttsToggle || !sendBtn) return;

    const agentType = agentTypeSelect.value;
    const message = input.value.trim();
    const isTtsEnabledByUser = ttsToggle.checked;
    if (!message) return;

    appendAgentMessage(message, 'user');
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;
    setAgentStatus('...');

    const dashboardData = window.dashboardConfig?.initialData || {};

    try {
        const headers = {
            'Content-Type':'application/json',
            'Accept': 'application/json',
            'X-CSRFToken': chatCsrfToken
        };

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: headers,
            credentials: 'same-origin',
            body: JSON.stringify({
                prompt: message,
                dashboard_data: dashboardData,
                agent_type: agentType,
                tts_enabled: isTtsEnabledByUser,
                message_count: chatHistory.length
            })
        });
        const data = await response.json();

        // Enhanced Error Handling for API Failures
        if (!response.ok) {
            let errorMsg = data.error || `Error ${response.status}`;
            if (response.status === 501 || response.status === 503) {
                errorMsg = data.error || "Chat feature is currently unavailable.";
            } else if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                errorMsg = data.error + " Please refresh the page.";
            }
            throw new Error(errorMsg);
        }

        if (data.response) {
            appendAgentMessage(data.response, 'ai');
            if (data.audio_url) playAgentAudio(data.audio_url);
        } else if (data.error) {
            appendAgentMessage(`Sorry, ${data.error}`, 'ai');
        } else {
            appendAgentMessage('Unexpected empty response.', 'ai');
        }
    } catch (err) {
        console.error("Agent Chat Send Error:", err);
        appendAgentMessage(`Error: ${err.message}`, 'ai');
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        setAgentStatus('');
        input.focus();
    }
}

// --- playAgentAudio ---
function playAgentAudio(audioUrl) {
    const ttsToggle = document.getElementById('tts-toggle');
    // Only play if TTS toggle is checked
    if (!ttsToggle || !ttsToggle.checked) return;

    const audio = document.getElementById('agent-chat-audio');
    if (!audio) return;
    if (!audio.paused) { audio.pause(); audio.currentTime = 0; }
    audio.src = audioUrl;
    const playPromise = audio.play();
    if (playPromise) {
        playPromise.catch(error => {
            console.warn('Audio playback error:', error);
            setAgentStatus(error.name === 'NotAllowedError' ? 'Audio blocked' : 'Audio error');
        });
    }
    audio.onerror = () => setAgentStatus('Audio error');
}

// --- setupAgentChatEvents ---
function setupAgentChatEvents() {
    const sendBtn = document.getElementById('agent-chat-send');
    const inputField = document.getElementById('agent-chat-input');
    const agentTypeSelect = document.getElementById('agent-type-select');

    if (sendBtn) sendBtn.onclick = sendAgentMessage;
    if (inputField) inputField.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMessage(); }
    });

    if (agentTypeSelect) {
        agentTypeSelect.addEventListener('change', () => {
            sessionStorage.setItem(AGENT_SELECTION_KEY, agentTypeSelect.value);
        });
    }
}

// --- Timer Event Hooks ---
window.triggerAgentEvent = function(eventType) {
    const agentInput = document.getElementById('agent-chat-input');
    if (!agentInput) return;
    const prompts = {
        'timer_start': "I'm starting a new Pomodoro session! Any tips?",
        'timer_complete': "I just finished a Pomodoro work session!",
        'break_start': "It's break time. How should I recharge effectively?",
        'break_end': "Break's over. Any advice for getting back into focus?"
    };
    agentInput.value = prompts[eventType] || '';
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    createAgentChatBox(); // Create the UI regardless of server config

    // Load chat history
    try {
        const stored = sessionStorage.getItem(CHAT_HISTORY_KEY);
        if (stored) {
            chatHistory = JSON.parse(stored);
            chatHistory.forEach(msg => renderMessageWithoutSaving(msg.text, msg.sender));
            // Scroll to bottom after rendering history
            const log = document.getElementById('agent-chat-log');
            if(log) log.scrollTop = log.scrollHeight;
        } else {
            appendAgentMessage("Hello! Ask me about your Pomodoro stats or for productivity tips.", 'ai');
        }
    } catch (e) {
        console.error('Error loading chat history:', e);
        sessionStorage.removeItem(CHAT_HISTORY_KEY);
        chatHistory = [];
        appendAgentMessage("Error loading previous chat messages.", 'ai'); // Inform user
    }

    // Restore agent selection
    const agentTypeSelect = document.getElementById('agent-type-select');
    const savedAgent = sessionStorage.getItem(AGENT_SELECTION_KEY);
    if (agentTypeSelect && savedAgent && AGENTS[savedAgent]) {
        agentTypeSelect.value = savedAgent;
    }

    setupAgentChatEvents();

    // --- MODIFIED: Set initial TTS toggle state ---
    const ttsToggle = document.getElementById('tts-toggle');
    if (ttsToggle) {
        // Always default the checkbox to unchecked on page load.
        ttsToggle.checked = false;
        console.log("Agent Chat: TTS toggle default set to OFF (unchecked). User must opt-in.");
    }
    // --- END MODIFICATION ---

    // Check CSRF token presence during init (still important)
    if (!chatCsrfToken) {
        console.error("Agent Chat Init Error: CSRF token missing!");
        appendAgentMessage("CRITICAL ERROR: Security token missing. Chat will not work. Please refresh.", 'ai');
        // Disable input/send if token is missing
        const inputField = document.getElementById('agent-chat-input');
        const sendBtn = document.getElementById('agent-chat-send');
        if(inputField) inputField.disabled = true;
        if(sendBtn) sendBtn.disabled = true;
    }

    console.log("Agent chat initialization complete (UI always enabled).");
});


// --- Minimal styles ---
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
    #agent-chatbox.agent-chat-collapsed {
        width: auto;
        min-width: 120px;
    }
    #agent-chatbox.agent-chat-collapsed #agent-chat-body {
        display: none;
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
    try {
        document.head.appendChild(style);
    } catch (e) {
        console.error("Could not append chat styles to document head:", e);
        try { document.getElementsByTagName('head')[0].appendChild(style); } catch (e2) {}
    }
}