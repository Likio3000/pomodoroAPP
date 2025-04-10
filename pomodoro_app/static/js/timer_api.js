// pomodoro_app/static/js/timer_api.js
// Handles communication with the backend timer API endpoints.

// Expose functions via a global object
window.PomodoroAPI = (function() {
    'use strict';

    // --- API URLs (passed in via init) ---
    let apiUrls = {
        start: '/api/timer/start',
        complete: '/api/timer/complete_phase'
    };

    // --- DOM Elements (passed in via init) ---
    let elements = {
        statusMessage: null,
        startBtn: null,
        pauseBtn: null,
        resetBtn: null // Add resetBtn here
    };

    // --- Helper to disable/enable buttons during calls ---
    function setControlsDisabled(disabled) {
        if (elements.startBtn) elements.startBtn.disabled = disabled;
        if (elements.pauseBtn) elements.pauseBtn.disabled = disabled;
        if (elements.resetBtn) elements.resetBtn.disabled = disabled; // Include resetBtn
    }

    // --- API Communication ---

    async function sendStartSignal(workDuration, breakDuration) {
         console.log("Sending start signal to server...");
         if(elements.statusMessage) elements.statusMessage.textContent = 'Starting...';
         setControlsDisabled(true); // Disable Start, Pause, Reset

         try {
            const response = await fetch(apiUrls.start, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 body: JSON.stringify({ work: workDuration, break: breakDuration })
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `Server error ${response.status}`);
            }

            console.log("Server acknowledged timer start.", data);
            // --- Update state using PomodoroLogic setters ---
            window.PomodoroLogic.setTotalPoints(data.total_points);
            window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
            window.PomodoroLogic.setServerEndTimeUTC(data.end_time);

            const now = new Date();
            const remaining = Math.max(0, Math.floor((new Date(data.end_time) - now) / 1000));
            window.PomodoroLogic.setRemainingSeconds(remaining);
            window.PomodoroLogic.setPhase('work');
            window.PomodoroLogic.setPrePausePhase(null);
            // --- End state update ---

            window.PomodoroLogic.startCountdown(); // Start client timer via Logic module
            // Buttons will be re-enabled correctly by updateButtonStates called via startCountdown

         } catch (error) {
             console.error("Error sending start signal:", error);
             if(elements.statusMessage) elements.statusMessage.textContent = `Error: ${error.message || 'Could not start timer.'}`;
             setControlsDisabled(false); // Re-enable controls on error
         }
         // No finally block needed for re-enabling on success path
    }

    async function sendCompleteSignal(completedPhase) {
         console.log(`Sending complete signal for phase: ${completedPhase}`);
         setControlsDisabled(true); // Disable Start, Pause, Reset

         try {
             const response = await fetch(apiUrls.complete, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 body: JSON.stringify({ phase_completed: completedPhase })
             });
             const data = await response.json();

              if (!response.ok) {
                    throw new Error(data.error || `Server error ${response.status}`);
             }

             console.log(`Server acknowledged ${completedPhase} completion.`, data);

             // --- Update state using PomodoroLogic setters ---
             window.PomodoroLogic.setTotalPoints(data.total_points);
             window.PomodoroLogic.setServerEndTimeUTC(null); // Clear end time
             // --- End state update ---

             // Handle next phase based on server status
             if (data.status === 'break_started') {
                 window.PomodoroLogic.setPhase('break');
                 window.PomodoroLogic.setPrePausePhase(null);
                 window.PomodoroLogic.setCurrentMultiplier(1.0); // Break multiplier

                 const breakDuration = window.PomodoroLogic.getBreakDuration(); // Get from logic
                 const now = new Date();
                 const breakEndTimeUTC = new Date(now.getTime() + breakDuration * 60000).toISOString();

                 window.PomodoroLogic.setServerEndTimeUTC(breakEndTimeUTC);
                 window.PomodoroLogic.setRemainingSeconds(breakDuration * 60);

                 if(elements.statusMessage) elements.statusMessage.textContent = "Work complete! Starting break.";
                 window.PomodoroLogic.updateUIDisplays();
                 setTimeout(window.PomodoroLogic.startCountdown, 500); // Start break via Logic
                 // Buttons re-enabled by updateButtonStates in startCountdown

             } else if (data.status === 'session_complete' || data.status === 'acknowledged_no_state') {
                 // Resetting the timer will handle button states
                 if (data.status === 'acknowledged_no_state') {
                    console.warn("Server had no state for completion signal. Resetting client.");
                    if(elements.statusMessage) elements.statusMessage.textContent = "Session desync? Resetting timer.";
                 } else {
                    if(elements.statusMessage) elements.statusMessage.textContent = "Break complete! Session finished.";
                 }
                 const initialConfig = window.pomodoroConfig || { initialData: {} }; // Get from global
                 setTimeout(() => window.PomodoroLogic.resetTimer(initialConfig.initialData), 500); // Reset via Logic

             } else {
                 throw new Error(`Unexpected status from complete API: ${data.status}`);
             }

         } catch (error) {
              console.error(`Error sending complete signal (${completedPhase}):`, error);
              if(elements.statusMessage) elements.statusMessage.textContent = `Error: ${error.message || 'Could not complete phase.'}`;
              // Attempt to pause locally on error
              window.PomodoroLogic.pauseCountdown(); // Pause via Logic
              // Buttons re-enabled by updateButtonStates in pauseCountdown
              // setControlsDisabled(false); // No longer needed here
         }
        // No finally block needed for re-enabling
    }


    // --- Public Methods ---
    return {
        init: function(domElements, configUrls) {
            console.log("Initializing Pomodoro API...");
            elements = domElements; // Store relevant DOM elements
            apiUrls = configUrls;   // Store API URLs
            console.log("Pomodoro API Initialized with URLs:", apiUrls);
        },
        sendStartSignal: sendStartSignal,
        sendCompleteSignal: sendCompleteSignal
    };

})(); // End of IIFE