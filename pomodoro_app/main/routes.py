# pomodoro_app/main/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta  # Import datetime components

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
#     1: {'phase': 'work', 'end_time': datetime_obj, 'break_duration_minutes': 5},
#     2: {'phase': 'break', 'end_time': datetime_obj, 'break_duration_minutes': 10}
# }
# --------------------------------------

@main.route('/')
@limiter.limit("10 per minute")
def index():
    if current_user.is_authenticated:
        # Check if this user has an active timer state on the server
        # If so, redirect to timer, otherwise dashboard.
        # (Optional: could also pass state to dashboard)
        if current_user.id in active_timers:
             return redirect(url_for('main.timer'))
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    # Optionally pass existing server state to the template if needed for initial render
    # server_state = active_timers.get(current_user.id)
    # return render_template('main/timer.html', server_state=server_state)
    return render_template('main/timer.html')


# --- NEW/MODIFIED API Endpoints ---

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
    now = datetime.utcnow()
    end_time = now + timedelta(minutes=work_minutes)

    # Store server-side state
    active_timers[user_id] = {
        'phase': 'work',
        'end_time': end_time,
        'start_time': now, # Store start time for accurate logging
        'work_duration_minutes': work_minutes, # Store original duration
        'break_duration_minutes': break_minutes
    }

    print(f"TIMER DEBUG: User {user_id} started timer. State: {active_timers[user_id]}") # For debugging
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

    if user_id not in active_timers:
        # Might happen if server restarted or client is out of sync
        print(f"TIMER DEBUG: User {user_id} completed phase '{phase_completed}', but no active timer found.")
        # Decide how to handle: maybe just accept it, maybe return error
        # Let's try to log if it was work, otherwise ignore.
        if phase_completed == 'work':
             # We don't have exact duration without server state, log with placeholder? Or ignore?
             # For now, let's just return success without logging/state change
             return jsonify({'status': 'acknowledged_no_state'}), 200
        else:
             return jsonify({'status': 'acknowledged_no_state'}), 200


    # --- State exists, proceed ---
    server_state = active_timers[user_id]
    now = datetime.utcnow()

    # Sanity check: does completed phase match server state?
    if server_state['phase'] != phase_completed:
         print(f"TIMER DEBUG: Phase mismatch for User {user_id}. Client says '{phase_completed}' done, server state is '{server_state['phase']}'.")
         # Decide: Trust client? Return error? For now, trust client and proceed.
         pass # Continue processing based on client report

    if phase_completed == 'work':
        print(f"TIMER DEBUG: User {user_id} completed WORK phase.")
        # --- Log the completed Work Session ---
        # Use stored durations for accuracy, calculate elapsed if needed
        # For simplicity, using the originally intended durations here.
        try:
            work_duration = server_state.get('work_duration_minutes', int(data.get('actual_work_duration', 0))) # Use actual if sent, else fallback
            break_duration = server_state.get('break_duration_minutes', 0)
            new_session = PomodoroSession(
                user_id=user_id,
                work_duration=work_duration,
                break_duration=break_duration, # Storing intended break duration here
                timestamp=server_state.get('start_time', now) # Use server start time if available
            )
            db.session.add(new_session)
            db.session.commit()
            print(f"TIMER DEBUG: User {user_id} logged work session.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR: Failed to log session for user {user_id}: {e}")
            # Decide if this should halt the process or just log error

        # --- Update server state to Break ---
        break_minutes = server_state['break_duration_minutes']
        break_end_time = now + timedelta(minutes=break_minutes)
        active_timers[user_id]['phase'] = 'break'
        active_timers[user_id]['end_time'] = break_end_time
        active_timers[user_id]['start_time'] = now # Reset start time for the break phase
        print(f"TIMER DEBUG: User {user_id} transitioning to BREAK phase. State: {active_timers[user_id]}")

        return jsonify({'status': 'break_started'}), 200

    elif phase_completed == 'break':
        print(f"TIMER DEBUG: User {user_id} completed BREAK phase. Session complete.")
        # --- Clear server state ---
        del active_timers[user_id]
        return jsonify({'status': 'session_complete'}), 200

    else:
        return jsonify({'error': 'Invalid phase specified'}), 400

# --- End of NEW/MODIFIED API Endpoints ---


# Keep original dashboard route (it doesn't need timer state directly)
@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    sessions = PomodoroSession.query.filter_by(user_id=current_user.id).order_by(PomodoroSession.timestamp.desc()).all()
    total_focus = sum(sess.work_duration for sess in sessions)
    total_break = sum(sess.break_duration for sess in sessions) # Note: this uses intended break time stored during work log
    total_sessions = PomodoroSession.query.filter(PomodoroSession.user_id == current_user.id, PomodoroSession.work_duration > 0).count() # Count only work sessions
    return render_template('main/dashboard.html',
                           total_focus=total_focus, total_break=total_break, total_sessions=total_sessions,
                           sessions=sessions)


# --- Example function for AI context (Optional) ---
def get_timer_status_for_user(user_id):
    """Helper function to get current timer status based on server state."""
    if user_id in active_timers:
        state = active_timers[user_id]
        now = datetime.utcnow()
        remaining_seconds = (state['end_time'] - now).total_seconds()
        return {
            'status': 'active',
            'phase': state['phase'],
            'remaining_seconds': max(0, remaining_seconds), # Don't return negative
            'server_end_time': state['end_time'].isoformat() # Optional: return exact end time
        }
    else:
        return {'status': 'inactive'}

# Example usage (e.g., in an AI query route):
# @main.route('/api/ai/ask', methods=['POST'])
# @login_required
# def ask_ai():
#     user_prompt = request.json.get('prompt')
#     user_id = current_user.id
#     timer_context = get_timer_status_for_user(user_id)
#     # ... format prompt for OpenAI including timer_context ...
#     # ... call OpenAI ...
#     # ... return response ...