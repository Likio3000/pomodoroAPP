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
    let serverEndTimeUTC = null; // Store expected end time from server

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
        if (serverEndTimeUTC) {
            const now = new Date();
            remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
        } else if (remainingSeconds > 0) {
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
            runningPhase = prePausePhase || 'work';
            // serverEndTimeUTC should be correct from load or API response
        }

        phase = runningPhase;
        prePausePhase = null;

        updateUIDisplays(); // Update display immediately
        saveState(); // Save state *after* phase is set

        intervalId = setInterval(tick, 1000);
        updateButtonStates(true); // Timer is running
        enableInputs(false); // Disable inputs

        elements.statusMessage.textContent = `${phase === 'work' ? 'Work' : 'Break'} session started/resumed.`;
        console.log(`Countdown started for phase: ${phase}. Expected end: ${serverEndTimeUTC}`);
    }

    function pauseCountdown() {
        if (intervalId && phase !== 'paused') {
            const phaseBeforePause = phase;
            stopCountdown(); // Helper to clear interval
            prePausePhase = phaseBeforePause;
            phase = 'paused';
            // Keep serverEndTimeUTC
            updateUIDisplays();
            saveState();
            updateButtonStates(false); // Timer is paused
            elements.statusMessage.textContent = `Timer paused.`;
            console.log(`Countdown paused. Phase was: ${prePausePhase}`);
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
        localStorage.removeItem(LS_KEY);

        // Reset to defaults or initial config data
        // Use initial config data for points/multiplier if available on first load reset
        // Otherwise, keep current points/multiplier if reset happens mid-session
        workDurationMinutes = parseInt(elements.workInput?.value) || initialConfigData?.workMins || 25;
        breakDurationMinutes = parseInt(elements.breakInput?.value) || initialConfigData?.breakMins || 5;
        currentMultiplier = initialConfigData?.activeMultiplier || window.PomodoroLogic.currentMultiplier || 1.0; // Keep current mult if exists
        totalPoints = initialConfigData?.totalPoints || window.PomodoroLogic.totalPoints || 0; // Keep current points if exists

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
            remainingSeconds: remainingSeconds,
            phase: phase,
            prePausePhase: prePausePhase,
            workDurationMinutes: workDurationMinutes,
            breakDurationMinutes: breakDurationMinutes,
            currentMultiplier: currentMultiplier,
            totalPoints: totalPoints,
            serverEndTimeUTC: serverEndTimeUTC
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
        if (stateToLoad && serverState) {
            console.log("Comparing local state with server state:", serverState);
            if (serverState.phase !== stateToLoad.phase && stateToLoad.phase !== 'paused') {
                console.warn(`State mismatch. Syncing from server.`);
                stateToLoad = null; source = 'server_sync';
            } else if (serverState.phase === stateToLoad.phase && stateToLoad.phase !== 'paused' || stateToLoad.phase === 'paused') {
                stateToLoad.serverEndTimeUTC = serverState.endTime;
                console.log("Local state kept/paused, updated server end time.");
                source = stateToLoad.phase === 'paused' ? 'local_paused_synced' : 'local_synced';
            }
        } else if (!stateToLoad && serverState) {
            console.log("No local state, using active state from server."); source = 'server_initial';
        } else if (stateToLoad && !serverState) {
            console.warn("Local state found, but server inactive. Resetting local state.");
            // Pass the original initial config data to reset properly
            resetTimer(window.pomodoroConfig?.initialData || {});
            return;
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

             if (serverEndTimeUTC) {
                 const now = new Date();
                 remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
             } else { remainingSeconds = stateToLoad.remainingSeconds; }

              if (phase === 'work' || phase === 'break') { // Force pause on load if running
                 console.warn(`Loaded running state (${phase}) from ${source}. Forcing pause.`);
                 prePausePhase = phase; phase = 'paused';
              }
        } else if (serverState) { // From initial server data
            phase = serverState.phase; prePausePhase = null;
            workDurationMinutes = serverState.workMins; breakDurationMinutes = serverState.breakMins;
            currentMultiplier = serverState.multiplier; totalPoints = initialConfigData.totalPoints;
            serverEndTimeUTC = serverState.endTime;

            const now = new Date();
            remainingSeconds = Math.max(0, Math.floor((new Date(serverEndTimeUTC) - now) / 1000));
            console.log(`Loaded state from server. Phase: ${phase}, Remaining: ${remainingSeconds}s`);

            prePausePhase = phase; phase = 'paused'; // Force pause
            console.log("Forcing pause state after loading from server.");
        } else { // No state -> Start fresh/idle
            console.log("No active state found. Initializing idle.");
            resetTimer(window.pomodoroConfig?.initialData || {}); return;
        }

        // 4. Update UI based on loaded state
        if(elements.workInput) elements.workInput.value = workDurationMinutes;
        if(elements.breakInput) elements.breakInput.value = breakDurationMinutes;
        updateUIDisplays();

        if (phase === 'paused') {
            updateButtonStates(false); // Show Resume
            enableInputs(false);
            elements.statusMessage.textContent = `Loaded paused ${prePausePhase || '?'} session. Press Resume.`;
        } else if (phase === 'idle') {
             updateButtonStates(false); enableInputs(true);
             elements.statusMessage.textContent = 'Set durations and click Start.';
        } else {
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