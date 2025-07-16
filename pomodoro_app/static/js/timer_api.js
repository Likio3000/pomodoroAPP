// pomodoro_app/static/js/timer_api.js
// Handles communication with the backend timer API endpoints.

// Expose functions via a global object
window.PomodoroAPI = (function() {
    'use strict';

    // --- CSRF Token ---
    let csrfToken = null;
    const csrfMetaTag = document.querySelector('meta[name=csrf-token]');
    if (csrfMetaTag) {
        csrfToken = csrfMetaTag.content;
        console.log("CSRF token found in meta tag.");
    } else {
        console.error("CSRF meta tag not found! API calls requiring CSRF will fail.");
        // Optionally, disable buttons or show an error message immediately
    }

    // --- API URLs (initialized via init) ---
    let apiUrls = {
        start: '/api/timer/start',
        complete: '/api/timer/complete_phase',
        getState: '/api/timer/state',
        reset: '/api/timer/reset',
        pause: '/api/timer/pause',
        resume: '/api/timer/resume'
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
        // ... (keep existing helper function)
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

    // Helper to create headers object including CSRF token
    function createHeaders() {
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        } else {
             console.warn("CSRF token is missing, X-CSRFToken header not set.");
        }
        return headers;
    }


    async function sendStartSignal(workDuration, breakDuration) {
         setControlsDisabled(true, "Starting");
         if (!csrfToken) {
             console.error("Cannot send Start signal: CSRF token missing.");
             if(elements.statusMessage) { elements.statusMessage.textContent = "Error: Missing security token. Please refresh."; elements.statusMessage.classList.add('status-alert'); }
             setControlsDisabled(false);
             return; // Stop if token is missing
         }

         try {
            const response = await fetch(apiUrls.start, {
                 method: 'POST',
                 headers: createHeaders(), // <--- Use helper to include CSRF token
                 credentials: 'same-origin',
                 body: JSON.stringify({ work: workDuration, break: breakDuration })
            });
            const data = await response.json();

            if (!response.ok) {
                // Check for CSRF specific error (Flask-WTF typically returns 400)
                if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                    throw new Error(data.error + " Please refresh the page.");
                }
                throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }

            console.log("Server acknowledged timer start.", data);
            window.PomodoroLogic.setTotalPoints(data.total_points);
            window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
            window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
            window.PomodoroLogic.setPhase('work');
            window.PomodoroLogic.setPrePausePhase(null);
            window.PomodoroLogic.startCountdown();

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
         if (!csrfToken) {
             console.error("Cannot send Complete signal: CSRF token missing.");
             if(elements.statusMessage) { elements.statusMessage.textContent = "Error: Missing security token. Please refresh."; elements.statusMessage.classList.add('status-alert'); }
             setControlsDisabled(false);
             return;
         }

         try {
             const response = await fetch(apiUrls.complete, {
                 method: 'POST',
                 headers: createHeaders(), // <--- Use helper to include CSRF token
                 credentials: 'same-origin',
                 body: JSON.stringify({ phase_completed: completedPhase })
             });
             const data = await response.json();

             // Always update total points if received
             if (data && typeof data.total_points === 'number') {
                  window.PomodoroLogic.setTotalPoints(data.total_points);
             }

             if (!response.ok) {
                 if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                     throw new Error(data.error + " Please refresh the page.");
                 }
                 throw new Error(data.error || response.statusText || `Server error ${response.status}`);
             }

             // ... (rest of the success logic remains the same)
             console.log(`Server acknowledged ${completedPhase} completion. Status: ${data.status}`, data);
             window.PomodoroLogic.setServerEndTimeUTC(null); // Clear old end time initially

             if (data.status === 'break_started') {
                 // Enter BREAK phase. Breaks *inherit the multiplier from the preceding WORK*.
                 window.PomodoroLogic.setPhase('break');
                 window.PomodoroLogic.setPrePausePhase(null);
                 if (typeof data.active_multiplier === 'number') {
                     window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
                 } else {
                     // Fallback: keep whatever multiplier Logic currently has (from work completion)
                     console.warn('break_started response missing active_multiplier; preserving previous multiplier.');
                 }
                 if (data.end_time) {
                    window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
                    const endTimeMs = new Date(data.end_time).getTime();
                    const nowMs = Date.now();
                    const remainingS = Math.max(0, Math.floor((endTimeMs - nowMs) / 1000));
                    window.PomodoroLogic.setRemainingSeconds(remainingS);
                 } else {
                    console.warn("Break started response missing end_time, using local duration.");
                    const breakDuration = window.PomodoroLogic.getBreakDuration();
                    window.PomodoroLogic.setRemainingSeconds(breakDuration * 60);
                 }
                 if(elements.statusMessage) elements.statusMessage.textContent = "Work complete! Starting break.";
                 window.PomodoroLogic.updateUIDisplays();
                 setTimeout(() => { window.PomodoroLogic.startCountdown(); }, 100);

             } else if (data.status === 'work_started') {
                 window.PomodoroLogic.setPhase('work');
                 window.PomodoroLogic.setPrePausePhase(null);
                 if (typeof data.active_multiplier === 'number') {
                      window.PomodoroLogic.setCurrentMultiplier(data.active_multiplier);
                 }
                 if (data.end_time) {
                      window.PomodoroLogic.setServerEndTimeUTC(data.end_time);
                      const endTimeMs = new Date(data.end_time).getTime();
                      const nowMs = Date.now();
                      const remainingS = Math.max(0, Math.floor((endTimeMs - nowMs) / 1000));
                      window.PomodoroLogic.setRemainingSeconds(remainingS);
                 } else {
                      console.warn("Work started response missing end_time, using local duration.");
                      const workDuration = window.PomodoroLogic.getWorkDuration();
                      window.PomodoroLogic.setRemainingSeconds(workDuration * 60);
                 }
                 if(elements.statusMessage) elements.statusMessage.textContent = "Break complete! Starting next work session.";
                 window.PomodoroLogic.updateUIDisplays();
                 setTimeout(() => { window.PomodoroLogic.startCountdown(); }, 100);

             } else if (data.status === 'session_complete' || data.status === 'acknowledged_no_state') {
                 if (data.status === 'acknowledged_no_state') {
                    console.warn("Server had no state for completion signal. Resetting client.");
                    if(elements.statusMessage) elements.statusMessage.textContent = "Session desync? Timer reset.";
                 } else {
                    console.warn("Received 'session_complete' status unexpectedly after break. Resetting.");
                    if(elements.statusMessage) elements.statusMessage.textContent = "Session ended. Ready for next session.";
                 }
                  window.PomodoroLogic.resetTimer(false);

             } else {
                 throw new Error(`Unexpected status from complete API: ${data.status}`);
             }


         } catch (error) {
              // Error handling remains the same
              console.error(`Error sending complete signal (${completedPhase}):`, error);
              if(elements.statusMessage) {
                elements.statusMessage.textContent = `Error: ${error.message || 'Could not complete phase.'}`;
                elements.statusMessage.classList.add('status-alert');
              }
              if (window.PomodoroLogic) {
                  if (window.PomodoroLogic.getPhase() !== 'work' && window.PomodoroLogic.getPhase() !== 'break') {
                     window.PomodoroLogic.setPhase('paused');
                     window.PomodoroLogic.setPrePausePhase(completedPhase);
                  }
                  window.PomodoroLogic.updateUIDisplays();
                  window.PomodoroLogic.updateButtonStates(false);
                  window.PomodoroLogic.enableInputs(false);
              }
              setControlsDisabled(false);
         }
    }

    async function sendResetSignal() {
        console.log("Sending reset signal to server...");
        setControlsDisabled(true, "Resetting");
        if (!csrfToken) {
            console.error("Cannot send Reset signal: CSRF token missing.");
             if(elements.statusMessage) { elements.statusMessage.textContent = "Error: Missing security token. Please refresh."; elements.statusMessage.classList.add('status-alert'); }
            setControlsDisabled(false);
            return;
        }

        try {
            const response = await fetch(apiUrls.reset, {
                method: 'POST',
                headers: createHeaders(), // <--- Use helper to include CSRF token
                credentials: 'same-origin'
                // No body needed for reset
            });
            const data = await response.json();

            if (!response.ok) {
                 if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                     throw new Error(data.error + " Please refresh the page.");
                 }
                 throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }
            console.log("Server acknowledged reset signal:", data.status);

        } catch (error) {
            console.error("Error sending reset signal:", error);
            if(elements.statusMessage) {
                const currentStatus = elements.statusMessage.textContent;
                // Prevent appending error multiple times if reset is clicked again
                if (!currentStatus.includes("(Server reset failed)") && !currentStatus.includes("CSRF Error")) {
                   elements.statusMessage.textContent = currentStatus + ` (Server reset failed: ${error.message})`;
                   elements.statusMessage.classList.add('status-alert');
                } else if (!currentStatus.includes(error.message)){
                    // Update error message if it changed (e.g., from generic to CSRF)
                    elements.statusMessage.textContent = `Error: ${error.message}`;
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

    async function sendPauseSignal() {
        console.log('Sending pause signal to server...');
        setControlsDisabled(true, 'Pausing');
        if (!csrfToken) {
            console.error('Cannot send Pause signal: CSRF token missing.');
            if (elements.statusMessage) {
                elements.statusMessage.textContent = 'Error: Missing security token. Please refresh.';
                elements.statusMessage.classList.add('status-alert');
            }
            setControlsDisabled(false);
            return false;
        }

        try {
            const response = await fetch(apiUrls.pause, {
                method: 'POST',
                headers: createHeaders(),
                credentials: 'same-origin'
            });
            const data = await response.json();

            if (!response.ok) {
                if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                    throw new Error(data.error + ' Please refresh the page.');
                }
                throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }

            console.log('Server acknowledged pause signal.', data);
            return true;
        } catch (error) {
            console.error('Error sending pause signal:', error);
            if (elements.statusMessage) {
                elements.statusMessage.textContent = `Error pausing: ${error.message || 'Could not sync pause with server.'}`;
                elements.statusMessage.classList.add('status-alert');
            }
            return false;
        } finally {
            setControlsDisabled(false);
        }
    }

    async function sendResumeSignal(pauseDurationMs) {
        console.log(`Sending resume signal to server. Pause duration: ${pauseDurationMs}ms`);
        setControlsDisabled(true, "Resuming");
        if (!csrfToken) {
            console.error("Cannot send Resume signal: CSRF token missing.");
            if(elements.statusMessage) { elements.statusMessage.textContent = "Error: Missing security token. Please refresh."; elements.statusMessage.classList.add('status-alert'); }
            // Don't re-enable controls here, let calling function handle UI
            return false; // Indicate failure
        }

        try {
            const response = await fetch(apiUrls.resume, {
                method: 'POST',
                headers: createHeaders(), // <--- Use helper to include CSRF token
                credentials: 'same-origin',
                body: JSON.stringify({ pause_duration_ms: pauseDurationMs })
            });
            const data = await response.json();

            if (!response.ok) {
                if (response.status === 400 && data.error && data.error.toLowerCase().includes('csrf')) {
                    throw new Error(data.error + " Please refresh the page.");
                }
                throw new Error(data.error || response.statusText || `Server error ${response.status}`);
            }

            console.log("Server acknowledged resume signal.", data);

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
            return false; // Indicate API call failure
        }
    }


    // --- Public Methods ---
    return {
        init: function(domElements, configUrls) {
            console.log("Initializing Pomodoro API...");
            elements = domElements;
            apiUrls = { ...apiUrls, ...configUrls };
            if (!apiUrls.resume) console.error("Resume API URL missing in config!");
            // Check CSRF token presence again during init, more visible
            if (!csrfToken) {
                 console.error("Pomodoro API Init Error: CSRF token meta tag not found!");
                 if (elements.statusMessage) elements.statusMessage.textContent = "CRITICAL ERROR: Security token missing. Refresh page.";
                 // Optionally disable all buttons here
                 setControlsDisabled(true, "Initialization Failed (CSRF)");
            }
            console.log("Pomodoro API Initialized with URLs:", apiUrls);
        },
        sendStartSignal: sendStartSignal,
        sendCompleteSignal: sendCompleteSignal,
        sendResetSignal: sendResetSignal,
        sendPauseSignal: sendPauseSignal,
        sendResumeSignal: sendResumeSignal
    };

})(); // End of IIFE