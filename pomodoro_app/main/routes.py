# pomodoro_app/main/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone # *** Ensure timezone is imported ***

from pomodoro_app import db, limiter
from pomodoro_app.models import PomodoroSession

main = Blueprint('main', __name__)

# --- Server-Side Timer State Storage ---
# Simple in-memory dictionary for active timers.
# Key: user_id, Value: dictionary with timer details
# IMPORTANT: This is NOT persistent across server restarts and won't work
#            correctly with multiple server processes/workers.
#            For production, use Redis or a similar shared store.
active_timers = {}
# Example structure:
# active_timers = {
#     1: {'phase': 'work', 'start_time': utc_dt, 'end_time': utc_dt, 'work_duration_minutes': 25, 'break_duration_minutes': 5},
# }
# --------------------------------------

@main.route('/')
@limiter.limit("10 per minute")
def index():
    if current_user.is_authenticated:
        if current_user.id in active_timers:
             return redirect(url_for('main.timer'))
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    return render_template('main/timer.html')


# --- API Endpoints ---

@main.route('/api/timer/start', methods=['POST'])
@login_required
@limiter.limit("15 per minute") # Allow slightly more starts/updates
def api_start_timer():
    """API endpoint for the client to signal the start of a timer."""
    data = request.get_json()
    if not data or 'work' not in data or 'break' not in data:
        return jsonify({'error': 'Missing work or break duration'}), 400

    try:
        work_minutes = int(data['work'])
        break_minutes = int(data['break'])
        if work_minutes <= 0 or break_minutes <= 0:
            raise ValueError("Durations must be positive.")
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid duration values'}), 400

    user_id = current_user.id
    # Ensure we are using UTC for server-side calculations
    now_utc = datetime.now(timezone.utc)
    end_time_utc = now_utc + timedelta(minutes=work_minutes)

    # Store server-side state
    active_timers[user_id] = {
        'phase': 'work',
        'end_time': end_time_utc,
        'start_time': now_utc, # Store start time for accurate logging
        'work_duration_minutes': work_minutes, # Store original duration
        'break_duration_minutes': break_minutes
    }

    # Keep this debug log if you find it helpful, or remove it
    print(f"TIMER DEBUG (Start): User {user_id} starting timer. Server state: {active_timers[user_id]}")
    return jsonify({'status': 'timer_started'}), 200


@main.route('/api/timer/complete_phase', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_complete_phase():
    """API endpoint for the client to signal the completion of a phase (work/break)."""
    data = request.get_json()
    if not data or 'phase_completed' not in data:
        return jsonify({'error': 'Missing phase_completed field'}), 400

    phase_completed = data.get('phase_completed')
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc) # Use UTC for comparisons and new timestamps

    if user_id not in active_timers:
        # Optional: Keep this logging if helpful
        print(f"TIMER DEBUG (Complete): User {user_id} completed phase '{phase_completed}', but NO active server timer found.")
        # Log work session even if server state is missing, using client data if needed (less accurate)
        if phase_completed == 'work':
            try:
                # Attempt to get duration from request if possible, otherwise use a default or 0
                work_duration = int(data.get('work_duration', 0)) # Example: client might send duration
                break_duration = int(data.get('break_duration', 0)) # Example
                print(f"TIMER DEBUG (Complete/No State): Attempting to log work session for user {user_id} without server state.")
                new_session = PomodoroSession(
                    user_id=user_id,
                    work_duration=work_duration,
                    break_duration=break_duration,
                    timestamp=now_utc # Log with current UTC time as best guess
                )
                db.session.add(new_session)
                db.session.commit()
                print(f"TIMER DEBUG (Complete/No State): Logged session {new_session.id} for user {user_id}.")
                return jsonify({'status': 'acknowledged_logged_no_state'}), 200
            except Exception as e:
                db.session.rollback()
                print(f"ERROR (Complete/No State): Failed to log session for user {user_id}: {e}")
                return jsonify({'status': 'acknowledged_log_failed_no_state'}), 200
        else:
             return jsonify({'status': 'acknowledged_no_state'}), 200


    # --- State exists, proceed ---
    server_state = active_timers[user_id]

    # Optional Sanity check: does completed phase match server state?
    if server_state['phase'] != phase_completed:
         # Optional: Keep this logging if helpful
         print(f"TIMER DEBUG (Complete): Phase mismatch for User {user_id}. Client says '{phase_completed}' done, server state is '{server_state['phase']}'. Trusting client.")
         # Decide: Trust client? Return error? For now, trust client and proceed.

    if phase_completed == 'work':
        # Optional: Keep logging if helpful
        print(f"TIMER DEBUG (Complete): User {user_id} completed WORK phase.")
        # --- Log the completed Work Session ---
        try:
            # Use durations stored in server state for accuracy
            work_duration = server_state.get('work_duration_minutes')
            break_duration = server_state.get('break_duration_minutes')
            start_time = server_state.get('start_time', now_utc) # Use server start time if available

            # *** Use the start_time which should be UTC aware from server_state ***
            new_session = PomodoroSession(
                user_id=user_id,
                work_duration=work_duration,
                break_duration=break_duration,
                timestamp=start_time # Use the recorded start time of the work phase
            )
            db.session.add(new_session)
            db.session.commit()
            # Optional: Keep logging if helpful
            print(f"TIMER DEBUG (Complete): User {user_id} logged work session {new_session.id}.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR (Complete): Failed to log session for user {user_id}: {e}")
            # Decide if this should halt the process or just log error

        # --- Update server state to Break ---
        break_minutes = server_state['break_duration_minutes']
        break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
        active_timers[user_id]['phase'] = 'break'
        active_timers[user_id]['end_time'] = break_end_time_utc
        active_timers[user_id]['start_time'] = now_utc # Reset start time for the break phase
        # Optional: Keep logging if helpful
        print(f"TIMER DEBUG (Complete): User {user_id} transitioning to BREAK phase. Server state: {active_timers[user_id]}")

        return jsonify({'status': 'break_started'}), 200

    elif phase_completed == 'break':
        # Optional: Keep logging if helpful
        print(f"TIMER DEBUG (Complete): User {user_id} completed BREAK phase. Session complete.")
        # --- Clear server state ---
        if user_id in active_timers: # Check again before deleting
            del active_timers[user_id]
            # Optional: Keep logging if helpful
            print(f"TIMER DEBUG (Complete): Cleared server state for user {user_id}.")
        return jsonify({'status': 'session_complete'}), 200

    else:
        # Optional: Keep logging if helpful
        print(f"TIMER DEBUG (Complete): User {user_id} sent invalid phase '{phase_completed}'.")
        return jsonify({'error': 'Invalid phase specified'}), 400

# --- End of API Endpoints ---


@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    """Displays user dashboard with session history and stats."""
    # 1. Query the database as before
    sessions_from_db = PomodoroSession.query.filter_by(user_id=current_user.id).order_by(PomodoroSession.timestamp.desc()).all()

    # ---- FIX: Make timestamps timezone-aware (assuming UTC) for SQLite ----
    # This step ensures timestamps from the DB (which are naive for SQLite)
    # are made UTC-aware before being passed to the template.
    aware_sessions = []
    for sess in sessions_from_db:
        if sess.timestamp and getattr(sess.timestamp, 'tzinfo', None) is None:
            # If timestamp exists and is naive, replace it with an aware version (attach UTC info)
            try:
                # This crucial step adds the UTC timezone info without changing the time value
                sess.timestamp = sess.timestamp.replace(tzinfo=timezone.utc)
            except Exception as e:
                # Log error if replace fails, but it's unlikely for standard datetimes
                print(f"ERROR: Could not make timestamp aware for session {sess.id}: {e}")
                # In case of error, we pass the session with the naive timestamp
        aware_sessions.append(sess)
    # -----------------------------------------------------------------------

    # 2. Perform calculations using the list that now contains aware timestamps
    total_focus = sum(sess.work_duration for sess in aware_sessions)
    total_break = sum(sess.break_duration for sess in aware_sessions)
    total_sessions = PomodoroSession.query.filter(PomodoroSession.user_id == current_user.id, PomodoroSession.work_duration > 0).count() # Count doesn't need aware times

    # 3. Pass the list with *aware* timestamps to the template.
    #    Jinja's {{ sess.timestamp.isoformat() }} will now include the UTC offset.
    return render_template('main/dashboard.html',
                           total_focus=total_focus,
                           total_break=total_break,
                           total_sessions=total_sessions,
                           sessions=aware_sessions) # Use the processed list


# Helper function example (unmodified)
def get_timer_status_for_user(user_id):
    """Helper function to get current timer status based on server state."""
    if user_id in active_timers:
        state = active_timers[user_id]
        now_utc = datetime.now(timezone.utc)
        remaining_seconds = (state['end_time'] - now_utc).total_seconds()
        return {
            'status': 'active',
            'phase': state['phase'],
            'remaining_seconds': max(0, remaining_seconds), # Don't return negative
            'server_end_time_utc': state['end_time'].isoformat()
        }
    else:
        return {'status': 'inactive'}