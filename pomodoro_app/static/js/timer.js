// Wrap in IIFE to avoid global scope pollution
(function() {
    // Ensure the URLs are available from the global scope (set in timer.html)
    // Fallback to avoid errors if the script tag is somehow misplaced, though it shouldn't be.
    const API_START_URL = window.pomodoroUrls?.start || '/api/timer/start';
    const API_COMPLETE_URL = window.pomodoroUrls?.complete || '/api/timer/complete_phase';

    const timerDisplay = document.getElementById('timer-display');
    const statusMessage = document.getElementById('status-message');
    const workInput = document.getElementById('work-minutes');
    const breakInput = document.getElementById('break-minutes');
    const startBtn = document.getElementById('start-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const resetBtn = document.getElementById('reset-btn');
    const alarmSound = document.getElementById('alarm-sound');

    // State variables
    let intervalId = null;
    let remainingSeconds = 0;
    let phase = 'idle'; // 'idle', 'work', 'break', 'paused'
    let prePausePhase = null; // Stores the phase ('work' or 'break') before pausing
    let workDurationMinutes = 25;
    let breakDurationMinutes = 5;

    // localStorage Keys
    const LS_KEY = 'pomodoroState';

    // --- Core Timer Logic ---

    function formatTime(seconds) {
        // Ensure seconds is a non-negative number
        const safeSeconds = Math.max(0, Math.floor(seconds));
        const m = Math.floor(safeSeconds / 60);
        const s = safeSeconds % 60;
        return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    function updateDisplay() {
        // Determine the label based on the *actual* running/paused state
        let displayPhase = phase;
        if (phase === 'paused' && prePausePhase) {
            displayPhase = prePausePhase; // Show 'Work' or 'Break' even when paused
        }

        let phaseLabel = '';
        switch(displayPhase) { // Use displayPhase for label
            case 'work': phaseLabel = 'Work'; break;
            case 'break': phaseLabel = 'Break'; break;
            case 'paused': phaseLabel = 'Paused'; break; // Fallback if prePausePhase is null
            default: phaseLabel = 'Idle'; break;
        }
        timerDisplay.textContent = formatTime(remainingSeconds);
        // Add '(Paused)' to title if paused
        const titleSuffix = (phase === 'paused') ? ' (Paused)' : '';
        document.title = `${formatTime(remainingSeconds)} - ${phaseLabel}${titleSuffix} - Pomodoro`;
    }

    function playAlarm() {
        if (alarmSound) {
            alarmSound.currentTime = 0; // Rewind to start
            alarmSound.play().catch(e => console.error("Audio play failed:", e));
        }
    }

    function tick() {
        if (remainingSeconds > 0) {
            remainingSeconds--;
            updateDisplay();
            saveState(); // Save state every second
        }

        // Check for completion *after* potential decrement
        // Use <= 0 check for robustness
        if (remainingSeconds <= 0) {
            // Ensure we only handle completion once per phase end
            if (intervalId && (phase === 'work' || phase === 'break')) {
                handlePhaseCompletion();
            }
        }
    }

    function startCountdown() {
        if (intervalId) clearInterval(intervalId); // Clear any existing interval

        // Determine the correct running phase when starting/resuming
        let runningPhase = phase;
        if (phase === 'idle') { // Starting fresh work session
            runningPhase = 'work';
        } else if (phase === 'paused') { // Resuming from pause
            runningPhase = prePausePhase || 'work'; // Use stored pre-pause phase, default to work if missing
        } // If phase is already 'work' or 'break' (e.g., called by handlePhaseCompletion), keep it.

        phase = runningPhase; // Set the active running phase

        // Set remaining seconds only if starting a phase fresh from 0
        // This ensures resuming keeps the correct remaining time
        if (remainingSeconds <= 0) {
             if (phase === 'work') {
                remainingSeconds = workDurationMinutes * 60;
             } else if (phase === 'break') {
                remainingSeconds = breakDurationMinutes * 60;
             }
        }
         // If resuming from pause, remainingSeconds should already hold the correct value

        prePausePhase = null; // Clear pre-pause state once running

        updateDisplay(); // Update display immediately
        saveState(); // Save state *after* phase and seconds are set
        intervalId = setInterval(tick, 1000); // Start ticking
        updateButtonStates(true); // Timer is running
        statusMessage.textContent = `${phase === 'work' ? 'Work' : 'Break'} session started/resumed.`;
    }

    function pauseCountdown() {
        if (intervalId && phase !== 'paused') { // Only pause if running
            stopCountdown(); // Use helper to clear interval
            prePausePhase = phase; // *** Store the phase before pausing ***
            phase = 'paused';
            updateDisplay(); // *** Update display immediately after setting paused state ***
            saveState();
            updateButtonStates(false); // Timer is paused/stopped
            statusMessage.textContent = `Timer paused.`;
        }
    }

    function stopCountdown() { // Helper to just stop the interval
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
    }

     function resetTimer(notifyServer = false) {
        stopCountdown();
        phase = 'idle';
        prePausePhase = null; // Clear pre-pause state
        remainingSeconds = 0; // Reset time
        // Use current input values as defaults for next start
        workDurationMinutes = parseInt(workInput.value) || 25;
        breakDurationMinutes = parseInt(breakInput.value) || 5;
        localStorage.removeItem(LS_KEY); // Clear saved state
        updateDisplay(); // Display 00:00 and Idle state
        updateButtonStates(false); // Show start, hide pause/reset
        enableInputs(true);
        statusMessage.textContent = 'Timer reset. Set durations and click Start.';
        document.title = "Pomodoro Timer";

         // Optional: Notify server if reset happens mid-session
         // if (notifyServer) { sendResetSignal(); } // Implement sendResetSignal if needed
    }

    function handlePhaseCompletion() {
        const completedPhase = phase; // Store before changing
        stopCountdown(); // Stop interval explicitly
        playAlarm();

        // Signal completion to backend BEFORE changing client state
        sendCompleteSignal(completedPhase);

        if (completedPhase === 'work') {
            phase = 'break'; // Set next phase *before* starting countdown
            remainingSeconds = 0; // Ensure break starts fresh
            prePausePhase = null;
            statusMessage.textContent = "Work complete! Starting break.";
            saveState(); // Save break state before starting countdown
            // Use configured break duration
            remainingSeconds = breakDurationMinutes * 60;
            updateDisplay(); // Show initial break time
            setTimeout(startCountdown, 1000); // Start break countdown after 1 sec

        } else if (completedPhase === 'break') {
             statusMessage.textContent = "Break complete! Session finished.";
             // Fully reset after break
             setTimeout(resetTimer, 1000); // Reset UI after 1 sec
        }
    }

    // --- State Persistence (localStorage) ---

    function saveState() {
        // Only save state if timer is not idle
        if (phase === 'idle') {
            localStorage.removeItem(LS_KEY); // Clear state if idle
            return;
        }
        const state = {
            remainingSeconds,
            phase,
            prePausePhase, // *** Save prePausePhase ***
            workDurationMinutes,
            breakDurationMinutes
        };
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(state));
        } catch (e) {
            console.error("Failed to save state to localStorage:", e);
        }
    }

    function loadState() {
        try {
            const savedState = localStorage.getItem(LS_KEY);
            if (savedState) {
                const state = JSON.parse(savedState);
                // Validate loaded state properties
                if (typeof state.remainingSeconds !== 'number' || typeof state.phase !== 'string') {
                     throw new Error("Invalid state structure");
                }

                remainingSeconds = state.remainingSeconds;
                phase = state.phase; // Could be 'work', 'break', 'paused', or potentially 'idle' if saved incorrectly
                prePausePhase = state.prePausePhase || null; // *** Load prePausePhase ***
                workDurationMinutes = state.workDurationMinutes || 25; // Provide default
                breakDurationMinutes = state.breakDurationMinutes || 5; // Provide default

                // Update UI based on loaded state
                workInput.value = workDurationMinutes;
                breakInput.value = breakDurationMinutes;
                updateDisplay(); // Update display based on loaded state

                // If loaded state is technically running, force pause for user interaction
                if (phase === 'work' || phase === 'break') {
                     console.warn("Loaded running state, forcing pause.");
                     prePausePhase = phase; // Store the intended running phase
                     phase = 'paused';
                }

                if (phase === 'paused') {
                    updateButtonStates(false); // Show Resume button
                    enableInputs(false);
                    statusMessage.textContent = `Loaded paused ${prePausePhase || '?'} session. Press Resume.`;
                } else if (phase === 'idle') {
                     resetTimer(); // Treat loaded idle state as a reset
                } else {
                     // Unexpected state, reset
                     console.warn("Loaded unexpected state, resetting:", state);
                     resetTimer();
                }
            } else {
                 // No saved state, ensure UI is default
                 resetTimer();
            }
        } catch (e) {
            console.error("Failed to load or parse state from localStorage:", e);
            localStorage.removeItem(LS_KEY); // Clear potentially corrupted state
            resetTimer(); // Reset to default
        }
    }

    // --- UI Updates ---

    function updateButtonStates(isRunning) {
        if (isRunning) {
            startBtn.style.display = 'none';
            pauseBtn.style.display = 'inline-block';
            resetBtn.style.display = 'inline-block';
            pauseBtn.textContent = 'Pause';
        } else { // Paused or Idle
            startBtn.style.display = 'inline-block';
            startBtn.textContent = (phase === 'paused') ? 'Resume' : 'Start'; // Change text if paused
            pauseBtn.style.display = 'none';
            // Keep reset visible only if paused
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
         try {
            // Use the URL defined globally (from timer.html)
            const response = await fetch(API_START_URL, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}, // Added Accept
                 body: JSON.stringify({ work: workDurationMinutes, break: breakDurationMinutes })
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: "Unknown server error" })); // Try to parse error
                console.error("Server error on start:", response.status, errorData);
            } else {
                 console.log("Server acknowledged timer start.");
                 // const data = await response.json(); // Process if needed
            }
         } catch (error) {
             console.error("Network error sending start signal:", error);
             // TODO: Maybe inform user that state might not be synced with server?
         }
    }

    async function sendCompleteSignal(completedPhase) {
         console.log(`Sending complete signal for phase: ${completedPhase}`);
         try {
             // Use the URL defined globally (from timer.html)
             const response = await fetch(API_COMPLETE_URL, {
                 method: 'POST',
                 headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}, // Added Accept
                 body: JSON.stringify({ phase_completed: completedPhase })
             });
              if (!response.ok) {
                 const errorData = await response.json().catch(() => ({ error: "Unknown server error" })); // Try to parse error
                 console.error(`Server error on complete phase (${completedPhase}):`, response.status, errorData);
             } else {
                 console.log(`Server acknowledged ${completedPhase} completion.`);
                 // const data = await response.json(); // Process if needed
             }
         } catch (error) {
              console.error(`Network error sending complete signal (${completedPhase}):`, error);
               // TODO: Maybe inform user that state might not be synced with server?
         }
    }

    // --- Initialization ---

    function init() {
        // Ensure essential elements exist before adding listeners
        if (!startBtn || !pauseBtn || !resetBtn) {
            console.error("Timer control buttons not found in the DOM!");
            return;
        }

        startBtn.addEventListener('click', () => {
            // Handles both Start and Resume clicks
            if (phase === 'idle') { // Starting fresh
                workDurationMinutes = parseInt(workInput.value) || 25;
                breakDurationMinutes = parseInt(breakInput.value) || 5;
                if (workDurationMinutes <= 0 || breakDurationMinutes <= 0) {
                     alert("Please enter positive values for work and break durations.");
                     return;
                }
                remainingSeconds = 0; // Ensure start from full duration
                enableInputs(false); // Disable inputs once started
                sendStartSignal(); // Notify server
                startCountdown();
            } else if (phase === 'paused') { // Resuming
                 enableInputs(false);
                 startCountdown(); // Resumes from remainingSeconds and restores prePausePhase
            }
        });

        pauseBtn.addEventListener('click', pauseCountdown); // Should work correctly now

        resetBtn.addEventListener('click', () => {
             if (confirm("Are you sure you want to reset the timer? This will end the current session and clear server state.")) {
                 resetTimer();
                 // Consider if server needs notification on reset (e.g., clear active_timers[user_id])
                 // sendResetSignal(); // <-- Implement if needed to clear server state immediately
             }
        });

        // Load state on initial page load
        loadState();
    }

    // Run initialization only when the DOM is fully loaded and parsed
    if (document.readyState === 'loading') { // Loading hasn't finished yet
        document.addEventListener('DOMContentLoaded', init);
    } else { // `DOMContentLoaded` has already fired
        init();
    }

})(); // End of IIFE