# pomodoro_app/main/routes.py
from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
import os
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None # Flag that OpenAI library is not installed

# Import database functions and specific exceptions
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

# Import database instance, limiter, and models
from pomodoro_app import db, limiter
from pomodoro_app.models import PomodoroSession, ActiveTimerState, User # Make sure User is imported if needed

main = Blueprint('main', __name__)

# --- OpenAI Client Initialization ---
# Initialize based on environment variable presence, checked later via config flag
openai_client = None
openai_api_key = os.getenv("OPENAI_API_KEY")
if OpenAI and openai_api_key:
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        # Cannot use logger here reliably as app context might not exist yet
        # Logging about OpenAI init status is done in create_app
    except Exception as e:
        print(f"WARNING: Failed to initialize OpenAI client during module load: {e}") # Print warning if init fails early
        openai_client = None
# else: # No warning needed here if lib/key missing, handled by config flag

# --- Routes ---

@main.route('/')
@limiter.limit("10 per minute")
def index():
    """Handles the root URL. Redirects authenticated users."""
    if current_user.is_authenticated:
        try:
            # Check DB for active timer state using primary key lookup (efficient)
            active_state = db.session.get(ActiveTimerState, current_user.id)
            if active_state:
                 current_app.logger.debug(f"User {current_user.id} has active timer state in DB, redirecting to timer page.")
                 return redirect(url_for('main.timer'))
            else:
                 current_app.logger.debug(f"User {current_user.id} has no active timer state, redirecting to dashboard.")
                 return redirect(url_for('main.dashboard'))
        except SQLAlchemyError as e:
             current_app.logger.error(f"Database error checking active timer for user {current_user.id} on index: {e}", exc_info=True)
             # Fallback: Redirect to dashboard even if DB check failed
             return redirect(url_for('main.dashboard'))
        except Exception as e:
             current_app.logger.error(f"Unexpected error checking active timer for user {current_user.id} on index: {e}", exc_info=True)
             return redirect(url_for('main.dashboard')) # Fallback
    # Unauthenticated users see the landing page
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    """Displays the timer page."""
    # Client-side JS handles loading its state from localStorage.
    # Server only needs to know the current active state via API calls.
    return render_template('main/timer.html')

# --- API Endpoints ---

@main.route('/api/timer/start', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_start_timer():
    """API endpoint for the client to signal the start/restart of a timer."""
    data = request.get_json()
    if not data or 'work' not in data or 'break' not in data:
        current_app.logger.warning(f"API Start: Bad request from User {current_user.id}. Missing work/break data.")
        return jsonify({'error': 'Missing work or break duration'}), 400

    try:
        work_minutes = int(data['work'])
        break_minutes = int(data['break'])
        if work_minutes <= 0 or break_minutes <= 0:
            raise ValueError("Durations must be positive.")
    except (ValueError, TypeError):
        current_app.logger.warning(f"API Start: Bad request from User {current_user.id}. Invalid duration values: {data}")
        return jsonify({'error': 'Invalid duration values'}), 400

    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)
    end_time_utc = now_utc + timedelta(minutes=work_minutes)

    try:
        # Efficiently check and update/insert using session.get (if PK is user_id)
        current_state = db.session.get(ActiveTimerState, user_id)

        if current_state:
            # Update existing state
            current_app.logger.info(f"API Start: Updating existing timer state for User {user_id}.")
            current_state.phase = 'work'
            current_state.start_time = now_utc
            current_state.end_time = end_time_utc
            current_state.work_duration_minutes = work_minutes
            current_state.break_duration_minutes = break_minutes
        else:
            # Create new state
            current_app.logger.info(f"API Start: Creating new timer state for User {user_id}.")
            new_state = ActiveTimerState(
                user_id=user_id,
                phase='work',
                start_time=now_utc,
                end_time=end_time_utc,
                work_duration_minutes=work_minutes,
                break_duration_minutes=break_minutes
            )
            db.session.add(new_state)

        db.session.commit() # Commit the change (update or insert)
        current_app.logger.debug(f"API Start: Timer state saved for User {user_id}. Phase: work, Ends: {end_time_utc.isoformat()}")
        return jsonify({'status': 'timer_started'}), 200

    except SQLAlchemyError as e:
        db.session.rollback() # Rollback on DB errors
        current_app.logger.error(f"API Start: Database error saving timer state for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred saving timer state.'}), 500
    except Exception as e:
        db.session.rollback() # Rollback on any other unexpected errors
        current_app.logger.error(f"API Start: Unexpected error saving timer state for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred.'}), 500


@main.route('/api/timer/complete_phase', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_complete_phase():
    """API endpoint for the client to signal the completion of a phase (work/break)."""
    data = request.get_json()
    if not data or 'phase_completed' not in data:
         current_app.logger.warning(f"API Complete: Bad request from User {current_user.id}. Missing phase_completed field.")
         return jsonify({'error': 'Missing phase_completed field'}), 400

    phase_completed = data.get('phase_completed')
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)

    try:
        # Get current timer state from DB
        server_state = db.session.get(ActiveTimerState, user_id)

        if not server_state:
            # If the client thinks a phase completed but the server has no state,
            # it might be due to a server restart or client/server desync.
            # Avoid logging a session here to prevent potential duplicates.
            current_app.logger.warning(f"API Complete: User {user_id} reported phase '{phase_completed}' completion, but NO active timer state found in DB. Acknowledging without action.")
            return jsonify({'status': 'acknowledged_no_state'}), 200

        # --- State exists, proceed ---
        current_app.logger.debug(f"API Complete: Processing phase '{phase_completed}' completion for User {user_id}. Current DB state phase: '{server_state.phase}'")

        # Sanity check: does completed phase match server state?
        if server_state.phase != phase_completed:
            # This indicates a potential desync. Log it, but generally trust the client signal
            # as it drives the UI. The server is primarily for logging and persistence.
            current_app.logger.warning(f"API Complete: Phase mismatch for User {user_id}. Client says '{phase_completed}' done, DB state is '{server_state.phase}'. Proceeding based on client signal.")
            # Continue processing based on phase_completed from client

        if phase_completed == 'work':
            current_app.logger.info(f"API Complete: User {user_id} completed WORK phase. Logging session and transitioning to break.")
            # --- Log the completed Work Session ---
            # Use durations and start time stored in the server state for accuracy.
            try:
                log_entry = PomodoroSession(
                    user_id=user_id,
                    work_duration=server_state.work_duration_minutes,
                    break_duration=server_state.break_duration_minutes,
                    timestamp=server_state.start_time # Log with the actual start time of the work phase
                )
                db.session.add(log_entry)
                current_app.logger.debug(f"API Complete: Prepared PomodoroSession log entry for User {user_id}.")
            except Exception as log_err:
                # If creating the log object fails (unlikely), log error but try to continue state transition.
                current_app.logger.error(f"API Complete: Failed to create PomodoroSession object for User {user_id}: {log_err}", exc_info=True)
                # Do not add the failed log_entry to the session.

            # --- Update server state to Break ---
            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc # Reset start time for the break phase
            server_state.end_time = break_end_time_utc
            current_app.logger.debug(f"API Complete: Updated timer state to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}.")

            # Commit both the new session log (if successfully created) and the state update
            db.session.commit()
            current_app.logger.info(f"API Complete: User {user_id} successfully logged work session and transitioned to BREAK phase.")
            return jsonify({'status': 'break_started'}), 200

        elif phase_completed == 'break':
            current_app.logger.info(f"API Complete: User {user_id} completed BREAK phase. Clearing timer state.")
            # --- Clear server state ---
            db.session.delete(server_state)
            db.session.commit()
            current_app.logger.info(f"API Complete: Cleared active timer state from DB for User {user_id}.")
            return jsonify({'status': 'session_complete'}), 200

        else:
            # Should not happen if client sends 'work' or 'break'
            current_app.logger.error(f"API Complete: User {user_id} sent an invalid phase '{phase_completed}'.")
            return jsonify({'error': 'Invalid phase specified'}), 400

    except SQLAlchemyError as e:
        db.session.rollback() # Rollback on any DB error during processing
        current_app.logger.error(f"API Complete: Database error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred processing phase completion.'}), 500
    except Exception as e:
        db.session.rollback() # Rollback on any other unexpected error
        current_app.logger.error(f"API Complete: Unexpected error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred.'}), 500


@main.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_chat():
    """API endpoint for the AI productivity assistant chat."""
    # Check if chat is enabled via app config (set based on API key presence)
    if not current_app.config.get('FEATURE_CHAT_ENABLED', False):
        current_app.logger.warning(f"API Chat: Attempt by User {current_user.id} when chat feature is disabled.")
        return jsonify({'error': 'Chat feature is not configured or available.'}), 501 # 501 Not Implemented

    if not openai_client:
        current_app.logger.error(f"API Chat: Attempt by User {current_user.id} but OpenAI client is not initialized (check API key and logs).")
        return jsonify({'error': 'Chat service client is not available.'}), 503 # 503 Service Unavailable

    data = request.get_json()
    if not data or 'prompt' not in data or 'dashboard_data' not in data:
         current_app.logger.warning(f"API Chat: Bad request from User {current_user.id}. Missing prompt or dashboard_data.")
         return jsonify({'error': 'Missing prompt or dashboard_data in request'}), 400

    user_prompt = data.get('prompt', '').strip()
    dashboard_data = data.get('dashboard_data', {}) # Expects dict like {'total_focus': '120', ...}

    if not user_prompt:
         return jsonify({'error': 'Prompt cannot be empty.'}), 400

    # Log the prompt (be mindful of sensitive info if prompts could contain it)
    current_app.logger.info(f"API Chat: User {current_user.id} prompt (truncated): '{user_prompt[:100]}...'")

    # --- Construct Enhanced Context for AI (Ensure data extraction is robust) ---
    def get_data(key, default='N/A'):
        # Helper to safely get data, handling potential missing keys or None values
        val = dashboard_data.get(key)
        return val if val is not None else default

    context = f"""
    You are a helpful productivity assistant integrated into a Pomodoro timer web app.
    The user '{current_user.name}' (ID: {current_user.id}) you are talking to has the following Pomodoro statistics:

    Overall Stats:
    - Total Focused Time: {get_data('total_focus')} minutes
    - Total Break Time: {get_data('total_break')} minutes
    - Completed Pomodoro Sessions (Overall): {get_data('total_sessions')}

    Today's Stats (UTC):
    - Focused Time Today: {get_data('today_focus')} minutes
    - Sessions Today: {get_data('today_sessions')}

    This Week's Stats (UTC, starting Monday):
    - Focused Time This Week: {get_data('week_focus')} minutes
    - Sessions This Week: {get_data('week_sessions')}

    Answer the user's question based ONLY on this provided context and general productivity knowledge related to the Pomodoro technique. Be encouraging and helpful. Keep responses concise and focused. Do not invent statistics not provided.
    """
    # --- End of Enhanced Context ---

    try:
        # Use the Chat Completions endpoint
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4o-mini", # Or your preferred model like gpt-3.5-turbo
            max_tokens=250, # Adjust as needed
            temperature=0.6, # Balance creativity and factualness
            user=f"user-{current_user.id}" # Optional: pass user ID for monitoring abuse
        )

        # Extract the response text
        ai_response = chat_completion.choices[0].message.content.strip()
        current_app.logger.info(f"API Chat: OpenAI response generated successfully for User {current_user.id}.")
        return jsonify({'response': ai_response})

    except Exception as e:
        # Catch generic OpenAI errors or network issues
        current_app.logger.error(f"API Chat: Error calling OpenAI API for User {current_user.id}: {e}", exc_info=True)
        # Avoid leaking detailed internal errors to the client
        return jsonify({'error': 'Sorry, I encountered an issue while communicating with the AI service.'}), 500

# --- End of API Endpoints ---


@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    """Displays user dashboard with session history and stats."""
    user_id = current_user.id
    current_app.logger.debug(f"Dashboard: Loading data for User {user_id}")

    try:
        # --- Aggregate Stat Calculations (using SQLAlchemy functions) ---
        total_focus_query = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter_by(user_id=user_id)
        total_break_query = db.session.query(func.coalesce(func.sum(PomodoroSession.break_duration), 0)).filter_by(user_id=user_id)
        total_sessions_query = db.session.query(func.count(PomodoroSession.id)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.work_duration > 0 # Only count sessions with actual work time
        )

        total_focus = total_focus_query.scalar()
        total_break = total_break_query.scalar()
        total_sessions = total_sessions_query.scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Overall Stats - Focus: {total_focus}, Break: {total_break}, Sessions: {total_sessions}")

        # --- Time-based Stats (Using UTC) ---
        now_utc = datetime.now(timezone.utc)
        today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        # Assuming Monday is the start of the week (weekday() == 0)
        start_of_week_utc = today_start_utc - timedelta(days=now_utc.weekday())

        # Today's Stats
        today_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.timestamp >= today_start_utc
        ).scalar()
        today_sessions = db.session.query(func.count(PomodoroSession.id)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.work_duration > 0,
            PomodoroSession.timestamp >= today_start_utc
        ).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Today Stats - Focus: {today_focus}, Sessions: {today_sessions}")


        # This Week's Stats
        week_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.timestamp >= start_of_week_utc
        ).scalar()
        week_sessions = db.session.query(func.count(PomodoroSession.id)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.work_duration > 0,
            PomodoroSession.timestamp >= start_of_week_utc
        ).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Week Stats - Focus: {week_focus}, Sessions: {week_sessions}")


        # --- Fetch Session History ---
        # Limiting the history fetched can improve performance if list becomes huge
        # sessions_from_db = PomodoroSession.query.filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).limit(100).all() # Example limit
        sessions_from_db = PomodoroSession.query.filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).all()
        current_app.logger.debug(f"Dashboard: Fetched {len(sessions_from_db)} session history entries for User {user_id}")

        # Apply timezone info if needed (primarily for SQLite)
        aware_sessions = []
        for sess in sessions_from_db:
            # Check if timestamp exists and is naive
            if sess.timestamp and getattr(sess.timestamp, 'tzinfo', None) is None:
                try:
                    # Assume naive timestamps from SQLite are UTC
                    sess.timestamp = sess.timestamp.replace(tzinfo=timezone.utc)
                except Exception as tz_err:
                    # Log error if replace fails, pass the session with naive timestamp
                    current_app.logger.error(f"Dashboard: Could not make timestamp timezone-aware for session {sess.id}: {tz_err}")
            aware_sessions.append(sess)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Dashboard: Database error loading stats/history for User {user_id}: {e}", exc_info=True)
        # Render dashboard with potentially incomplete data or error message?
        # For now, set defaults and let template handle missing data gracefully.
        total_focus, total_break, total_sessions = 0, 0, 0
        today_focus, today_sessions = 0, 0
        week_focus, week_sessions = 0, 0
        aware_sessions = []
        # Optionally flash a message to the user
        # flash('Could not load all dashboard data due to a database error.', 'error')
    except Exception as e:
         current_app.logger.error(f"Dashboard: Unexpected error loading data for User {user_id}: {e}", exc_info=True)
         total_focus, total_break, total_sessions = 0, 0, 0
         today_focus, today_sessions = 0, 0
         week_focus, week_sessions = 0, 0
         aware_sessions = []
         # flash('An unexpected error occurred while loading the dashboard.', 'error')


    # Get chat enabled status from app config
    chat_enabled = current_app.config.get('FEATURE_CHAT_ENABLED', False)
    current_app.logger.debug(f"Dashboard: Rendering for User {user_id}. Chat enabled: {chat_enabled}")

    # Pass all stats and session list to the template.
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