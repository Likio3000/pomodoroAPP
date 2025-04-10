// pomodoro_app/static/js/timer.js
(function() {
    // --- Get Config & Elements ---
    // Use default empty objects to prevent errors if config is missing
    const config = window.pomodoroConfig || { apiUrls: {}, initialData: {} };
    const API_START_URL = config.apiUrls?.start || '/api/timer/start';
    const API_COMPLETE_URL = config.apiUrls?.complete || '/api/timer/complete_phase';

    const timerDisplay = document.getElementById('timer-display');
    const statusMessage = document.getElementById('status-message');
    const workInput = document.getElementById('work-minutes');
    const breakInput = document.getElementById('break-minutes');
    const startBtn = document.getElementById('start-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const resetBtn = document.getElementById('reset-btn');
    const alarmSound = document.getElementById('alarm-sound');

    // +++ New Elements +++
    const totalPointsDisplay = document.getElementById('total-points-display');
    const activeMultiplierDisplay = document.getElementById('active-multiplier-display');

    // --- State variables ---
    let intervalId = null;
    let remainingSeconds = 0;
    let phase = 'idle'; // 'idle', 'work', 'break', 'paused'
    let prePausePhase = null;
    let serverEndTimeUTC = null; // Store expected end time from server

    // Initialize durations and points/multiplier from server-passed data
    let workDurationMinutes = config.initialData?.activeState?.workMins || parseInt(workInput.value) || 25;
    let breakDurationMinutes = config.initialData?.activeState?.breakMins || parseInt(breakInput.value) || 5;
    let currentMultiplier = config.initialData?.activeMultiplier || 1.0;
    let totalPoints = config.initialData?.totalPoints || 0;

    // localStorage Keys
    const LS_KEY = 'pomodoroState_v2'; // Use a new key for the updated structure

    // --- Core Timer Logic ---

    function formatTime(seconds) {
        const safeSeconds = Math.max(0, Math.floor(seconds));
        const m = Math.floor(safeSeconds / 60);
        const s = safeSeconds % 60;
        return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    function updateUIDisplays() {
        let displayPhase = phase;
        if (phase === 'paused' && prePausePhase) {
            displayPhase = prePausePhase;
        }

        let phaseLabel = '';
        let multiplierContext = '';
        switch(displayPhase) {
            case 'work':
                phaseLabel = 'Work';
                multiplierContext = ''; // Base context is just the multiplier value
                break;
            case 'break':
                phaseLabel = 'Break';
                multiplierContext = '(Break Rate)'; // Explicitly label break rate
                currentMultiplier = 1.0; // Ensure multiplier display is 1.0 during break
                break;
            case 'paused':
                phaseLabel = prePausePhase === 'break' ? 'Break Paused' : 'Work Paused';
                multiplierContext = '(Paused)';
                 if (prePausePhase === 'break') currentMultiplier = 1.0; // Show 1.0x if break is paused
                break;
            default: //'idle'
                phaseLabel = 'Idle';
                // Multiplier shows potential for next session
                multiplierContext = '(Next Session)';
                break;
        }

        timerDisplay.textContent = formatTime(remainingSeconds);
        const titleSuffix = (phase === 'paused') ? ' (Paused)' : '';
        document.title = `${formatTime(remainingSeconds)} - ${phaseLabel}${titleSuffix} - Pomodoro`;

        // Update Points and Multiplier displays safely
        if (totalPointsDisplay) {
            totalPointsDisplay.textContent = totalPoints.toLocaleString();
        }
        if (activeMultiplierDisplay) {
            // Format multiplier to 1 decimal place
            let multiplierText = `${currentMultiplier.toFixed(1)}x`;
            // Add context span if needed
            if (multiplierContext) {
                 multiplierText += ` <span class="multiplier-context">${multiplierContext}</span>`;
            }
             activeMultiplierDisplay.innerHTML = multiplierText; // Use innerHTML to render the span
        }
    }

    function playAlarm() {
        if (alarmSound) {
            alarmSound.currentTime = 0;
            alarmSound.play().catch(e => console.error("Audio play failed:", e));
        }
    }

    function tick() {
        if (serverEndTimeUTC) {
            // Calculate remaining seconds based on server end time for accuracy
            const now = new Date();
            remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
        } else if (remainingSeconds > 0) {
             // Fallback: Decrement local counter if server time isn't set (shouldn't happen in normal flow)
             remainingSeconds--;
        } else {
             remainingSeconds = 0; // Ensure it doesn't go negative
        }

        updateUIDisplays(); // Update display based on calculated remaining time
        saveState(); // Save state every second

        if (remainingSeconds <= 0 && intervalId && (phase === 'work' || phase === 'break')) {
            // Only trigger completion if the timer was actually running
            console.log(`Timer tick reached zero for phase: ${phase}. Handling completion.`);
            handlePhaseCompletion();
        }
    }

    function startCountdown() {
        if (intervalId) clearInterval(intervalId); // Clear existing interval

        let runningPhase = phase;
        if (phase === 'idle') { // Starting fresh work session
            runningPhase = 'work';
            // Remaining seconds and end time will be set by API response
        } else if (phase === 'paused') { // Resuming from pause
            runningPhase = prePausePhase || 'work';
            // Recalculate serverEndTimeUTC if needed based on remainingSeconds? Or trust API value?
            // Best practice: server should provide the authoritative end time on start/resume if possible.
            // For now, assume serverEndTimeUTC is correct from initial load or start API call.
        }

        phase = runningPhase;
        prePausePhase = null; // Clear pre-pause state once running

        updateUIDisplays(); // Update display immediately
        saveState(); // Save state *after* phase is set

        // Start the interval timer
        intervalId = setInterval(tick, 1000);
        updateButtonStates(true); // Timer is running
        enableInputs(false); // Disable inputs

        statusMessage.textContent = `${phase === 'work' ? 'Work' : 'Break'} session started/resumed.`;
        console.log(`Countdown started for phase: ${phase}. Expected end: ${serverEndTimeUTC}`);
    }

    function pauseCountdown() {
        if (intervalId && phase !== 'paused') {
            const phaseBeforePause = phase; // Capture current phase
            stopCountdown(); // Use helper to clear interval
            prePausePhase = phaseBeforePause; // Store the phase *before* changing it
            phase = 'paused';
            // Keep serverEndTimeUTC as is.
            updateUIDisplays(); // Update display immediately after setting paused state
            saveState();
            updateButtonStates(false); // Timer is paused/stopped
            statusMessage.textContent = `Timer paused.`;
            console.log(`Countdown paused. Phase was: ${prePausePhase}`);
        }
    }

    function stopCountdown() { // Helper to just stop the interval
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
            console.log("Interval stopped.");
        }
    }

     function resetTimer(notifyServer = false) {
        stopCountdown();
        phase = 'idle';
        prePausePhase = null;
        remainingSeconds = 0;
        serverEndTimeUTC = null; // Clear server end time
        localStorage.removeItem(LS_KEY); // Clear saved state

        // Fetch potential multiplier for next session from server? Or estimate?
        // For simplicity, load initial multiplier from config again, or default to 1.0
        currentMultiplier = config.initialData?.activeMultiplier || 1.0;
        // Keep total points as they are, only API calls should change them.

        updateUIDisplays(); // Display 00:00 and Idle state
        updateButtonStates(false); // Show start, hide pause/reset
        enableInputs(true);
        statusMessage.textContent = 'Timer reset. Set durations and click Start.';
        document.title = "Pomodoro Timer";
        console.log("Timer reset locally.");

        // Optional: Send signal to server to clear ActiveTimerState
        // if (notifyServer) { sendResetSignalToServer(); }
    }

    function handlePhaseCompletion() {
        const completedPhase = phase; // Store before changing/stopping
        stopCountdown(); // Stop the interval immediately
        playAlarm();
        statusMessage.textContent = `Completing ${completedPhase} phase...`; // Indicate activity

        // Signal completion to backend (points/state update happens server-side)
        sendCompleteSignal(completedPhase);

        // Client state change is now handled within the sendCompleteSignal success callback
        // based on the response from the server.
    }

    // --- State Persistence (localStorage) ---

    function saveState() {
        // Only save state if timer is not idle
        if (phase === 'idle') {
            localStorage.removeItem(LS_KEY); // Clear state if idle
            return;
        }
        const state = {
            remainingSeconds: remainingSeconds, // Save remaining seconds based on calculation or decrement
            phase: phase,
            prePausePhase: prePausePhase,
            workDurationMinutes: workDurationMinutes,
            breakDurationMinutes: breakDurationMinutes,
            currentMultiplier: currentMultiplier, // Save current multiplier displayed
            totalPoints: totalPoints, // Save total points displayed
            serverEndTimeUTC: serverEndTimeUTC // Persist the expected end time
        };
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(state));
        } catch (e) {
            console.error("Failed to save state to localStorage:", e);
        }
    }

    function loadState() {
        let stateToLoad = null;
        let source = 'initial'; // Where did the state come from? 'initial', 'local', 'server_sync'

        // 1. Try loading from localStorage
        try {
            const savedState = localStorage.getItem(LS_KEY);
            if (savedState) {
                const parsedState = JSON.parse(savedState);
                // Basic validation
                if (typeof parsedState.remainingSeconds === 'number' && typeof parsedState.phase === 'string') {
                    stateToLoad = parsedState;
                    source = 'local';
                    console.log("State loaded from localStorage:", stateToLoad);
                } else {
                     console.warn("Invalid state structure in localStorage. Clearing.");
                     localStorage.removeItem(LS_KEY);
                }
            }
        } catch (e) {
            console.error("Failed to load or parse state from localStorage:", e);
            localStorage.removeItem(LS_KEY); // Clear corrupted state
        }

        // 2. Compare with initial server data if local state exists
        const serverState = config.initialData?.activeState;
        if (stateToLoad && serverState) { // Both local and server state exist
            console.log("Comparing local state with server state:", serverState);
            // If server says timer is active but local says idle/paused, or phases mismatch, prefer server.
            if (serverState.phase !== stateToLoad.phase && stateToLoad.phase !== 'paused') {
                console.warn(`State mismatch: Local=${stateToLoad.phase}, Server=${serverState.phase}. Syncing from server.`);
                stateToLoad = null; // Discard local, force load from server data below
                source = 'server_sync';
            } else if (serverState.phase === stateToLoad.phase && stateToLoad.phase !== 'paused') {
                 // If phases match and running, update end time from server for accuracy
                 console.log("Phases match, updating end time from server.");
                 stateToLoad.serverEndTimeUTC = serverState.endTime;
                 source = 'local_synced'; // Local state updated with server time
            }
            // If local is paused, generally keep it paused, serverEndTimeUTC might update if it changed.
             if(stateToLoad && stateToLoad.phase === 'paused') {
                stateToLoad.serverEndTimeUTC = serverState.endTime; // Update end time even if paused
                console.log("Local state is paused, updated server end time.");
             }

        } else if (!stateToLoad && serverState) { // No local state, but server has active state
            console.log("No local state found, using active state from server.");
            // Prepare to load from server data below
            source = 'server_initial';
        } else if (stateToLoad && !serverState) { // Local state exists, but server says inactive
            console.warn("Local state found, but server reports no active timer. Resetting local state.");
            resetTimer(); // Reset client to match server (inactive)
            return; // Stop further processing as timer is reset
        }


        // 3. Apply the chosen state (either from local storage or initial server data)
        if (stateToLoad) { // Load from localStorage (potentially synced)
             phase = stateToLoad.phase;
             prePausePhase = stateToLoad.prePausePhase || null;
             workDurationMinutes = stateToLoad.workDurationMinutes || 25;
             breakDurationMinutes = stateToLoad.breakDurationMinutes || 5;
             currentMultiplier = stateToLoad.currentMultiplier || 1.0;
             totalPoints = stateToLoad.totalPoints || config.initialData?.totalPoints || 0;
             serverEndTimeUTC = stateToLoad.serverEndTimeUTC || null;

             // Calculate remaining seconds based on server time if available
             if (serverEndTimeUTC) {
                 const now = new Date();
                 remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
                 console.log(`Calculated remaining seconds from serverEndTimeUTC: ${remainingSeconds}`);
             } else {
                  remainingSeconds = stateToLoad.remainingSeconds; // Fallback to saved seconds
                  console.log(`Using remaining seconds from local state: ${remainingSeconds}`);
             }


              // If the loaded state *should* be running but isn't paused, force pause
              if (phase === 'work' || phase === 'break') {
                 console.warn(`Loaded running state (${phase}) from ${source}. Forcing pause.`);
                 prePausePhase = phase;
                 phase = 'paused';
              }


        } else if (serverState) { // Load from initial server data
            phase = serverState.phase;
            prePausePhase = null; // No pre-pause state when loading fresh from server
            workDurationMinutes = serverState.workMins;
            breakDurationMinutes = serverState.breakMins;
            currentMultiplier = serverState.multiplier;
            totalPoints = config.initialData.totalPoints; // Get points from initial data
            serverEndTimeUTC = serverState.endTime;

            const now = new Date();
            remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
            console.log(`Loaded state from server. Phase: ${phase}, Remaining: ${remainingSeconds}s`);

            // Force pause state for user interaction
            prePausePhase = phase;
            phase = 'paused';
            console.log("Forcing pause state after loading from server.");

        } else { // No local state, no server state -> Start fresh/idle
            console.log("No active state found locally or on server. Initializing idle.");
            resetTimer(); // Ensure clean idle state
            return; // Stop processing
        }


        // 4. Update UI based on the final loaded state
        workInput.value = workDurationMinutes;
        breakInput.value = breakDurationMinutes;
        updateUIDisplays(); // Update timer, points, multiplier display

        if (phase === 'paused') {
            updateButtonStates(false); // Show Resume button
            enableInputs(false);
            statusMessage.textContent = `Loaded paused ${prePausePhase || '?'} session. Press Resume.`;
        } else if (phase === 'idle') {
            // Should have been handled by resetTimer() earlier
             updateButtonStates(false);
             enableInputs(true);
             statusMessage.textContent = 'Set durations and click Start.';
        } else {
            // Should not happen if forced pause logic works
            console.warn("State loaded into unexpected running phase:", phase);
            resetTimer(); // Reset if state is inconsistent
        }
    }


    // --- UI Updates ---

    function updateButtonStates(isRunning) {
        if (isRunning) {
            startBtn.style.display = 'none';
            pauseBtn.style.display = 'inline-block';
            resetBtn.style.display = 'inline-block';
            pauseBtn.textContent = 'Pause';
            pauseBtn.disabled = false; // Ensure pause is enabled when running
        } else { // Paused or Idle
            startBtn.style.display = 'inline-block';
            startBtn.textContent = (phase === 'paused') ? 'Resume' : 'Start';
            pauseBtn.style.display = 'none';
            pauseBtn.disabled = true; // Disable pause button when not running
            // Keep reset visible only if paused or idle (allow reset anytime?) - Keep visible if paused only for now
            resetBtn.style.display = (phase === 'paused') ? 'inline-block' : 'none';
        }
    }


    function enableInputs(enabled) {
         workInput.disabled = !enabled;
         breakInput.disabled = !enabled;
    }


    // --- API Communication ---

    async function sendStartSignal() {
         console.log("Sending start signal to server...");
         statusMessage.textContent = 'Starting...';
         // Disable buttons during API call
         startBtn.disabled = true;
         resetBtn.disabled = true;

         try {
            const response = await fetch(API_START_URL, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 body: JSON.stringify({ work: workDurationMinutes, break: breakDurationMinutes })
            });
            const data = await response.json(); // Assume server always returns JSON

            if (!response.ok) {
                // Throw an error to be caught below
                throw new Error(data.error || `Server error ${response.status}`);
            }

            console.log("Server acknowledged timer start.", data);
            // Update state from server response
            totalPoints = data.total_points;
            currentMultiplier = data.active_multiplier;
            serverEndTimeUTC = data.end_time; // Store the authoritative end time

            // Calculate initial remaining seconds based on server end time
            const now = new Date();
            remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));

            phase = 'work'; // Set phase explicitly after successful start
            prePausePhase = null; // Clear pre-pause state

            startCountdown(); // Start client timer now that server confirmed

         } catch (error) {
             console.error("Error sending start signal:", error);
             statusMessage.textContent = `Error: ${error.message || 'Could not start timer.'}`;
             // Re-enable start button on error
             startBtn.disabled = false;
             resetBtn.disabled = false; // Consider enabling reset again
             // Optionally reset UI to idle state?
             // resetTimer();
         } finally {
             // Re-enable buttons if they weren't re-enabled by other logic
             startBtn.disabled = false;
             resetBtn.disabled = false;
         }
    }

    async function sendCompleteSignal(completedPhase) {
         console.log(`Sending complete signal for phase: ${completedPhase}`);
         // Disable buttons during API call
         pauseBtn.disabled = true;
         resetBtn.disabled = true;

         try {
             const response = await fetch(API_COMPLETE_URL, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                 body: JSON.stringify({ phase_completed: completedPhase })
             });
             const data = await response.json(); // Assume JSON response

              if (!response.ok) {
                    throw new Error(data.error || `Server error ${response.status}`);
             }

             console.log(`Server acknowledged ${completedPhase} completion.`, data);
             // Update points from server response
             totalPoints = data.total_points;
             // Server end time should be cleared or updated for break phase
             serverEndTimeUTC = null; // Clear it, next start will set it again

             // Handle next phase based on server status response
             if (data.status === 'break_started') {
                 phase = 'break';
                 prePausePhase = null;
                 currentMultiplier = 1.0; // Break multiplier is 1.0
                 // Calculate break end time based on *now* + break duration
                 const now = new Date();
                 serverEndTimeUTC = new Date(now.getTime() + breakDurationMinutes * 60000).toISOString();
                 remainingSeconds = breakDurationMinutes * 60; // Set local remaining seconds

                 statusMessage.textContent = "Work complete! Starting break.";
                 updateUIDisplays(); // Update points/multiplier/timer
                 saveState(); // Save new break state
                 setTimeout(startCountdown, 500); // Start break countdown shortly

             } else if (data.status === 'session_complete') {
                 statusMessage.textContent = "Break complete! Session finished.";
                 setTimeout(resetTimer, 500); // Reset UI after short delay

             } else if (data.status === 'acknowledged_no_state'){
                 console.warn("Server had no state for completion signal. Resetting client.");
                 statusMessage.textContent = "Session desync? Resetting timer.";
                 setTimeout(resetTimer, 500);
             } else {
                 // Unexpected status
                 throw new Error(`Unexpected status from complete API: ${data.status}`);
             }

         } catch (error) {
              console.error(`Error sending complete signal (${completedPhase}):`, error);
              statusMessage.textContent = `Error: ${error.message || 'Could not complete phase.'}`;
              // What to do on error? Maybe try pausing locally?
              pauseCountdown(); // Attempt to pause the timer locally
              // Re-enable buttons after error
              pauseBtn.disabled = false;
              resetBtn.disabled = false;
         } finally {
             // Ensure buttons are re-enabled if applicable
             // The logic above might already handle enabling via state changes (e.g., resetTimer)
             // If paused, updateButtonStates(false) will handle it.
             if (phase !== 'idle') {
                 updateButtonStates(phase === 'paused' ? false : true);
             }
         }
    }

    // --- Initialization ---

    function init() {
        // Ensure essential elements exist before adding listeners
        if (!startBtn || !pauseBtn || !resetBtn || !timerDisplay || !statusMessage || !totalPointsDisplay || !activeMultiplierDisplay) {
            console.error("Required timer UI elements not found! Aborting initialization.");
            if(statusMessage) statusMessage.textContent = "UI Error: Missing elements.";
            // Disable controls if UI is broken
            if(startBtn) startBtn.disabled = true;
            if(workInput) workInput.disabled = true;
            if(breakInput) breakInput.disabled = true;
            return;
        }
        console.log("Initializing timer script...");
        console.log("Initial Config:", config);

        startBtn.addEventListener('click', () => {
            if (phase === 'idle') {
                // Get values from input fields at the moment start is clicked
                const currentWorkVal = parseInt(workInput.value) || 25;
                const currentBreakVal = parseInt(breakInput.value) || 5;
                if (currentWorkVal <= 0 || currentBreakVal <= 0) {
                     alert("Please enter positive values for work and break durations.");
                     return;
                }
                // Update state variables before sending API request
                workDurationMinutes = currentWorkVal;
                breakDurationMinutes = currentBreakVal;

                sendStartSignal(); // API call handles starting the countdown on success

            } else if (phase === 'paused') {
                 // Resuming locally
                 startCountdown();
            }
        });

        pauseBtn.addEventListener('click', pauseCountdown);

        resetBtn.addEventListener('click', () => {
             // Allow reset only when paused? Or anytime? Let's allow if paused.
             if (phase === 'paused') {
                 if (confirm("Are you sure you want to reset the timer? This will end the current session.")) {
                     resetTimer();
                     // Optional: send signal to server to clear state immediately
                 }
             } else {
                 console.log("Reset button clicked while not paused. Ignoring.");
             }
        });

        // Add input listeners to update state variables if changed *before* starting
         workInput.addEventListener('change', () => {
             if (phase === 'idle') {
                 workDurationMinutes = parseInt(workInput.value) || 25;
                 console.log("Work duration changed to:", workDurationMinutes);
             }
         });
         breakInput.addEventListener('change', () => {
              if (phase === 'idle') {
                  breakDurationMinutes = parseInt(breakInput.value) || 5;
                  console.log("Break duration changed to:", breakDurationMinutes);
              }
         });


        // Load state on initial page load (handles server sync logic)
        loadState();

        console.log("Timer initialization complete.");
    }

    // Run initialization only when the DOM is fully loaded and parsed
    if (document.readyState === 'loading') { // Loading hasn't finished yet
        document.addEventListener('DOMContentLoaded', init);
    } else { // `DOMContentLoaded` has already fired
        init();
    }

})(); // End of IIFE