// pomodoro_app/static/js/timer_logic.js
// Contains core timer state, countdown logic, UI updates, and state persistence.

// Expose functions and state via a global object
window.PomodoroLogic = (function() {
    'use strict';

    // --- State variables (scoped within this module) ---
    let intervalId = null;
    let remainingSeconds = 0;
    let phase = 'idle'; // 'idle', 'work', 'break', 'paused'
    let prePausePhase = null; // Stores 'work' or 'break' when paused
    let serverEndTimeUTC = null; // Store expected end time from server (ISO String) - Gets adjusted on RESUME
    let pauseStartTime = null; // Timestamp (ms UTC) when pause began

    // Durations, points, multiplier - initialized by loadState or init
    let workDurationMinutes = 25;
    let breakDurationMinutes = 5;
    let currentMultiplier = 1.0; // Potential multiplier for next session or active session
    let totalPoints = 0; // User's total points

    const LS_KEY = 'pomodoroState_v2'; // Local storage key

    // --- DOM Elements (passed in via init) ---
    let elements = {
        timerDisplay: null, statusMessage: null,
        workInput: null, breakInput: null,
        alarmSound: null, totalPointsDisplay: null,
        activeMultiplierDisplay: null, startBtn: null,
        pauseBtn: null, resetBtn: null
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
            elements.alarmSound.currentTime = 0; // Rewind before playing
            elements.alarmSound.play().catch(e => console.error("Audio play failed:", e));
        }
    }

    function tick() {
        // Calculate remaining time based on serverEndTimeUTC (which is adjusted on resume)
        if (serverEndTimeUTC && phase !== 'paused' && phase !== 'idle') {
            const now = Date.now(); // Current time in ms UTC
            const endTimeMs = new Date(serverEndTimeUTC).getTime(); // Target end time in ms UTC

            // Calculate remaining seconds based on the potentially adjusted end time
            remainingSeconds = Math.max(0, Math.floor((endTimeMs - now) / 1000));

            // --- Add check: If serverEndTimeUTC is past but timer still ticking, force completion ---
            if (now >= endTimeMs && intervalId && (phase === 'work' || phase === 'break')) {
                 console.warn(`Timer tick detected end time ${serverEndTimeUTC} has passed (Now: ${new Date(now).toISOString()}). Forcing completion.`);
                 remainingSeconds = 0; updateUIDisplays(); handlePhaseCompletion(); return;
            }
            // --- End check ---

        } else if (phase === 'paused') {
            // If paused, remainingSeconds should NOT change automatically.
        }
        else if (phase !== 'idle') {
            // Fallback only if serverEndTimeUTC isn't set but timer is somehow running
            console.warn("Tick running without serverEndTimeUTC, decrementing manually.");
            remainingSeconds = Math.max(0, remainingSeconds - 1);
        }

        updateUIDisplays(); // Update display based on calculated/static time

        // Check for completion only if running and not paused
        if (remainingSeconds <= 0 && intervalId && (phase === 'work' || phase === 'break')) {
            console.log(`Timer tick reached zero for phase: ${phase}. Handling completion.`);
            handlePhaseCompletion(); // Call the local handler
        } else {
            if (phase !== 'idle') { saveState(); } // Save state every second while active
        }
    }


    // MODIFIED startCountdown - Now calls API on resume
    async function startCountdown() { // <<< Make async to await API call
        if (intervalId) clearInterval(intervalId); // Clear any existing interval

        let runningPhase = phase;

        if (phase === 'idle') {
            // Start from idle (should only happen after API start call)
             console.error("startCountdown called while phase is still 'idle'. API flow issue?");
             if (serverEndTimeUTC && window.PomodoroLogic.phase === 'work') {
                 runningPhase = 'work'; console.warn("Recovering startCountdown - Assuming 'work'.");
             } else {
                 elements.statusMessage.textContent = "Error: Cannot start, state invalid.";
                 updateButtonStates(false); enableInputs(true); return;
             }
        } else if (phase === 'paused') {
             // --- Handle Resume ---
             if (pauseStartTime && serverEndTimeUTC) {
                 const pauseDurationMs = Date.now() - pauseStartTime; // Calculate how long pause lasted
                 console.log(`Attempting to resume. Calculated pause duration: ${pauseDurationMs}ms`);

                 // --- Call API to update server end time ---
                 const resumeApiSuccess = await window.PomodoroAPI.sendResumeSignal(pauseDurationMs); // << Await API call

                 if (!resumeApiSuccess) {
                      console.error("Server resume failed. Keeping timer paused.");
                      // API module's error handler should have updated status message and buttons
                      return; // Stop startCountdown if API failed
                 }
                 // --- API Success ---
                 console.log("Server resume successful. Proceeding with client resume.");

                 // API response *might* have updated serverEndTimeUTC via setServerEndTimeUTC.
                 // If not, we MUST clear pauseStartTime so tick calculation works correctly.
                 pauseStartTime = null; // Clear pause start time marker AFTER successful API call
                 runningPhase = prePausePhase || 'work'; // Determine phase to resume ('work' or 'break')
                 phase = runningPhase; // Set phase back to work/break

             } else {
                 console.warn("Resuming from pause but pauseStartTime or serverEndTimeUTC missing. Timer might be inaccurate.");
                 pauseStartTime = null; // Clear marker anyway
                 runningPhase = prePausePhase || 'work'; // Still attempt to resume phase
                 phase = runningPhase;
             }
             // --- End Resume Handling ---
        }

        prePausePhase = null; // Clear pre-pause marker

        // Update display immediately before starting interval
        tick(); // Calculate remainingSeconds based on current time and potentially adjusted serverEndTimeUTC
        updateUIDisplays(); // Display the freshly calculated time
        saveState(); // Save state *after* phase is set and time potentially adjusted

        // Start the interval
        intervalId = setInterval(tick, 1000);
        updateButtonStates(true); // Timer is running (show Pause, Reset)
        enableInputs(false); // Disable duration inputs

        elements.statusMessage.textContent = `${phase === 'work' ? 'Work' : 'Break'} session started/resumed.`;
        console.log(`Countdown started/resumed for phase: ${phase}. Expected end: ${serverEndTimeUTC || 'N/A'}`);
    }

    function pauseCountdown() {
        if (intervalId && (phase === 'work' || phase === 'break')) {
            const phaseBeforePause = phase;
            stopCountdown();
            prePausePhase = phaseBeforePause;
            phase = 'paused';
            pauseStartTime = Date.now();
            // Save state *after* setting pauseStartTime and remainingSeconds is stable
            saveState(); // Save includes remainingSeconds at the moment of pause
            updateUIDisplays();
            updateButtonStates(false);
            enableInputs(false);
            elements.statusMessage.textContent = `Timer paused during ${prePausePhase}.`;
            console.log(`Countdown paused. Phase was: ${prePausePhase}. Pause started at: ${pauseStartTime}. Remaining: ${remainingSeconds}`);
        } else {
            console.warn(`Attempted to pause when not running. Phase: ${phase}`);
        }
    }

    function stopCountdown() {
        if (intervalId) { clearInterval(intervalId); intervalId = null; console.log("Interval stopped."); }
    }

    function resetTimer(isInitialLoad = false) {
        console.log(`Resetting timer (logic). Initial load: ${isInitialLoad}`);
        const oldPhase = phase; stopCountdown();
        phase = 'idle'; prePausePhase = null; remainingSeconds = 0;
        serverEndTimeUTC = null; pauseStartTime = null;
        localStorage.removeItem(LS_KEY);

        workDurationMinutes = parseInt(elements.workInput?.value) || 25;
        breakDurationMinutes = parseInt(elements.breakInput?.value) || 5;
        const initialConfigData = window.pomodoroConfig?.initialData || {};
        currentMultiplier = initialConfigData.activeMultiplier ?? 1.0;
        totalPoints = initialConfigData.totalPoints ?? 0;
        if ('currentMultiplier' in window.PomodoroLogic) window.PomodoroLogic.currentMultiplier = currentMultiplier;
        if ('totalPoints' in window.PomodoroLogic) window.PomodoroLogic.totalPoints = totalPoints;

        if(elements.workInput) elements.workInput.value = workDurationMinutes;
        if(elements.breakInput) elements.breakInput.value = breakDurationMinutes;
        updateUIDisplays(); updateButtonStates(false); enableInputs(true);
        if (!isInitialLoad) { elements.statusMessage.textContent = 'Timer reset. Set durations and click Start.'; }
        document.title = "Pomodoro Timer";

        if (!isInitialLoad && (oldPhase === 'work' || oldPhase === 'break' || oldPhase === 'paused')) {
            console.log(`User reset active timer (was ${oldPhase}), triggering API reset.`);
            if (window.PomodoroAPI && typeof window.PomodoroAPI.sendResetSignal === 'function') {
                window.PomodoroAPI.sendResetSignal();
            } else {
                console.error("PomodoroAPI.sendResetSignal not found! Cannot reset server state.");
                elements.statusMessage.textContent += " (Error: Server state may be out of sync)";
                elements.statusMessage.classList.add('status-alert');
            }
        }
    }

    function handlePhaseCompletion() {
        const completedPhase = phase;
        if (completedPhase !== 'work' && completedPhase !== 'break') { console.error(`handlePhaseCompletion called with invalid phase: ${completedPhase}. Aborting.`); return; }
        stopCountdown(); playAlarm(); pauseStartTime = null;

        if (elements.statusMessage) { elements.statusMessage.textContent = `Completing ${completedPhase} phase...`; elements.statusMessage.classList.remove('status-alert', 'status-success'); }
        serverEndTimeUTC = null; remainingSeconds = 0;
        localStorage.removeItem(LS_KEY);

        if (completedPhase === 'work' && elements.timerDisplay) {
            elements.timerDisplay.classList.add('break-animate');
            setTimeout(() => elements.timerDisplay.classList.remove('break-animate'), 1200);
        }

        if (window.PomodoroAPI && typeof window.PomodoroAPI.sendCompleteSignal === 'function') {
             window.PomodoroAPI.sendCompleteSignal(completedPhase);
        } else {
             console.error("PomodoroAPI.sendCompleteSignal not found!");
             elements.statusMessage.textContent = "Error: Cannot contact server for completion.";
             elements.statusMessage.classList.add('status-alert');
             resetTimer(false);
        }
    }

    function updateUIDisplays() {
        if (!elements.timerDisplay) return;
        let displayPhaseLabel = 'Idle'; let multiplierContext = '(Next Session)'; let displayMultiplier = currentMultiplier;
        const phaseForDisplay = (phase === 'paused') ? prePausePhase : phase;
        switch(phaseForDisplay) { case 'work': displayPhaseLabel = 'Work'; multiplierContext = ''; break; case 'break': displayPhaseLabel = 'Break'; multiplierContext = '(Break Rate)'; displayMultiplier = 1.0; break; }
        if (phase === 'paused') { displayPhaseLabel += ' (Paused)'; multiplierContext = '(Paused)'; if (prePausePhase === 'break') displayMultiplier = 1.0; }

        elements.timerDisplay.textContent = formatTime(remainingSeconds);
        document.title = `${formatTime(remainingSeconds)} - ${displayPhaseLabel} - Pomodoro`;

        if (elements.totalPointsDisplay) {
            const currentPointsText = elements.totalPointsDisplay.textContent.replace(/,/g, ''); const currentPoints = parseInt(currentPointsText, 10);
            if (isNaN(currentPoints) || totalPoints !== currentPoints) {
                elements.totalPointsDisplay.textContent = totalPoints.toLocaleString();
                if (!isNaN(currentPoints) && currentPoints !== 0 && currentPointsText !== "") { elements.totalPointsDisplay.classList.add('points-animate'); setTimeout(() => elements.totalPointsDisplay.classList.remove('points-animate'), 600); }
            }
        }
        if (elements.activeMultiplierDisplay) {
            let multiplierHTML = `${displayMultiplier.toFixed(1)}x`; if (multiplierContext) { multiplierHTML += ` <span class="multiplier-context">${multiplierContext}</span>`; }
             elements.activeMultiplierDisplay.innerHTML = multiplierHTML;
        }
    }

    function updateButtonStates(isRunning) {
        if (!elements.startBtn || !elements.pauseBtn || !elements.resetBtn) return;
        const isIdle = (phase === 'idle'); const isPaused = (phase === 'paused');
        elements.startBtn.style.display = (isIdle || isPaused) ? 'inline-block' : 'none'; elements.startBtn.textContent = isPaused ? 'Resume' : 'Start'; elements.startBtn.disabled = !(isIdle || isPaused);
        elements.pauseBtn.style.display = (phase === 'work' || phase === 'break') ? 'inline-block' : 'none'; elements.pauseBtn.textContent = 'Pause'; elements.pauseBtn.disabled = !(phase === 'work' || phase === 'break');
        elements.resetBtn.style.display = (!isIdle) ? 'inline-block' : 'none'; elements.resetBtn.disabled = isIdle;
    }

    function enableInputs(enabled) { if(elements.workInput) elements.workInput.disabled = !enabled; if(elements.breakInput) elements.breakInput.disabled = !enabled; }

    function saveState() {
        if (phase === 'idle') { localStorage.removeItem(LS_KEY); return; }
        const state = {
            remainingSeconds: remainingSeconds, phase: phase, prePausePhase: prePausePhase,
            workDurationMinutes: workDurationMinutes, breakDurationMinutes: breakDurationMinutes,
            currentMultiplier: currentMultiplier, totalPoints: totalPoints,
            serverEndTimeUTC: serverEndTimeUTC, pauseStartTime: pauseStartTime // Save original target end time
        };
        try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (e) { console.error("Failed to save state:", e); }
    }

    // loadState uses Attempt 3 logic - remains unchanged from previous step
    function loadState(serverState, initialPoints, initialMultiplier) {
        console.log("loadState called. Server State:", serverState);
        let stateSource = 'idle_init'; totalPoints = initialPoints; currentMultiplier = initialMultiplier; let localState = null;
        try { const saved = localStorage.getItem(LS_KEY); if (saved) { localState = JSON.parse(saved); console.log("Parsed localStorage state:", localState); } } catch(e) { console.warn("Could not parse localStorage state:", e); localStorage.removeItem(LS_KEY); localState = null; }

        if (serverState && serverState.active && serverState.end_time) {
            console.log("Server reports ACTIVE state:", serverState.phase, "ending at", serverState.end_time);
            const serverTargetEndTime = serverState.end_time; let useLocalPausedState = false;
            if (localState && localState.phase === 'paused') {
                console.log("Local state indicates pause. Checking alignment...");
                if (localState.prePausePhase === serverState.phase) {
                    try {
                        const localTargetEndTimeMs = new Date(localState.serverEndTimeUTC || 0).getTime(); // Use epoch if null
                        const serverTargetEndTimeMs = new Date(serverTargetEndTime).getTime();
                        if (localTargetEndTimeMs === serverTargetEndTimeMs) {
                             if (localState.pauseStartTime && typeof localState.remainingSeconds === 'number' && localState.remainingSeconds >= 0) { console.log("Local paused state appears valid and aligned with server."); useLocalPausedState = true; }
                             else { console.warn("Local paused state aligned on phase/end time but missing pauseStartTime or valid remainingSeconds."); }
                        } else { console.warn("Local paused state has DIFFERENT target end time than server. Ignoring local pause state."); }
                    } catch (dateError) { console.error("Error parsing end time dates for alignment check:", dateError); }
                } else { console.warn("Local paused state prePausePhase doesn't match server's active phase. Ignoring local pause state."); }
            }

            if (useLocalPausedState) {
                console.log("Restoring PAUSED state from aligned localStorage."); stateSource = 'local_paused_sync';
                phase = 'paused'; prePausePhase = localState.prePausePhase;
                workDurationMinutes = localState.workDurationMinutes || serverState.work_duration_minutes || workDurationMinutes;
                breakDurationMinutes = localState.breakDurationMinutes || serverState.break_duration_minutes || breakDurationMinutes;
                currentMultiplier = localState.currentMultiplier || serverState.current_multiplier || currentMultiplier;
                remainingSeconds = localState.remainingSeconds; pauseStartTime = localState.pauseStartTime;
                serverEndTimeUTC = localState.serverEndTimeUTC; // Use the matching end time
            } else {
                 if (localState && localState.phase === 'paused') { console.warn(`Server active (${serverState.phase}), but ignoring misaligned/invalid local PAUSED state. Forcing pause now.`); }
                 else { console.warn(`Server active (${serverState.phase}), but no valid PAUSED state found locally. Forcing pause now.`); }
                stateSource = 'server_forced_pause';
                phase = serverState.phase; workDurationMinutes = serverState.work_duration_minutes || workDurationMinutes;
                breakDurationMinutes = serverState.break_duration_minutes || breakDurationMinutes; currentMultiplier = serverState.current_multiplier || currentMultiplier;
                serverEndTimeUTC = serverTargetEndTime;
                const now = Date.now(); const endTimeMs = new Date(serverEndTimeUTC).getTime();
                remainingSeconds = Math.max(0, Math.floor((endTimeMs - now) / 1000));
                console.log(`Calculated remaining seconds for forced pause: ${remainingSeconds}s`);
                prePausePhase = phase; phase = 'paused'; pauseStartTime = Date.now();
                localStorage.removeItem(LS_KEY); saveState();
            }
        } else {
             if (serverState && serverState.active && !serverState.end_time) { console.error("Server state reported active but missing end_time! Resetting client to idle."); }
             else if (serverState && !serverState.active) { console.log("Server reports INACTIVE state. Ensuring client is idle."); }
             else { console.log("No valid active server state found (or fetch failed). Ensuring client is idle."); }
             stateSource = 'idle_server_inactive_or_error';
             localStorage.removeItem(LS_KEY); phase = 'idle'; prePausePhase = null; remainingSeconds = 0;
             serverEndTimeUTC = null; pauseStartTime = null;
        }

        window.PomodoroLogic.currentMultiplier = currentMultiplier; window.PomodoroLogic.totalPoints = totalPoints;
        if(elements.workInput) elements.workInput.value = (phase === 'idle') ? (parseInt(elements.workInput.value) || 25) : workDurationMinutes;
        if(elements.breakInput) elements.breakInput.value = (phase === 'idle') ? (parseInt(elements.breakInput.value) || 5) : breakDurationMinutes;
        updateUIDisplays();

        if (phase === 'paused') { updateButtonStates(false); enableInputs(false); elements.statusMessage.textContent = `Loaded paused ${prePausePhase || '?'} session. Press Resume.`; }
        else if (phase === 'idle') { updateButtonStates(false); enableInputs(true); if (!elements.statusMessage.textContent.startsWith("Error")) { elements.statusMessage.textContent = 'Set durations and click Start.'; } }
        else { console.error("State loaded into unexpected final running phase:", phase, "Attempting recovery reset."); resetTimer(true); }
        console.log(`Logic state loaded. Final phase: ${phase}, Source: ${stateSource}`);
    }


    // --- Public Methods & Properties ---
    return {
        currentMultiplier: currentMultiplier, totalPoints: totalPoints, // Exposed state
        init: function(domElements, serverState, initialConfigData) { // Methods
             console.log("Initializing Pomodoro Logic..."); elements = domElements;
             const initialPoints = initialConfigData?.totalPoints ?? 0; const initialMultiplier = initialConfigData?.activeMultiplier ?? 1.0;
             workDurationMinutes = parseInt(elements.workInput?.value) || 25; breakDurationMinutes = parseInt(elements.breakInput?.value) || 5;
             loadState(serverState, initialPoints, initialMultiplier); console.log("Pomodoro Logic Initialized.");
        },
        startCountdown: startCountdown, pauseCountdown: pauseCountdown, resetTimer: resetTimer,
        setPhase: function(newPhase) { phase = newPhase; }, // State setters
        setPrePausePhase: function(newPrePause) { prePausePhase = newPrePause; },
        setServerEndTimeUTC: function(newTime) { serverEndTimeUTC = newTime; },
        setRemainingSeconds: function(seconds) { remainingSeconds = seconds; },
        setTotalPoints: function(points) { totalPoints = points; window.PomodoroLogic.totalPoints = points; updateUIDisplays(); },
        setCurrentMultiplier: function(multiplier) { currentMultiplier = multiplier; window.PomodoroLogic.currentMultiplier = multiplier; updateUIDisplays(); },
        setWorkDuration: function(duration) { workDurationMinutes = duration; }, setBreakDuration: function(duration) { breakDurationMinutes = duration; },
        getPhase: function() { return phase; }, // Getters
        getWorkDuration: function() { return workDurationMinutes; }, getBreakDuration: function() { return breakDurationMinutes; },
        updateUIDisplays: updateUIDisplays, updateButtonStates: updateButtonStates, enableInputs: enableInputs // UI Updaters
    };

})(); // End of IIFE wrapper   