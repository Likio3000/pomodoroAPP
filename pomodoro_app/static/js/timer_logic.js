// pomodoro_app/static/js/timer_logic.js
// Contains core timer state, countdown logic, UI updates, and state persistence.

// Expose functions and state via a global object
window.PomodoroLogic = (function() {
    'use strict';

    // --- State variables (scoped within this module) ---
    let intervalId = null;
    let remainingSeconds = 0;
    let phase = 'idle'; // 'idle', 'work', 'break', 'paused'
    let prePausePhase = null;
    let serverEndTimeUTC = null; // Store expected end time from server (ISO String)
    let pauseStartTime = null; // Timestamp (ms) when pause began

    // Durations, points, multiplier - initialized by loadState or init
    let workDurationMinutes = 25;
    let breakDurationMinutes = 5;
    let currentMultiplier = 1.0;
    let totalPoints = 0;

    const LS_KEY = 'pomodoroState_v2';

    // --- DOM Elements (passed in via init) ---
    let elements = {
        timerDisplay: null,
        statusMessage: null,
        workInput: null,
        breakInput: null,
        alarmSound: null,
        totalPointsDisplay: null,
        activeMultiplierDisplay: null,
        startBtn: null,
        pauseBtn: null,
        resetBtn: null
    };

    // --- Core Timer Logic ---

    function formatTime(seconds) {
        const safeSeconds = Math.max(0, Math.floor(seconds));
        const m = Math.floor(safeSeconds / 60);
        const s = safeSeconds % 60;
        return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    function playAlarm() {
        if (elements.alarmSound) {
            elements.alarmSound.currentTime = 0;
            elements.alarmSound.play().catch(e => console.error("Audio play failed:", e));
        }
    }

    function tick() {
        // Calculate remaining time based on adjusted serverEndTimeUTC
        if (serverEndTimeUTC) {
            const now = Date.now(); // Use ms for more precise calculation base
            const endTimeMs = new Date(serverEndTimeUTC).getTime();
            remainingSeconds = Math.max(0, Math.floor((endTimeMs - now) / 1000));
        } else if (remainingSeconds > 0) {
             // Fallback ONLY if serverEndTimeUTC isn't set (shouldn't happen in normal flow)
             remainingSeconds--;
        } else {
             remainingSeconds = 0;
        }

        updateUIDisplays(); // Update display based on calculated time
        saveState(); // Save state every second

        if (remainingSeconds <= 0 && intervalId && (phase === 'work' || phase === 'break')) {
            console.log(`Timer tick reached zero for phase: ${phase}. Handling completion.`);
            handlePhaseCompletion(); // Call the local handler
        }
    }

    function startCountdown() {
        if (intervalId) clearInterval(intervalId);

        let runningPhase = phase;
        if (phase === 'idle') {
            runningPhase = 'work'; // API response sets remaining seconds / end time
        } else if (phase === 'paused') {
             // --- Adjust serverEndTimeUTC on Resume ---
             if (pauseStartTime && serverEndTimeUTC) {
                 const pauseDurationMs = Date.now() - pauseStartTime;
                 if (pauseDurationMs > 100) { // Only adjust if pause was significant (e.g., > 100ms)
                     const currentEndTime = new Date(serverEndTimeUTC);
                     const newEndTime = new Date(currentEndTime.getTime() + pauseDurationMs);
                     serverEndTimeUTC = newEndTime.toISOString(); // Update with adjusted time
                     console.log(`Resumed. Adjusted serverEndTimeUTC by ${Math.round(pauseDurationMs/1000)}s to: ${serverEndTimeUTC}`);
                 }
                 pauseStartTime = null; // Clear pause start time
             }
             // --- End Adjust ---
             runningPhase = prePausePhase || 'work'; // Determine phase to resume
        }

        phase = runningPhase;
        prePausePhase = null;

        // Update display immediately before starting interval
        // Manually trigger a tick calculation to show the correct time instantly
        tick(); // Calculate remainingSeconds based on potentially adjusted serverEndTimeUTC
        updateUIDisplays(); // Display the freshly calculated time
        saveState(); // Save state *after* phase is set and time potentially adjusted

        intervalId = setInterval(tick, 1000);
        updateButtonStates(true); // Timer is running
        enableInputs(false); // Disable inputs

        elements.statusMessage.textContent = `${phase === 'work' ? 'Work' : 'Break'} session started/resumed.`;
        console.log(`Countdown started/resumed for phase: ${phase}. Expected end: ${serverEndTimeUTC}`);
    }

    function pauseCountdown() {
        if (intervalId && phase !== 'paused') {
            const phaseBeforePause = phase;
            stopCountdown(); // Helper to clear interval
            prePausePhase = phaseBeforePause;
            phase = 'paused';
            pauseStartTime = Date.now(); // <<<<<< Record pause start time
            // Keep serverEndTimeUTC - it will be adjusted on resume
            updateUIDisplays(); // Show paused state
            saveState(); // Save paused state including pauseStartTime
            updateButtonStates(false); // Timer is paused
            elements.statusMessage.textContent = `Timer paused.`;
            console.log(`Countdown paused. Phase was: ${prePausePhase}. Pause started at: ${pauseStartTime}`);
        }
    }

    function stopCountdown() {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
            console.log("Interval stopped.");
        }
    }

    function resetTimer(initialConfigData = {}) {
        console.log("Resetting timer (logic)...");
        stopCountdown();
        phase = 'idle';
        prePausePhase = null;
        remainingSeconds = 0;
        serverEndTimeUTC = null;
        pauseStartTime = null; // <<<<<< Clear pause start time on reset
        localStorage.removeItem(LS_KEY);

        // Reset durations
        workDurationMinutes = parseInt(elements.workInput?.value) || initialConfigData?.workMins || 25;
        breakDurationMinutes = parseInt(elements.breakInput?.value) || initialConfigData?.breakMins || 5;

        // Reset points/multiplier only if initialConfigData is provided (i.e., page load)
        // Otherwise, keep the current values accumulated so far if reset is manual
        if (initialConfigData && Object.keys(initialConfigData).length > 0) {
             window.PomodoroLogic.currentMultiplier = initialConfigData.activeMultiplier ?? 1.0;
             window.PomodoroLogic.totalPoints = initialConfigData.totalPoints ?? 0;
        } else {
            // Manual reset keeps current points/multiplier but resets timer phase/time
            // Multiplier might reset visually to 'Next Session' context
        }
        currentMultiplier = window.PomodoroLogic.currentMultiplier;
        totalPoints = window.PomodoroLogic.totalPoints;


        // Update UI
        if(elements.workInput) elements.workInput.value = workDurationMinutes;
        if(elements.breakInput) elements.breakInput.value = breakDurationMinutes;
        updateUIDisplays(); // Display 00:00, Idle state, potential multiplier/points
        updateButtonStates(false); // Show start, hide pause
        enableInputs(true);
        elements.statusMessage.textContent = 'Timer reset. Set durations and click Start.';
        document.title = "Pomodoro Timer";
    }

    function handlePhaseCompletion() {
        const completedPhase = phase;
        stopCountdown();
        playAlarm();
        pauseStartTime = null; // <<<<<< Clear pause start time on completion too
        if (elements.statusMessage) {
            elements.statusMessage.textContent = `Completing ${completedPhase} phase...`;
        }

        // Call the API function
        if (window.PomodoroAPI && typeof window.PomodoroAPI.sendCompleteSignal === 'function') {
             window.PomodoroAPI.sendCompleteSignal(completedPhase);
        } else {
             console.error("PomodoroAPI.sendCompleteSignal not found!");
             elements.statusMessage.textContent = "Error: Cannot contact server.";
        }
    }


    // --- UI Updates ---

    function updateUIDisplays() {
        if (!elements.timerDisplay) return; // Guard against missing elements

        let displayPhase = phase;
        if (phase === 'paused' && prePausePhase) {
            displayPhase = prePausePhase;
        }

        let phaseLabel = '';
        let multiplierContext = '';
        let displayMultiplier = currentMultiplier; // Start with current

        switch(displayPhase) {
            case 'work': phaseLabel = 'Work'; multiplierContext = ''; break;
            case 'break': phaseLabel = 'Break'; multiplierContext = '(Break Rate)'; displayMultiplier = 1.0; break; // Force 1.0x during break
            case 'paused':
                phaseLabel = prePausePhase === 'break' ? 'Break Paused' : 'Work Paused';
                multiplierContext = '(Paused)';
                 if (prePausePhase === 'break') displayMultiplier = 1.0; // Show 1.0x if break paused
                break;
            default: //'idle'
                phaseLabel = 'Idle'; multiplierContext = '(Next Session)'; break;
        }

        elements.timerDisplay.textContent = formatTime(remainingSeconds);
        const titleSuffix = (phase === 'paused') ? ' (Paused)' : '';
        document.title = `${formatTime(remainingSeconds)} - ${phaseLabel}${titleSuffix} - Pomodoro`;

        if (elements.totalPointsDisplay) {
            elements.totalPointsDisplay.textContent = totalPoints.toLocaleString();
        }
        if (elements.activeMultiplierDisplay) {
            let multiplierText = `${displayMultiplier.toFixed(1)}x`;
            if (multiplierContext) {
                 multiplierText += ` <span class="multiplier-context">${multiplierContext}</span>`;
            }
             elements.activeMultiplierDisplay.innerHTML = multiplierText;
        }
    }

    function updateButtonStates(isRunning) {
        if (!elements.startBtn || !elements.pauseBtn || !elements.resetBtn) return;

        if (isRunning) {
            elements.startBtn.style.display = 'none';
            elements.pauseBtn.style.display = 'inline-block';
            elements.resetBtn.style.display = 'inline-block'; // Keep reset visible
            elements.pauseBtn.textContent = 'Pause';
            elements.pauseBtn.disabled = false;
        } else { // Paused or Idle
            elements.startBtn.style.display = 'inline-block';
            elements.startBtn.textContent = (phase === 'paused') ? 'Resume' : 'Start';
            elements.pauseBtn.style.display = 'none';
            elements.pauseBtn.disabled = true;
            elements.resetBtn.style.display = 'inline-block'; // Keep reset visible
        }
         // Ensure Start/Resume button is enabled when visible
         elements.startBtn.disabled = false;
         // Ensure Reset button is also enabled when visible (API module handles disabling during calls)
         elements.resetBtn.disabled = false;
    }

    function enableInputs(enabled) {
         if(elements.workInput) elements.workInput.disabled = !enabled;
         if(elements.breakInput) elements.breakInput.disabled = !enabled;
    }


    // --- State Persistence ---

    function saveState() {
        if (phase === 'idle') {
            localStorage.removeItem(LS_KEY);
            return;
        }
        const state = {
            remainingSeconds: remainingSeconds, // Save calculated remaining seconds
            phase: phase,
            prePausePhase: prePausePhase,
            workDurationMinutes: workDurationMinutes,
            breakDurationMinutes: breakDurationMinutes,
            currentMultiplier: currentMultiplier,
            totalPoints: totalPoints,
            serverEndTimeUTC: serverEndTimeUTC, // Save the potentially adjusted end time
            pauseStartTime: pauseStartTime // <<<<<< Save pause start time if paused
        };
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(state));
        } catch (e) { console.error("Failed to save state:", e); }
    }

    function loadState(initialConfigData) {
        let stateToLoad = null;
        let source = 'initial';

        // 1. Try loading from localStorage
        try {
            const savedState = localStorage.getItem(LS_KEY);
            if (savedState) {
                const parsedState = JSON.parse(savedState);
                if (typeof parsedState.remainingSeconds === 'number' && typeof parsedState.phase === 'string') {
                    stateToLoad = parsedState;
                    source = 'local';
                    console.log("State loaded from localStorage:", stateToLoad);
                } else { localStorage.removeItem(LS_KEY); }
            }
        } catch (e) { console.error("Failed to load/parse state:", e); localStorage.removeItem(LS_KEY); }

        // 2. Compare with initial server data
        const serverState = initialConfigData?.activeState;
        if (stateToLoad && serverState) { // Both local and server state exist
             console.log("Comparing local state with server state:", serverState);
             // Sync based on server if phases mismatch AND local isn't paused
             if (serverState.phase !== stateToLoad.phase && stateToLoad.phase !== 'paused') {
                 console.warn(`State mismatch. Syncing from server.`);
                 stateToLoad = null; source = 'server_sync';
             }
             // If phases match or local is paused, update end time from server
             else if (stateToLoad.phase === 'paused' || serverState.phase === stateToLoad.phase) {
                  stateToLoad.serverEndTimeUTC = serverState.endTime; // Update end time
                  console.log("Local state kept/paused, updated server end time.");
                  source = stateToLoad.phase === 'paused' ? 'local_paused_synced' : 'local_synced';
             }
        } else if (!stateToLoad && serverState) { // No local state, but server has active state
            console.log("No local state, using active state from server."); source = 'server_initial';
        } else if (stateToLoad && !serverState) { // Local state exists, but server says inactive
            console.warn("Local state found, but server inactive. Resetting local state.");
            resetTimer(window.pomodoroConfig?.initialData || {}); return;
        }

        // 3. Apply the chosen state
        if (stateToLoad) { // From localStorage
             phase = stateToLoad.phase;
             prePausePhase = stateToLoad.prePausePhase || null;
             workDurationMinutes = stateToLoad.workDurationMinutes || 25;
             breakDurationMinutes = stateToLoad.breakDurationMinutes || 5;
             currentMultiplier = stateToLoad.currentMultiplier || 1.0;
             totalPoints = stateToLoad.totalPoints || initialConfigData?.totalPoints || 0;
             serverEndTimeUTC = stateToLoad.serverEndTimeUTC || null;
             pauseStartTime = stateToLoad.pauseStartTime || null; // <<<<<< Load pause start time

             // Calculate remaining seconds based on server time if available and *not paused*
             // If paused, keep the saved remainingSeconds as the source of truth until resume
             if (serverEndTimeUTC && phase !== 'paused') {
                 const now = Date.now();
                 const endTimeMs = new Date(serverEndTimeUTC).getTime();
                 remainingSeconds = Math.max(0, Math.floor((endTimeMs - now) / 1000));
                 console.log(`Calculated remaining seconds from serverEndTimeUTC: ${remainingSeconds}`);
             } else if (phase === 'paused') {
                  remainingSeconds = stateToLoad.remainingSeconds; // Use saved seconds if paused
                  console.log(`Using remaining seconds from paused local state: ${remainingSeconds}`);
             } else {
                  remainingSeconds = stateToLoad.remainingSeconds; // Fallback
                  console.log(`Using remaining seconds from non-paused local state: ${remainingSeconds}`);
             }

              // Force pause on load if state was running (just to be safe, user needs to resume)
              if (phase === 'work' || phase === 'break') {
                 console.warn(`Loaded running state (${phase}) from ${source}. Forcing pause.`);
                 prePausePhase = phase; phase = 'paused';
                 if (!pauseStartTime) { // If loaded state didn't have pause time, set it now
                    pauseStartTime = Date.now();
                 }
              }
        } else if (serverState) { // From initial server data
            phase = serverState.phase; prePausePhase = null;
            workDurationMinutes = serverState.workMins; breakDurationMinutes = serverState.breakMins;
            currentMultiplier = serverState.multiplier; totalPoints = initialConfigData.totalPoints;
            serverEndTimeUTC = serverState.endTime;
            pauseStartTime = null; // No pause state from server

            const now = Date.now();
            const endTimeMs = new Date(serverEndTimeUTC).getTime();
            remainingSeconds = Math.max(0, Math.floor((endTimeMs - now) / 1000));
            console.log(`Loaded state from server. Phase: ${phase}, Remaining: ${remainingSeconds}s`);

            // Force pause on initial load from server active state
            prePausePhase = phase; phase = 'paused';
            pauseStartTime = Date.now(); // Set pause time since we forced pause
            console.log("Forcing pause state after loading from server.");

        } else { // No state -> Start fresh/idle
            console.log("No active state found. Initializing idle.");
            resetTimer(window.pomodoroConfig?.initialData || {}); return;
        }

        // Update exposed state properties after loading
        window.PomodoroLogic.currentMultiplier = currentMultiplier;
        window.PomodoroLogic.totalPoints = totalPoints;

        // 4. Update UI based on loaded state
        if(elements.workInput) elements.workInput.value = workDurationMinutes;
        if(elements.breakInput) elements.breakInput.value = breakDurationMinutes;
        updateUIDisplays(); // Display the calculated/loaded time

        if (phase === 'paused') {
            updateButtonStates(false); // Show Resume
            enableInputs(false);
            elements.statusMessage.textContent = `Loaded paused ${prePausePhase || '?'} session. Press Resume.`;
        } else if (phase === 'idle') {
             updateButtonStates(false); enableInputs(true);
             elements.statusMessage.textContent = 'Set durations and click Start.';
        } else {
            // Should not happen if forced pause logic works
            console.warn("State loaded into unexpected running phase:", phase);
            resetTimer(window.pomodoroConfig?.initialData || {});
        }
    }

    // --- Public Methods & Properties ---
    // Expose methods needed by other modules/init script
    // Also expose state variables needed by resetTimer
    return {
        // State (accessible for reset logic)
        currentMultiplier: currentMultiplier,
        totalPoints: totalPoints,

        // Methods
        init: function(domElements, initialConfig) {
             console.log("Initializing Pomodoro Logic...");
             elements = domElements; // Store passed DOM elements

             // Initialize state variables from config BEFORE loadState
             const initialData = initialConfig?.initialData || {};
             workDurationMinutes = initialData?.activeState?.workMins || parseInt(elements.workInput?.value) || 25;
             breakDurationMinutes = initialData?.activeState?.breakMins || parseInt(elements.breakInput?.value) || 5;
             // Assign to the module's state directly
             window.PomodoroLogic.currentMultiplier = initialData?.activeMultiplier || 1.0;
             window.PomodoroLogic.totalPoints = initialData?.totalPoints || 0;

             loadState(initialData); // Load persistent/server state
             console.log("Pomodoro Logic Initialized.");
        },
        startCountdown: startCountdown,
        pauseCountdown: pauseCountdown,
        resetTimer: resetTimer, // Expose reset
        updateUIDisplays: updateUIDisplays, // Expose for API callbacks
        updateButtonStates: updateButtonStates, // Expose for API callbacks
        enableInputs: enableInputs, // Expose for API callbacks

        // State setting methods (used by API module)
        setPhase: function(newPhase) { phase = newPhase; },
        setPrePausePhase: function(newPrePause) { prePausePhase = newPrePause; },
        setServerEndTimeUTC: function(newTime) { serverEndTimeUTC = newTime; },
        setRemainingSeconds: function(seconds) { remainingSeconds = seconds; },
        setTotalPoints: function(points) { totalPoints = points; window.PomodoroLogic.totalPoints = points; }, // Update exposed property too
        setCurrentMultiplier: function(multiplier) { currentMultiplier = multiplier; window.PomodoroLogic.currentMultiplier = multiplier; }, // Update exposed property too
        setWorkDuration: function(duration) { workDurationMinutes = duration; },
        setBreakDuration: function(duration) { breakDurationMinutes = duration; },

        // Getters for state needed by other modules
        getPhase: function() { return phase; },
        getWorkDuration: function() { return workDurationMinutes; },
        getBreakDuration: function() { return breakDurationMinutes; }
    };

})(); // End of IIFE