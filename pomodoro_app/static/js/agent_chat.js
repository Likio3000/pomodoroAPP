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
        <audio id="agent-chat-audio" style="display:none;"></audio>
    `;
    document.body.appendChild(chatBox);
}

// --- Chat Logic ---
function appendAgentMessage(text, sender = 'ai') {
    const log = document.getElementById('agent-chat-log');
    const msg = document.createElement('div');
    msg.className = 'agent-message ' + sender;
    if (sender === 'ai') {
    // Render Markdown for AI responses
    if (window.marked) {
        msg.innerHTML = `<strong>AI:</strong> ` + marked.parse(text);
    } else {
        msg.innerHTML = `<strong>AI:</strong> ${text}`;
    }
} else {
    msg.innerHTML = `<strong>You:</strong> ${text}`;
}
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
}

function setAgentStatus(status) {
    document.getElementById('agent-status').textContent = status;
}

async function sendAgentMessage() {
    const input = document.getElementById('agent-chat-input');
    const agentType = document.getElementById('agent-type-select').value;
    const message = input.value.trim();
    if (!message) return;
    appendAgentMessage(message, 'user');
    input.value = '';
    setAgentStatus('...');

    // Optionally, collect dashboard data from your app (dummy for now)
    const dashboardData = window.getDashboardData ? window.getDashboardData() : {};

    try {
        const response = await fetch('/api/chat', {
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
            appendAgentMessage(data.response, 'ai');
            if (data.audio_url) {
                playAgentAudio(data.audio_url);
            }
        } else {
            appendAgentMessage('Sorry, the assistant is unavailable.', 'ai');
        }
    } catch (err) {
        appendAgentMessage('Error contacting AI service.', 'ai');
    }
    setAgentStatus('');
}

function playAgentAudio(audioUrl) {
    const audio = document.getElementById('agent-chat-audio');
    audio.src = audioUrl;
    audio.style.display = 'block';
    audio.onplay = () => console.log('Agent audio playing:', audioUrl);
    audio.onerror = (e) => {
        console.error('Error playing agent audio:', e);
        alert('Could not play agent audio. See console for details.');
    };
    audio.play().catch(err => {
        console.error('Play() failed:', err);
        alert('Audio playback failed (possibly browser auto-play restriction). Click anywhere and try again.');
    });
}

function setupAgentChatEvents() {
    document.getElementById('agent-chat-send').onclick = sendAgentMessage;
    document.getElementById('agent-chat-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') sendAgentMessage();
    });
}

// --- Timer Event Hooks ---
// Call this from your timer logic to trigger agent messages
window.triggerAgentEvent = function(eventType) {
    const agentType = document.getElementById('agent-type-select').value;
    let prompt = '';
    if (eventType === 'timer_start') prompt = "I'm starting a new Pomodoro session! Any tips?";
    else if (eventType === 'timer_complete') prompt = "I just finished a Pomodoro!";
    else if (eventType === 'break_start') prompt = "It's break time. How should I recharge?";
    else if (eventType === 'break_end') prompt = "Break's over. Any advice for getting back to work?";
    if (prompt) {
        document.getElementById('agent-chat-input').value = prompt;
        sendAgentMessage();
    }
};

// --- Initialize on page load ---
document.addEventListener('DOMContentLoaded', function() {
    createAgentChatBox();
    setupAgentChatEvents();
});

// --- Minimal styles (could move to CSS file) ---
const style = document.createElement('style');
style.textContent = `
#agent-chatbox {
    position: fixed; bottom: 24px; right: 24px; width: 340px; z-index: 9999;
    background: #fff; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    font-family: inherit; border: 1px solid #e0e0e0;
}
.agent-chat-header { padding: 12px; font-weight: bold; background: #f7f7fa; border-bottom: 1px solid #eee; border-radius: 12px 12px 0 0; }
#agent-status { float: right; font-size: 0.9em; color: #888; }
.agent-chat-log { max-height: 180px; overflow-y: auto; padding: 10px; background: #fafbfc; }
.agent-message { margin-bottom: 7px; padding: 7px 10px; border-radius: 8px; font-size: 0.98em; }
.agent-message.user { background: #e6f0fa; text-align: right; }
.agent-message.ai { background: #f1f1f1; text-align: left; }
.agent-chat-controls.agent-chat-controls-col { display: flex; flex-direction: column; gap: 7px; padding: 10px; border-top: 1px solid #eee; }
.agent-chat-row { display: flex; gap: 6px; }
.agent-chat-input-row { margin-top: 2px; }
#agent-type-select { flex: 1 1 100%; font-size: 1em; }
#agent-chat-input { flex: 1 1 100%; font-size: 1em; border-radius: 5px; border: 1px solid #ccc; padding: 7px 10px; min-width: 0; }
#agent-chat-send { flex: 0 0 22%; background: #007bff; color: #fff; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; margin-left: 7px; }
#agent-chat-send:hover { background: #0056b3; }
`;
document.head.appendChild(style);
