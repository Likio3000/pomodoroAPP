// pomodoro_app/static/js/timer.js
// Main initialization script for the timer page.
// Fetches initial state, initializes logic/API modules, and sets up UI event listeners.

(function() {
    'use strict';

    // --- Get Config & Elements ---
    // Load config passed from template (API URLs, initial points/multiplier)
    const config = window.pomodoroConfig || {
        apiUrls: { start: '/api/timer/start', complete: '/api/timer/complete_phase', getState: '/api/timer/state', reset: '/api/timer/reset', pause: '/api/timer/pause', resume: '/api/timer/resume' },
        initialData: { totalPoints: 0, activeMultiplier: 1.0 }
        // Note: activeState is NO LONGER expected here, fetched via API
    };

    // Fetch all necessary DOM elements once for performance
    const elements = {
        timerDisplay: document.getElementById('timer-display'),
        statusMessage: document.getElementById('status-message'),
        workInput: document.getElementById('work-minutes'),
        breakInput: document.getElementById('break-minutes'),
        startBtn: document.getElementById('start-btn'),
        pauseBtn: document.getElementById('pause-btn'),
        resetBtn: document.getElementById('reset-btn'),
        alarmSound: document.getElementById('alarm-sound'),
        totalPointsDisplay: document.getElementById('total-points-display'),
        activeMultiplierDisplay: document.getElementById('active-multiplier-display')
    };

    // --- Initialization Function ---
    async function init() {
        console.log("Initializing timer script (main)...");

        // Basic check for essential UI elements
        if (!elements.startBtn || !elements.pauseBtn || !elements.resetBtn || !elements.timerDisplay || !elements.statusMessage || !elements.workInput || !elements.breakInput) {
            console.error("Required timer UI elements not found! Aborting initialization.");
            if(elements.statusMessage) elements.statusMessage.textContent = "UI Error: Missing essential elements.";
            // Attempt to disable potentially existing buttons to prevent interaction
            if(elements.startBtn) elements.startBtn.disabled = true;
            if(elements.pauseBtn) elements.pauseBtn.disabled = true;
            if(elements.resetBtn) elements.resetBtn.disabled = true;
            return; // Stop script execution if UI is broken
        }

        // Initial UI state: Show loading message, disable controls until state is known
        elements.statusMessage.textContent = 'Checking server state...';
        elements.startBtn.disabled = true;
        elements.pauseBtn.disabled = true;
        elements.resetBtn.disabled = true;
        elements.workInput.disabled = true;
        elements.breakInput.disabled = true;


        // Check if Logic and API modules (dependencies) are loaded
        if (typeof window.PomodoroLogic === 'undefined' || typeof window.PomodoroAPI === 'undefined') {
             console.error("Timer Logic or API modules not loaded! Aborting initialization.");
             if(elements.statusMessage) elements.statusMessage.textContent = "Error: Required script dependencies missing.";
             // Keep controls disabled
             return;
        }

        // Initialize the API module first (it's needed for state fetch and actions)
        const apiElements = { // API module only needs elements it interacts with directly
             statusMessage: elements.statusMessage,
             startBtn: elements.startBtn,
             pauseBtn: elements.pauseBtn,
             resetBtn: elements.resetBtn
        };
        window.PomodoroAPI.init(apiElements, config.apiUrls);


        // --- Fetch Initial Server Timer State ---
        let serverState = null; // Will hold { active: boolean, phase?: ..., end_time?: ... }
        try {
            console.log("Fetching initial timer state from server via API...");
            const resp = await fetch(config.apiUrls.getState, {
                method: 'GET',
                credentials: 'same-origin' // Send cookies
            });

            if (!resp.ok) {
                // Try to parse error message from JSON response
                const errorData = await resp.json().catch(() => ({ error: `HTTP error ${resp.status}` }));
                throw new Error(errorData.error || `Failed to fetch state: ${resp.status}`);
            }

            const data = await resp.json();
            if (data.active) {
                serverState = data; // Store the full active state object
                console.log("Received ACTIVE server state:", serverState);
            } else {
                 console.log("Received INACTIVE server state.");
                 serverState = { active: false }; // Ensure serverState is not null
            }
        } catch (e) {
            console.error('Fatal Error: Failed to fetch initial timer state from server:', e);
            elements.statusMessage.textContent = `Error loading timer: ${e.message}. Please refresh.`;
            // Keep controls disabled as we don't know the correct state
            return; // Stop initialization if state fetch fails critically
        }
        // --- End fetch server state ---


        // Initialize the Logic module, passing DOM elements, fetched serverState, and initial config data (points/multiplier)
        const logicElements = { ...elements }; // Logic module might need all elements
        window.PomodoroLogic.init(logicElements, serverState, config.initialData);
        // Logic init will now call loadState which uses serverState as the primary source


        // --- Attach UI Event Listeners ---

        // Start / Resume Button
        elements.startBtn.addEventListener('click', () => {
            // Button should only be clickable when logic determines it's appropriate (idle or paused)
            const currentPhase = window.PomodoroLogic.getPhase();
            if (currentPhase === 'idle') {
                // --- Start New Timer ---
                const workVal = parseInt(elements.workInput.value) || 25;
                const breakVal = parseInt(elements.breakInput.value) || 5;
                if (workVal <= 0 || breakVal <= 0) {
                     alert("Please enter positive values (minutes) for work and break durations.");
                     return;
                }
                // Update logic module durations (might be redundant if inputs didn't change, but safe)
                window.PomodoroLogic.setWorkDuration(workVal);
                window.PomodoroLogic.setBreakDuration(breakVal);
                // Trigger API call to start the timer on the server
                window.PomodoroAPI.sendStartSignal(workVal, breakVal);
            } else if (currentPhase === 'paused') {
                 // --- Resume Paused Timer ---
                 // Resume happens locally via Logic module, adjusting end time
                 window.PomodoroLogic.startCountdown();
            }
        });

        // Pause Button
        elements.pauseBtn.addEventListener('click', async () => {
             // Button should only be clickable when logic determines timer is running
             await window.PomodoroLogic.pauseCountdown(); // Call Logic module to handle pause
        });

        // Reset Button
        elements.resetBtn.addEventListener('click', () => {
             // Button should only be clickable when logic determines timer is running or paused
             if (confirm("Are you sure you want to reset the timer? This will end the current session and discard progress for this interval.")) {
                 // Reset client state immediately via Logic module.
                 // resetTimer function in Logic module now ALSO triggers the API call to reset server state.
                 window.PomodoroLogic.resetTimer(false); // 'false' indicates this is not part of the initial page load
             }
        });

        // Duration Input Listeners (Work & Break)
        elements.workInput.addEventListener('change', () => {
             // Only allow changing duration if timer is idle
             if (window.PomodoroLogic.getPhase() === 'idle') {
                 const newDuration = parseInt(elements.workInput.value) || 25;
                 if (newDuration > 0) {
                     window.PomodoroLogic.setWorkDuration(newDuration);
                     console.log("Work duration updated (idle state):", newDuration);
                 } else {
                     // Reset to previous valid value if input is invalid
                     elements.workInput.value = window.PomodoroLogic.getWorkDuration();
                 }
             } else {
                 // If timer is running/paused, revert input to the actual current duration to prevent confusion
                 elements.workInput.value = window.PomodoroLogic.getWorkDuration();
             }
         });

         elements.breakInput.addEventListener('change', () => {
              // Only allow changing duration if timer is idle
              if (window.PomodoroLogic.getPhase() === 'idle') {
                  const newDuration = parseInt(elements.breakInput.value) || 5;
                   if (newDuration > 0) {
                      window.PomodoroLogic.setBreakDuration(newDuration);
                      console.log("Break duration updated (idle state):", newDuration);
                   } else {
                       elements.breakInput.value = window.PomodoroLogic.getBreakDuration();
                   }
              } else {
                   // Revert input if timer is active
                   elements.breakInput.value = window.PomodoroLogic.getBreakDuration();
              }
         });

        console.log("Timer initialization complete (main). Event listeners attached.");
    }

    // Run initialization when the DOM is fully loaded and parsed
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // DOMContentLoaded has already fired, run init immediately
        init();
    }

})(); // End of IIFE wrapper