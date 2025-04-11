// pomodoro_app/static/js/timer.js
// Main initialization script for the timer page.
// Orchestrates calls to PomodoroLogic and PomodoroAPI.

(function() {
    'use strict';

    // --- Get Config & Elements ---
    // Ensure config exists, provide defaults
    const config = window.pomodoroConfig || {
        apiUrls: { start: '/api/timer/start', complete: '/api/timer/complete_phase' },
        initialData: { totalPoints: 0, activeMultiplier: 1.0, activeState: null }
    };

    // Fetch all necessary DOM elements once
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

    // --- Initialization ---
    function init() {
        // Basic check for essential elements
        if (!elements.startBtn || !elements.pauseBtn || !elements.resetBtn || !elements.timerDisplay || !elements.statusMessage) {
            console.error("Required timer UI elements not found! Aborting initialization.");
            if(elements.statusMessage) elements.statusMessage.textContent = "UI Error: Missing elements.";
            if(elements.startBtn) elements.startBtn.disabled = true;
            return; // Stop if UI is broken
        }

        // Check if Logic and API modules are loaded
        if (typeof window.PomodoroLogic === 'undefined' || typeof window.PomodoroAPI === 'undefined') {
             console.error("Timer Logic or API modules not loaded! Aborting initialization.");
             if(elements.statusMessage) elements.statusMessage.textContent = "Error: Script dependencies missing.";
             elements.startBtn.disabled = true;
             return;
        }

        console.log("Initializing timer script (main)...");
        console.log("Using Config:", config);

        // Initialize the Logic and API modules, passing necessary elements/config
        const logicElements = { ...elements }; // Pass all elements to logic
        window.PomodoroLogic.init(logicElements, config);

        const apiElements = { // API module needs fewer elements
             statusMessage: elements.statusMessage,
             startBtn: elements.startBtn,
             pauseBtn: elements.pauseBtn,
             resetBtn: elements.resetBtn
        };
        window.PomodoroAPI.init(apiElements, config.apiUrls);

        // --- Event Listeners ---
        elements.startBtn.addEventListener('click', () => {
            const currentPhase = window.PomodoroLogic.getPhase();
            if (currentPhase === 'idle') {
                // Get values fresh from inputs when starting
                const workVal = parseInt(elements.workInput.value) || 25;
                const breakVal = parseInt(elements.breakInput.value) || 5;
                if (workVal <= 0 || breakVal <= 0) {
                     alert("Please enter positive values for work and break durations.");
                     return;
                }
                // Update logic module state before API call
                window.PomodoroLogic.setWorkDuration(workVal);
                window.PomodoroLogic.setBreakDuration(breakVal);
                // Call API function
                window.PomodoroAPI.sendStartSignal(workVal, breakVal);
            } else if (currentPhase === 'paused') {
                 // Resume locally via Logic module
                 window.PomodoroLogic.startCountdown();
            }
        });

        elements.pauseBtn.addEventListener('click', window.PomodoroLogic.pauseCountdown); // Call Logic module

        elements.resetBtn.addEventListener('click', () => {
             const currentPhase = window.PomodoroLogic.getPhase();
             if (currentPhase === 'paused') { // Only allow reset when paused
                 if (confirm("Are you sure you want to reset the timer? This will end the current session.")) {
                     // Reset via Logic module, passing initial config data for default values
                     window.PomodoroLogic.resetTimer(config.initialData);
                     // Optional: Send reset signal to server API if needed
                 }
             } else { console.log("Reset ignored (not paused)."); }
        });

        // Input listeners to update *potential* durations in Logic module *only if idle*
         elements.workInput.addEventListener('change', () => {
             if (window.PomodoroLogic.getPhase() === 'idle') {
                 const newDuration = parseInt(elements.workInput.value) || 25;
                 window.PomodoroLogic.setWorkDuration(newDuration);
                 console.log("Work duration updated (idle state):", newDuration);
             }
         });
         elements.breakInput.addEventListener('change', () => {
              if (window.PomodoroLogic.getPhase() === 'idle') {
                  const newDuration = parseInt(elements.breakInput.value) || 5;
                  window.PomodoroLogic.setBreakDuration(newDuration);
                  console.log("Break duration updated (idle state):", newDuration);
              }
         });

        console.log("Timer initialization complete (main).");
    }

    // Run initialization when the DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init(); // DOM already loaded
    }

})(); // End of IIFE