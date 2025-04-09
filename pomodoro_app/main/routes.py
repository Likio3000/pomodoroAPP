# pomodoro_app/main/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from flask_login import login_required, current_user
# *** Make sure timedelta is imported ***
from datetime import datetime, timedelta, timezone
import os
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# *** Import func for aggregation (optional but cleaner) ***
from sqlalchemy import func, text # Added text for potential raw SQL if needed, func is primary

from pomodoro_app import db, limiter
from pomodoro_app.models import PomodoroSession

main = Blueprint('main', __name__)

# --- Server-Side Timer State Storage ---
# Simple in-memory dictionary for active timers.
# IMPORTANT: This is NOT persistent across server restarts and won't work
#            correctly with multiple server processes/workers.
#            For production, use Redis or a similar shared store.
active_timers = {}
# Example structure:
# active_timers = {
#     1: {'phase': 'work', 'start_time': utc_dt, 'end_time': utc_dt, 'work_duration_minutes': 25, 'break_duration_minutes': 5},
# }
# --------------------------------------

# --- OpenAI Client Initialization ---
# It's generally safe to initialize the client once if the API key is set
# Make sure OPENAI_API_KEY is loaded into the environment where Flask runs
openai_client = None
if OpenAI and os.getenv("OPENAI_API_KEY"):
    try:
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print("OpenAI client initialized.")
    except Exception as e:
        print(f"Warning: Failed to initialize OpenAI client: {e}")
        openai_client = None # Ensure it's None if init fails
else:
    if not OpenAI:
         print("Warning: OpenAI library not found. Chat agent will be disabled.")
    if not os.getenv("OPENAI_API_KEY"):
         print("Warning: OPENAI_API_KEY environment variable not set. Chat agent will be disabled.")


# --- Routes ---

@main.route('/')
@limiter.limit("10 per minute")
def index():
    if current_user.is_authenticated:
        # Check server-side state first (more reliable if implemented robustly)
        if current_user.id in active_timers:
             return redirect(url_for('main.timer'))
        # Could add a check here for client-side state via a cookie or API call if needed
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    # Optionally pass existing timer state if needed by template initially
    # user_timer_state = active_timers.get(current_user.id)
    return render_template('main/timer.html') #, timer_state=user_timer_state)


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

    # Store server-side state (replace with Redis/DB in production)
    active_timers[user_id] = {
        'phase': 'work',
        'end_time': end_time_utc,
        'start_time': now_utc, # Store start time for accurate logging
        'work_duration_minutes': work_minutes, # Store original duration
        'break_duration_minutes': break_minutes
    }

    # Optional debug log
    # print(f"TIMER DEBUG (Start): User {user_id} starting timer. Server state: {active_timers.get(user_id)}")
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
        # print(f"TIMER DEBUG (Complete): User {user_id} completed phase '{phase_completed}', but NO active server timer found.")
        # Log work session even if server state is missing, using client data if needed (less accurate)
        if phase_completed == 'work':
            try:
                # Attempt to get duration from request if possible, otherwise use a default or 0
                work_duration = int(data.get('work_duration', 0)) # Example: client might send duration
                break_duration = int(data.get('break_duration', 0)) # Example
                # print(f"TIMER DEBUG (Complete/No State): Attempting to log work session for user {user_id} without server state.")
                new_session = PomodoroSession(
                    user_id=user_id,
                    work_duration=work_duration,
                    break_duration=break_duration,
                    timestamp=now_utc # Log with current UTC time as best guess
                )
                db.session.add(new_session)
                db.session.commit()
                # print(f"TIMER DEBUG (Complete/No State): Logged session {new_session.id} for user {user_id}.")
                return jsonify({'status': 'acknowledged_logged_no_state'}), 200
            except Exception as e:
                db.session.rollback()
                print(f"ERROR (Complete/No State): Failed to log session for user {user_id}: {e}")
                return jsonify({'status': 'acknowledged_log_failed_no_state'}), 200
        else:
             # If break completes without state, just acknowledge
             return jsonify({'status': 'acknowledged_no_state'}), 200

    # --- State exists, proceed ---
    server_state = active_timers[user_id]

    # Optional Sanity check: does completed phase match server state?
    if server_state.get('phase') != phase_completed:
         # Optional: Keep this logging if helpful
         # print(f"TIMER DEBUG (Complete): Phase mismatch for User {user_id}. Client says '{phase_completed}' done, server state is '{server_state.get('phase', 'unknown')}'. Trusting client.")
         pass # Decide: Trust client? Return error? For now, trust client and proceed.

    if phase_completed == 'work':
        # Optional: Keep logging if helpful
        # print(f"TIMER DEBUG (Complete): User {user_id} completed WORK phase.")
        # --- Log the completed Work Session ---
        try:
            # Use durations stored in server state for accuracy
            work_duration = server_state.get('work_duration_minutes', 0) # Default to 0 if missing
            break_duration = server_state.get('break_duration_minutes', 0) # Default to 0 if missing
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
            # print(f"TIMER DEBUG (Complete): User {user_id} logged work session {new_session.id}.")
        except Exception as e:
            db.session.rollback()
            print(f"ERROR (Complete): Failed to log session for user {user_id}: {e}")
            # Decide if this should halt the process or just log error

        # --- Update server state to Break ---
        break_minutes = server_state.get('break_duration_minutes', 5) # Default if missing
        break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
        active_timers[user_id]['phase'] = 'break'
        active_timers[user_id]['end_time'] = break_end_time_utc
        active_timers[user_id]['start_time'] = now_utc # Reset start time for the break phase
        # Optional: Keep logging if helpful
        # print(f"TIMER DEBUG (Complete): User {user_id} transitioning to BREAK phase. Server state: {active_timers.get(user_id)}")

        return jsonify({'status': 'break_started'}), 200

    elif phase_completed == 'break':
        # Optional: Keep logging if helpful
        # print(f"TIMER DEBUG (Complete): User {user_id} completed BREAK phase. Session complete.")
        # --- Clear server state ---
        if user_id in active_timers: # Check again before deleting
            del active_timers[user_id]
            # Optional: Keep logging if helpful
            # print(f"TIMER DEBUG (Complete): Cleared server state for user {user_id}.")
        return jsonify({'status': 'session_complete'}), 200

    else:
        # Optional: Keep logging if helpful
        # print(f"TIMER DEBUG (Complete): User {user_id} sent invalid phase '{phase_completed}'.")
        return jsonify({'error': 'Invalid phase specified'}), 400


# +++ Updated API Endpoint for Chat +++
@main.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute") # Limit chat requests
def api_chat():
    if not openai_client:
        return jsonify({'error': 'Chat feature is not configured or OpenAI key is missing.'}), 501 # 501 Not Implemented

    data = request.get_json()
    if not data or 'prompt' not in data or 'dashboard_data' not in data:
        return jsonify({'error': 'Missing prompt or dashboard_data in request'}), 400

    user_prompt = data.get('prompt')
    dashboard_data = data.get('dashboard_data', {}) # e.g., {'total_focus': 120, ...}

    # --- *** CONSTRUCT ENHANCED CONTEXT FOR AI *** ---
    context = f"""
    You are a helpful productivity assistant integrated into a Pomodoro timer web app.
    The user '{current_user.name}' (ID: {current_user.id}) you are talking to has the following Pomodoro statistics:

    Overall Stats:
    - Total Focused Time: {dashboard_data.get('total_focus', 'N/A')} minutes
    - Total Break Time: {dashboard_data.get('total_break', 'N/A')} minutes
    - Completed Pomodoro Sessions (Overall): {dashboard_data.get('total_sessions', 'N/A')}

    Today's Stats (UTC):
    - Focused Time Today: {dashboard_data.get('today_focus', 'N/A')} minutes
    - Sessions Today: {dashboard_data.get('today_sessions', 'N/A')}

    This Week's Stats (UTC, starting Monday):
    - Focused Time This Week: {dashboard_data.get('week_focus', 'N/A')} minutes
    - Sessions This Week: {dashboard_data.get('week_sessions', 'N/A')}

    Answer the user's question based on this context and general productivity knowledge. Be encouraging and helpful. Keep responses concise.
    """
    # --- *** END OF ENHANCED CONTEXT *** ---

    try:
        # Use the Chat Completions endpoint
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": context,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            model="gpt-4o-mini", # Or your preferred model
            max_tokens=200, # Increased slightly for more context
            temperature=0.7, # Adjust creativity vs factualness
        )

        # Extract the response text
        ai_response = chat_completion.choices[0].message.content.strip()

        return jsonify({'response': ai_response})

    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        # Avoid leaking detailed internal errors to the client unless necessary for debugging
        # Consider logging the full error server-side and returning a generic message
        return jsonify({'error': f'Sorry, I encountered an issue processing your request.'}), 500

# --- End of API Endpoints ---


# +++ Updated Dashboard Route +++
@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    """Displays user dashboard with session history and stats."""
    user_id = current_user.id

    # --- Overall Stats ---
    # Use func.sum for database-level aggregation, coalesce ensures 0 if no sessions
    total_focus_query = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter_by(user_id=user_id)
    total_break_query = db.session.query(func.coalesce(func.sum(PomodoroSession.break_duration), 0)).filter_by(user_id=user_id)
    total_sessions_query = db.session.query(func.count(PomodoroSession.id)).filter(
        PomodoroSession.user_id == user_id,
        PomodoroSession.work_duration > 0 # Only count sessions with focus time
    )

    total_focus = total_focus_query.scalar()
    total_break = total_break_query.scalar()
    total_sessions = total_sessions_query.scalar()

    # --- Time-based Stats (Using UTC) ---
    now_utc = datetime.now(timezone.utc)
    today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    # Assuming Monday is the start of the week (weekday() == 0)
    start_of_week_utc = today_start_utc - timedelta(days=now_utc.weekday())

    # Today's Stats
    today_focus_query = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(
        PomodoroSession.user_id == user_id,
        PomodoroSession.timestamp >= today_start_utc
    )
    today_sessions_query = db.session.query(func.count(PomodoroSession.id)).filter(
        PomodoroSession.user_id == user_id,
        PomodoroSession.work_duration > 0,
        PomodoroSession.timestamp >= today_start_utc
    )
    today_focus = today_focus_query.scalar()
    today_sessions = today_sessions_query.scalar()

    # This Week's Stats
    week_focus_query = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(
        PomodoroSession.user_id == user_id,
        PomodoroSession.timestamp >= start_of_week_utc
    )
    week_sessions_query = db.session.query(func.count(PomodoroSession.id)).filter(
        PomodoroSession.user_id == user_id,
        PomodoroSession.work_duration > 0,
        PomodoroSession.timestamp >= start_of_week_utc
    )
    week_focus = week_focus_query.scalar()
    week_sessions = week_sessions_query.scalar()

    # --- Fetch Session History (with timezone fix from before) ---
    # Limiting the history fetched can improve performance if list becomes huge
    # sessions_from_db = PomodoroSession.query.filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).limit(100).all() # Example limit
    sessions_from_db = PomodoroSession.query.filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).all()

    aware_sessions = []
    for sess in sessions_from_db:
        if sess.timestamp and getattr(sess.timestamp, 'tzinfo', None) is None:
            # Apply timezone only if it's naive (likely from SQLite)
            try:
                sess.timestamp = sess.timestamp.replace(tzinfo=timezone.utc)
            except Exception as e:
                # Log error if replace fails
                print(f"ERROR: Could not make timestamp aware for session {sess.id}: {e}")
                # Pass the session with the naive timestamp anyway
        aware_sessions.append(sess)

    # Pass the flag indicating if chat is enabled
    chat_enabled = bool(openai_client)

    # 3. Pass all stats and session list to the template.
    return render_template('main/dashboard.html',
                           # Overall
                           total_focus=total_focus,
                           total_break=total_break,
                           total_sessions=total_sessions,
                           # Today
                           today_focus=today_focus,
                           today_sessions=today_sessions,
                           # Week
                           week_focus=week_focus,
                           week_sessions=week_sessions,
                           # History & Config
                           sessions=aware_sessions, # Use the processed list
                           chat_enabled=chat_enabled) # Pass the flag


# Helper function example (not actively used by routes above but kept for reference)
def get_timer_status_for_user(user_id):
    """Helper function to get current timer status based on server state."""
    if user_id in active_timers:
        state = active_timers[user_id]
        now_utc = datetime.now(timezone.utc)
        # Ensure end_time exists and is a datetime before comparison
        if 'end_time' in state and isinstance(state['end_time'], datetime):
             remaining_seconds = (state['end_time'] - now_utc).total_seconds()
        else:
             remaining_seconds = -1 # Indicate an issue or unknown state
             print(f"Warning: Invalid or missing 'end_time' in active_timers for user {user_id}")

        return {
            'status': 'active',
            'phase': state.get('phase', 'unknown'),
            'remaining_seconds': max(0, remaining_seconds) if remaining_seconds >= 0 else 0,
            'server_end_time_utc': state['end_time'].isoformat() if 'end_time' in state and isinstance(state['end_time'], datetime) else None
        }
    else:
        return {'status': 'inactive'}