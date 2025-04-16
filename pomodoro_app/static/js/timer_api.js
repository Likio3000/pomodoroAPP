// pomodoro_app/static/js/timer_api.js
// Handles communication with the backend timer API endpoints.

// Expose functions via a global object
window.PomodoroAPI = (function() {
    'use strict';

    // --- API URLs (initialized via init) ---
    let apiUrls = {
        start: '/api/timer/start',
        complete: '/api/timer/complete_phase',
        getState: '/api/timer/state',
        reset: '/api/timer/reset',
        resume: '/api/timer/resume' // Added resume URL holder
    };

    // --- DOM Elements (passed in via init) ---
    let elements = {
        statusMessage: null,
        startBtn: null,
        pauseBtn: null,
        resetBtn: null
    };

    // --- Helper to disable/enable buttons during API calls ---
    function setControlsDisabled(disabled, operation = '') {
        console.log(`API Controls: ${disabled ? 'Disabling' : 'Enabling'} for ${operation || 'operation'}`);
        if (elements.startBtn) elements.startBtn.disabled = disabled;
        if (elements.pauseBtn) elements.pauseBtn.disabled = disabled;
        if (elements.resetBtn) elements.resetBtn.disabled = disabled;

         if (disabled && elements.statusMessage && operation) {
            elements.statusMessage.textContent = `${operation}...`;
            elements.statusMessage.classList.remove('status-alert', 'status-success');
         }
    }

    // --- API Communication Functions ---

    async function sendStartSignal(workDuration, breakDuration) {
         setControlsDisabled(true, "Starting");

         try {
            const response = await fetch(apiUrls.start, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 credentials: 'same-origin',
                 body: JSON.stringify({ work: workDuration, break: breakDuration })
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }

            console.log("Server acknowledged timer start.", data);
            window.PomodoroLogic.setTotalPoints(data.total_points);
            window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
            window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
            window.PomodoroLogic.setPhase('work');
            window.PomodoroLogic.setPrePausePhase(null);
            window.PomodoroLogic.startCountdown(); // Now async, but we don't await its completion here

         } catch (error) {
             console.error("Error sending start signal:", error);
             if(elements.statusMessage) {
                elements.statusMessage.textContent = `Error: ${error.message || 'Could not start timer.'}`;
                elements.statusMessage.classList.add('status-alert');
             }
             setControlsDisabled(false);
             if (window.PomodoroLogic) {
                 window.PomodoroLogic.setPhase('idle');
                 window.PomodoroLogic.updateButtonStates(false);
                 window.PomodoroLogic.enableInputs(true);
             }
         }
    }

    async function sendCompleteSignal(completedPhase) {
         setControlsDisabled(true, `Completing ${completedPhase}`);

         try {
             const response = await fetch(apiUrls.complete, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 credentials: 'same-origin',
                 body: JSON.stringify({ phase_completed: completedPhase })
             });
             const data = await response.json();

             // Always update total points if received
             if (data && typeof data.total_points === 'number') {
                  window.PomodoroLogic.setTotalPoints(data.total_points);
             }

             if (!response.ok) {
                 // Throw error to be caught below, ensuring points are updated first if possible
                 throw new Error(data.error || response.statusText || `Server error ${response.status}`);
             }

             console.log(`Server acknowledged ${completedPhase} completion. Status: ${data.status}`, data);
             window.PomodoroLogic.setServerEndTimeUTC(null); // Clear old end time initially

             if (data.status === 'break_started') {
                 window.PomodoroLogic.setPhase('break');
                 window.PomodoroLogic.setPrePausePhase(null);
                 window.PomodoroLogic.setCurrentMultiplier(1.0); // Breaks have 1x multiplier
                 // Server sends the break end time
                 if (data.end_time) {
                    window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
                    // Calculate remaining seconds based on the received end time
                    const endTimeMs = new Date(data.end_time).getTime();
                    const nowMs = Date.now();
                    const remainingS = Math.max(0, Math.floor((endTimeMs - nowMs) / 1000));
                    window.PomodoroLogic.setRemainingSeconds(remainingS);
                 } else {
                    // Fallback if end_time is missing
                    console.warn("Break started response missing end_time, using local duration.");
                    const breakDuration = window.PomodoroLogic.getBreakDuration();
                    window.PomodoroLogic.setRemainingSeconds(breakDuration * 60);
                 }

                 if(elements.statusMessage) elements.statusMessage.textContent = "Work complete! Starting break.";
                 window.PomodoroLogic.updateUIDisplays();
                 // Use setTimeout to ensure UI update happens before countdown potentially changes display again
                 setTimeout(() => { window.PomodoroLogic.startCountdown(); }, 100);

             // --- START: Handle Automatic Work Start ---
             } else if (data.status === 'work_started') {
                 window.PomodoroLogic.setPhase('work');
                 window.PomodoroLogic.setPrePausePhase(null);

                 // Update multiplier and end time from server response
                 if (typeof data.active_multiplier === 'number') {
                      window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
                 }
                 if (data.end_time) {
                      window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
                      // Calculate remaining seconds based on the received end time
                      const endTimeMs = new Date(data.end_time).getTime();
                      const nowMs = Date.now();
                      const remainingS = Math.max(0, Math.floor((endTimeMs - nowMs) / 1000));
                      window.PomodoroLogic.setRemainingSeconds(remainingS);
                 } else {
                      // Fallback if end_time is missing
                      console.warn("Work started response missing end_time, using local duration.");
                      const workDuration = window.PomodoroLogic.getWorkDuration();
                      window.PomodoroLogic.setRemainingSeconds(workDuration * 60);
                 }

                 if(elements.statusMessage) elements.statusMessage.textContent = "Break complete! Starting next work session.";
                 window.PomodoroLogic.updateUIDisplays();
                 // Use setTimeout to ensure UI update happens before countdown potentially changes display again
                 setTimeout(() => { window.PomodoroLogic.startCountdown(); }, 100);
             // --- END: Handle Automatic Work Start ---

             } else if (data.status === 'session_complete' || data.status === 'acknowledged_no_state') {
                 // This case might become less common if breaks always lead to work_started
                 if (data.status === 'acknowledged_no_state') {
                    console.warn("Server had no state for completion signal. Resetting client.");
                    if(elements.statusMessage) elements.statusMessage.textContent = "Session desync? Timer reset.";
                 } else {
                    // This might happen if the flow is somehow interrupted?
                    console.warn("Received 'session_complete' status unexpectedly after break. Resetting.");
                    if(elements.statusMessage) elements.statusMessage.textContent = "Session ended. Ready for next session.";
                 }
                 // Reset timer immediately in these cases
                  window.PomodoroLogic.resetTimer(false);

             } else {
                 // Unexpected status from server
                 throw new Error(`Unexpected status from complete API: ${data.status}`);
             }

             // No need to call setControlsDisabled(false) here as startCountdown handles UI state

         } catch (error) {
              // Error handling remains the same
              console.error(`Error sending complete signal (${completedPhase}):`, error);
              if(elements.statusMessage) {
                elements.statusMessage.textContent = `Error: ${error.message || 'Could not complete phase.'}`;
                elements.statusMessage.classList.add('status-alert');
              }
              // Attempt to revert to a paused state to allow user intervention
              if (window.PomodoroLogic) {
                  // Don't reset phase if it was already updated by a successful part of the try block
                  if (window.PomodoroLogic.getPhase() !== 'work' && window.PomodoroLogic.getPhase() !== 'break') {
                     window.PomodoroLogic.setPhase('paused');
                     window.PomodoroLogic.setPrePausePhase(completedPhase); // Keep track of what failed
                  }
                  window.PomodoroLogic.updateUIDisplays();
                  window.PomodoroLogic.updateButtonStates(false); // Show Resume/Reset
                  window.PomodoroLogic.enableInputs(false);
              }
              setControlsDisabled(false); // Explicitly re-enable controls on error
         }
    }

    async function sendResetSignal() {
        console.log("Sending reset signal to server...");
        setControlsDisabled(true, "Resetting");

        try {
            const response = await fetch(apiUrls.reset, { method: 'POST', credentials: 'same-origin' });
            const data = await response.json();

            if (!response.ok) {
                 throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }
            console.log("Server acknowledged reset signal:", data.status);

        } catch (error) {
            console.error("Error sending reset signal:", error);
            if(elements.statusMessage) {
                const currentStatus = elements.statusMessage.textContent;
                if (!currentStatus.includes("(Server reset failed)")) {
                   elements.statusMessage.textContent = currentStatus + " (Server reset failed)";
                   elements.statusMessage.classList.add('status-alert');
                }
            }
        } finally {
             setControlsDisabled(false);
             if (window.PomodoroLogic) {
                window.PomodoroLogic.updateButtonStates(false);
                window.PomodoroLogic.enableInputs(true);
             }
        }
    }

    // +++ NEW: sendResumeSignal +++
    async function sendResumeSignal(pauseDurationMs) {
        // Sends the pause duration to the server to adjust the end time.
        // Returns true on success, false on failure.
        console.log(`Sending resume signal to server. Pause duration: ${pauseDurationMs}ms`);
        setControlsDisabled(true, "Resuming"); // Disable controls during API call

        try {
            const response = await fetch(apiUrls.resume, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                credentials: 'same-origin', // Send cookies
                body: JSON.stringify({ pause_duration_ms: pauseDurationMs })
            });
            const data = await response.json(); // Attempt to parse response

            if (!response.ok) {
                // Throw error using server message or default
                throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }

            console.log("Server acknowledged resume signal.", data);

            // Update client's target end time with the adjusted value from the server
            if (data.new_end_time && window.PomodoroLogic) {
                 console.log("Updating client serverEndTimeUTC from resume response:", data.new_end_time);
                 window.PomodoroLogic.setServerEndTimeUTC(data.new_end_time);
            } else {
                 console.warn("Resume API response did not include new_end_time. Client may need to rely on local calculation.");
            }
            return true; // Indicate API call success

        } catch (error) {
            console.error("Error sending resume signal:", error);
            if(elements.statusMessage) {
                elements.statusMessage.textContent = `Error resuming: ${error.message || 'Could not sync resume with server.'}`;
                elements.statusMessage.classList.add('status-alert');
            }
            // Do NOT re-enable controls here, as the calling function (startCountdown) needs
            // to know the API failed and should handle the UI state (keep it paused).
            return false; // Indicate API call failure
        }
        // Controls are re-enabled by the calling function (startCountdown) after this returns
    }


    // --- Public Methods ---
    return {
        init: function(domElements, configUrls) {
            console.log("Initializing Pomodoro API...");
            elements = domElements;
            // Merge default and passed URLs, ensuring all needed URLs are present
            apiUrls = { ...apiUrls, ...configUrls };
            if (!apiUrls.resume) console.error("Resume API URL missing in config!"); // Add check
            console.log("Pomodoro API Initialized with URLs:", apiUrls);
        },
        sendStartSignal: sendStartSignal,
        sendCompleteSignal: sendCompleteSignal,
        sendResetSignal: sendResetSignal,
        sendResumeSignal: sendResumeSignal // <-- Expose new function
    };

})(); // End of IIFE