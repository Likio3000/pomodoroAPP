# pomodoro_app/main/routes.py
from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app
)
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone, date # Add date
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
from pomodoro_app.models import PomodoroSession, ActiveTimerState, User # Make sure User is imported

main = Blueprint('main', __name__)

# --- OpenAI Client Initialization ---
# Initialize based on environment variable presence, checked later via config flag
openai_client = None
openai_api_key = os.getenv("OPENAI_API_KEY")
if OpenAI and openai_api_key:
    try:
        openai_client = OpenAI(api_key=openai_api_key)
        # Logging about OpenAI init status is done in create_app
    except Exception as e:
        print(f"WARNING: Failed to initialize OpenAI client during module load: {e}") # Print warning if init fails early
        openai_client = None


# --- Constants ---
POINTS_PER_MINUTE = 10
# Define Multiplier Rules (can be moved to config later)
MULTIPLIER_RULES = [
    {'id': 'base', 'condition': 'Base Rate (Work)', 'bonus': 0.0, 'details': 'Active during focused work.'},
    {'id': 'focus25', 'condition': 'Work Block > 25 Min', 'bonus': 0.1, 'details': 'Complete >25 mins in one work session.'},
    {'id': 'focus45', 'condition': 'Work Block > 45 Min', 'bonus': 0.2, 'details': 'Complete >45 mins in one work session.'},
    {'id': 'consecutive3', 'condition': '3+ Consecutive Sessions', 'bonus': 0.1, 'details': 'Complete 3+ work/break cycles.'},
    {'id': 'consecutive5', 'condition': '5+ Consecutive Sessions', 'bonus': 0.2, 'details': 'Complete 5+ work/break cycles.'},
    {'id': 'daily3', 'condition': '3+ Day Usage Streak', 'bonus': 0.1, 'details': 'Use timer for work 3+ days running.'},
    {'id': 'daily7', 'condition': '7+ Day Usage Streak', 'bonus': 0.2, 'details': 'Use timer for work 7+ days running.'},
]
MAX_CONSISTENCY_GAP_HOURS = 2 # How long between sessions before consistency streak breaks

# --- Helper Functions ---

def calculate_current_multiplier(user, work_duration_this_session=0):
    """Calculates the applicable multiplier based on user streaks AND PLANNED session duration."""
    base_multiplier = 1.0

    # --- Calculate bonuses independently ---
    streak_bonus = 0.0
    # Daily Streak Bonus (Highest applies)
    if user.daily_streak >= 7:
        streak_bonus = max(streak_bonus, 0.2)
    elif user.daily_streak >= 3:
        streak_bonus = max(streak_bonus, 0.1)

    # Consistency Streak Bonus (Highest applies)
    if user.consecutive_sessions >= 5:
        streak_bonus = max(streak_bonus, 0.2)
    elif user.consecutive_sessions >= 3:
        streak_bonus = max(streak_bonus, 0.1)

    # PLANNED Session Duration Bonus (Highest applies)
    duration_bonus = 0.0
    # Use the work_duration_this_session which should be the PLANNED duration
    if work_duration_this_session > 45:
         duration_bonus = max(duration_bonus, 0.2)
    elif work_duration_this_session > 25:
         duration_bonus = max(duration_bonus, 0.1)

    # Combine bonuses additively
    total_multiplier = base_multiplier + streak_bonus + duration_bonus

    # Optional: Cap the multiplier if desired (e.g., max 2.0x)
    # total_multiplier = min(total_multiplier, 2.0)

    current_app.logger.debug(f"Multiplier Calc for User {user.id}: Streaks={streak_bonus:.1f}, PlannedDuration({work_duration_this_session}min)={duration_bonus:.1f} -> Total={total_multiplier:.1f}")
    return round(total_multiplier, 2) # Round to avoid float issues

def update_streaks(user, now_utc):
    """Updates daily and consistency streaks based on the current time. Called on WORK phase completion."""
    today_utc = now_utc.date()

    # --- Daily Streak ---
    # Check if user was active today already. If so, don't increment/reset.
    if user.last_active_date != today_utc:
        if user.last_active_date:
            days_diff = (today_utc - user.last_active_date).days
            if days_diff == 1:
                user.daily_streak += 1
                current_app.logger.info(f"User {user.id}: Daily streak continued ({user.daily_streak} days).")
            elif days_diff > 1:
                user.daily_streak = 1 # Reset if gap is more than 1 day
                current_app.logger.info(f"User {user.id}: Daily streak reset (gap > 1 day). New streak: 1.")
            # else days_diff <= 0 (shouldn't happen if check above works)
        else:
            user.daily_streak = 1 # First active day recorded
            current_app.logger.info(f"User {user.id}: Daily streak started (1 day).")
        user.last_active_date = today_utc # Update last active date only if it changed

    # --- Consistency Streak ---
    reset_consistency = True
    if user.last_session_timestamp: # Check if a previous session exists

        # +++ FIX: Make last_session_timestamp timezone-aware +++
        aware_last_session_timestamp = None
        if getattr(user.last_session_timestamp, 'tzinfo', None) is None:
            # If naive, assume it's UTC and make it aware
            aware_last_session_timestamp = user.last_session_timestamp.replace(tzinfo=timezone.utc)
            current_app.logger.debug(f"Update Streaks: Made naive last_session_timestamp ({user.last_session_timestamp}) UTC-aware.")
        else:
            # If already aware, use it directly
            aware_last_session_timestamp = user.last_session_timestamp
            current_app.logger.debug(f"Update Streaks: last_session_timestamp ({user.last_session_timestamp}) is already timezone-aware.")
        # ++++++++++++++++++++++++++++++++++++++++++++++++++++++

        # Now perform subtraction with two aware datetimes
        time_diff = now_utc - aware_last_session_timestamp # Time since last work phase ENDED

        # Simplified check: Was the last session end within X hours?
        if time_diff <= timedelta(hours=MAX_CONSISTENCY_GAP_HOURS):
            user.consecutive_sessions += 1
            reset_consistency = False
            current_app.logger.info(f"User {user.id}: Consistency streak continued ({user.consecutive_sessions} sessions). Timediff: {time_diff}")
        else:
             current_app.logger.info(f"User {user.id}: Consistency streak broken. Timediff: {time_diff} > {MAX_CONSISTENCY_GAP_HOURS} hours.")

    if reset_consistency:
        user.consecutive_sessions = 1 # Start/reset streak to 1 (current session counts)
        current_app.logger.info(f"User {user.id}: Consistency streak started/reset (1 session).")

    # Update timestamp AFTER calculating streak, marks end of this work phase
    user.last_session_timestamp = now_utc

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
    """Displays the timer page with points and multiplier info."""
    user_id = current_user.id
    active_multiplier = 1.0 # Default if no active session
    total_points = 0
    active_state_info = None
    user = None # Initialize user

    try:
        # Use session.get for optimized lookup
        user = db.session.get(User, user_id)
        if not user: # Should not happen if logged in, but safety check
             current_app.logger.error(f"Timer Route: Could not find logged in user {user_id} in DB.")
             return redirect(url_for('auth.logout')) # Example handling

        total_points = user.total_points

        # Check for active timer state
        active_state = db.session.get(ActiveTimerState, user_id)
        if active_state:
             active_multiplier = active_state.current_multiplier
             active_state_info = { # Pass state details for JS resume logic
                  'phase': active_state.phase,
                  'endTime': active_state.end_time.isoformat(), # Send end time
                  'workMins': active_state.work_duration_minutes,
                  'breakMins': active_state.break_duration_minutes,
                  'multiplier': active_state.current_multiplier
             }
             current_app.logger.debug(f"Timer Route: Found active state for User {user_id}. Phase: {active_state.phase}, Mult: {active_multiplier}")
        else:
             # Calculate potential multiplier for *next* session based on current streaks
             # Pass 0 for work_duration as session hasn't started
             active_multiplier = calculate_current_multiplier(user, 0)
             current_app.logger.debug(f"Timer Route: No active state for User {user_id}. Potential next multiplier: {active_multiplier}")


    except SQLAlchemyError as e:
        current_app.logger.error(f"Timer Route: Database error loading data for User {user_id}: {e}", exc_info=True)
        # flash('Error loading timer data.', 'error') # Optional flash message
    except Exception as e:
         current_app.logger.error(f"Timer Route: Unexpected error for User {user_id}: {e}", exc_info=True)
         # flash('An unexpected error occurred.', 'error') # Optional flash message


    # Get points per minute from config or use default
    points_per_min_config = current_app.config.get('POINTS_PER_MINUTE', POINTS_PER_MINUTE)

    return render_template(
        'main/timer.html',
        total_points=total_points,
        active_multiplier=active_multiplier,
        multiplier_rules=MULTIPLIER_RULES, # Pass the rules definition
        active_state_info=active_state_info, # Pass active state details or None
        config={'POINTS_PER_MINUTE': points_per_min_config} # Pass config needed by template
    )


# --- API Endpoints ---

@main.route('/api/timer/start', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_start_timer():
    """API endpoint for the client to signal the start/restart of a timer. Calculates multiplier."""
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
        # Get user object to calculate multiplier
        user = db.session.get(User, user_id)
        if not user:
             current_app.logger.error(f"API Start: Cannot find User {user_id} to start timer.")
             return jsonify({'error': 'User not found.'}), 500 # Internal error likely

        # Calculate multiplier applicable for this session START
        # Pass planned work_minutes to check potential duration bonus for initial display
        current_multiplier = calculate_current_multiplier(user, work_minutes)

        current_state = db.session.get(ActiveTimerState, user_id)

        if current_state:
            # If restarting, ensure consistency streak isn't broken inappropriately
            # This logic might need refinement depending on desired behavior for quick restarts
            current_app.logger.info(f"API Start: Updating existing timer state for User {user_id}. New Mult: {current_multiplier}")
            current_state.phase = 'work'
            current_state.start_time = now_utc
            current_state.end_time = end_time_utc
            current_state.work_duration_minutes = work_minutes
            current_state.break_duration_minutes = break_minutes
            current_state.current_multiplier = current_multiplier # Update multiplier
        else:
            current_app.logger.info(f"API Start: Creating new timer state for User {user_id}. Mult: {current_multiplier}")
            new_state = ActiveTimerState(
                user_id=user_id,
                phase='work',
                start_time=now_utc,
                end_time=end_time_utc,
                work_duration_minutes=work_minutes,
                break_duration_minutes=break_minutes,
                current_multiplier=current_multiplier # Set multiplier
            )
            db.session.add(new_state)

        db.session.commit()
        current_app.logger.debug(f"API Start: Timer state saved for User {user_id}. Phase: work, Mult: {current_multiplier}, Ends: {end_time_utc.isoformat()}")

        # Return current points and the active multiplier
        return jsonify({
            'status': 'timer_started',
            'total_points': user.total_points,
            'active_multiplier': current_multiplier,
            'end_time': end_time_utc.isoformat() # Send end time to client
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Start: Database error saving timer state for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred saving timer state.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Start: Unexpected error saving timer state for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred.'}), 500


@main.route('/api/timer/complete_phase', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_complete_phase():
    """API endpoint for phase completion. Calculates points based on PLANNED duration and updates user stats/streaks."""
    data = request.get_json()
    if not data or 'phase_completed' not in data:
         current_app.logger.warning(f"API Complete: Bad request from User {current_user.id}. Missing phase_completed field.")
         return jsonify({'error': 'Missing phase_completed field'}), 400

    phase_completed = data.get('phase_completed')
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)

    try:
        server_state = db.session.get(ActiveTimerState, user_id)
        user = db.session.get(User, user_id) # Get user

        if not user:
            current_app.logger.error(f"API Complete: Cannot find User {user_id} to complete phase.")
            # Clean up state if it exists but user doesn't (edge case)
            if server_state: db.session.delete(server_state); db.session.commit()
            return jsonify({'error': 'User not found.'}), 500

        if not server_state:
            current_app.logger.warning(f"API Complete: User {user_id} reported phase '{phase_completed}' completion, but NO active timer state found. Acknowledging.")
            return jsonify({'status': 'acknowledged_no_state', 'total_points': user.total_points}), 200

        # --- State exists, proceed ---
        current_app.logger.debug(f"API Complete: Processing '{phase_completed}' completion for User {user_id}. DB phase: '{server_state.phase}', Start Mult: {server_state.current_multiplier}")

        if server_state.phase != phase_completed:
            current_app.logger.warning(f"API Complete: Phase mismatch for User {user_id}. Client says '{phase_completed}' done, DB is '{server_state.phase}'. Trusting client signal, but check logic.")
            # Let's proceed based on client signal, but log potential issue

        points_earned_this_phase = 0
        next_phase_status = 'unknown'
        new_total_points = user.total_points # Start with current total

        if phase_completed == 'work':
            # --- Use PLANNED duration stored in the state ---
            planned_work_duration = server_state.work_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed WORK phase. Logging session, calculating points based on PLANNED duration ({planned_work_duration}min), updating streaks.")

            # --- Recalculate multiplier based on the PLANNED duration ---
            # (This ensures duration bonus is applied correctly based on the plan, and considers current streaks)
            final_multiplier = calculate_current_multiplier(user, planned_work_duration)
            if final_multiplier != server_state.current_multiplier:
                # Log if the multiplier calculated now (with current streaks) differs from the one stored at the start
                current_app.logger.info(f"API Complete: User {user.id} planned duration ({planned_work_duration}m) resulted in final multiplier {final_multiplier} (Initial was {server_state.current_multiplier}). Using final multiplier for points.")
            else:
                 current_app.logger.debug(f"API Complete: User {user.id} final multiplier {final_multiplier} matches initial multiplier.")


            # --- Calculate points using PLANNED duration and FINAL multiplier ---
            points_earned_this_phase = int(round(planned_work_duration * POINTS_PER_MINUTE * final_multiplier))
            new_total_points += points_earned_this_phase
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for work ({planned_work_duration}min * {POINTS_PER_MINUTE} * {final_multiplier:.2f}x). New total: {new_total_points}")

            # Update streaks and points on User object *after* calculation
            # This updates consecutive_sessions, daily_streak, last_active_date, last_session_timestamp
            update_streaks(user, now_utc)
            user.total_points = new_total_points

            # Log the completed PomodoroSession using PLANNED work duration
            try:
                log_entry = PomodoroSession(
                    user_id=user_id,
                    work_duration=planned_work_duration, # Log planned duration
                    break_duration=server_state.break_duration_minutes,
                    points_earned=points_earned_this_phase, # Log points earned
                    timestamp=server_state.start_time # Log start time of work phase
                )
                db.session.add(log_entry)
            except Exception as log_err:
                current_app.logger.error(f"API Complete: Failed to create PomodoroSession object for User {user_id}: {log_err}", exc_info=True)

            # Update server state to Break
            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc # Reset start time for the break phase
            server_state.end_time = break_end_time_utc
            server_state.current_multiplier = 1.0 # Reset multiplier for break
            current_app.logger.debug(f"API Complete: Updated timer state to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}.")
            next_phase_status = 'break_started'


        elif phase_completed == 'break':
            # --- Use PLANNED break duration stored in the state ---
            planned_break_duration = server_state.break_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed BREAK phase. Awarding points based on PLANNED duration ({planned_break_duration}min), clearing state.")

            # --- Calculate points using PLANNED duration (Base rate only for breaks) ---
            points_earned_this_phase = planned_break_duration * POINTS_PER_MINUTE
            new_total_points += points_earned_this_phase
            user.total_points = new_total_points # Update user total
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for break ({planned_break_duration} min). New total: {new_total_points}")

            # Do NOT update streaks on break completion. Streaks are based on work completion.

            # Clear server state
            db.session.delete(server_state)
            current_app.logger.info(f"API Complete: Cleared active timer state from DB for User {user_id}.")
            next_phase_status = 'session_complete'

        else:
            # Should not happen if client sends 'work' or 'break'
            current_app.logger.error(f"API Complete: User {user_id} sent an invalid phase '{phase_completed}'.")
            # Clean up state if invalid phase somehow reached here
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': 'Invalid phase specified', 'total_points': user.total_points}), 400

        # Commit user update, log entry (if any), state update/delete
        db.session.add(user) # Ensure updated user is staged for commit
        # log_entry and server_state changes/deletion are already staged if applicable
        db.session.commit()
        current_app.logger.info(f"API Complete: User {user_id} state committed. Status: {next_phase_status}")

        # Return new point total and status
        return jsonify({'status': next_phase_status, 'total_points': new_total_points}), 200

    except SQLAlchemyError as e:
        db.session.rollback() # Rollback on any DB error during processing
        current_app.logger.error(f"API Complete: Database error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        # Try to return current points even on error
        current_points = 0
        try:
            # Attempt to fetch points again after rollback (might fail if connection is bad)
            user_after_error = db.session.get(User, user_id)
            if user_after_error: current_points = user_after_error.total_points
        except Exception:
            pass # Ignore error during error handling
        return jsonify({'error': 'Database error occurred processing phase completion.', 'total_points': current_points}), 500
    except Exception as e:
        db.session.rollback() # Rollback on any other unexpected error
        current_app.logger.error(f"API Complete: Unexpected error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        current_points = 0
        try:
            user_after_error = db.session.get(User, user_id)
            if user_after_error: current_points = user_after_error.total_points
        except Exception:
            pass
        return jsonify({'error': 'An unexpected server error occurred.', 'total_points': current_points}), 500


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

    # +++ Add User's Total Points to Context +++
    try:
        # Fetch points directly here to ensure latest value
        user = db.session.get(User, current_user.id)
        user_points = user.total_points if user else "N/A"
    except Exception as e:
        current_app.logger.error(f"API Chat: Failed to get user points for context: {e}")
        user_points = "N/A"

    context = f"""
    You are a helpful productivity assistant integrated into a Pomodoro timer web app with a points system.
    The user '{current_user.name}' (ID: {current_user.id}) you are talking to has the following Pomodoro statistics:

    Points & Overall Stats:
    - Total Earned Points: {user_points}
    - Total Focused Time: {get_data('total_focus')} minutes
    - Total Break Time: {get_data('total_break')} minutes
    - Completed Pomodoro Sessions (Overall): {get_data('total_sessions')}

    Today's Stats (UTC):
    - Focused Time Today: {get_data('today_focus')} minutes
    - Sessions Today: {get_data('today_sessions')}

    This Week's Stats (UTC, starting Monday):
    - Focused Time This Week: {get_data('week_focus')} minutes
    - Sessions This Week: {get_data('week_sessions')}

    Answer the user's question based ONLY on this provided context and general productivity knowledge related to the Pomodoro technique and gamification (points/streaks). Be encouraging and helpful. Keep responses concise and focused. Do not invent statistics not provided.
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


@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    """Displays user dashboard with session history and stats."""
    user_id = current_user.id
    current_app.logger.debug(f"Dashboard: Loading data for User {user_id}")
    user = None # Initialize user
    total_points = 0 # Initialize points

    try:
        # Fetch user once to get points and potentially other user-specific stats
        user = db.session.get(User, user_id)
        if not user:
            current_app.logger.error(f"Dashboard: Could not find logged in user {user_id} in DB.")
            return redirect(url_for('auth.logout'))

        total_points = user.total_points # Get total points from user object

        # --- Aggregate Stat Calculations (using SQLAlchemy functions) ---
        total_focus_query = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user_id)
        total_break_query = db.session.query(func.coalesce(func.sum(PomodoroSession.break_duration), 0)).filter(PomodoroSession.user_id == user_id)
        total_sessions_query = db.session.query(func.count(PomodoroSession.id)).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.work_duration > 0 # Only count sessions with actual work time
        )

        total_focus = total_focus_query.scalar()
        total_break = total_break_query.scalar()
        total_sessions = total_sessions_query.scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Overall Stats - Focus: {total_focus}, Break: {total_break}, Sessions: {total_sessions}, Points: {total_points}")


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
        sessions_from_db = PomodoroSession.query.filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).limit(100).all() # Limit history display
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
                    current_app.logger.error(f"Dashboard: Could not make timestamp timezone-aware for session {sess.id}: {tz_err}")
            aware_sessions.append(sess)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Dashboard: Database error loading stats/history for User {user_id}: {e}", exc_info=True)
        total_focus, total_break, total_sessions = 0, 0, 0
        today_focus, today_sessions = 0, 0
        week_focus, week_sessions = 0, 0
        aware_sessions = []
        # Ensure total_points has a default value on error
        total_points = user.total_points if user else 0
        # flash('Could not load all dashboard data due to a database error.', 'error')
    except Exception as e:
         current_app.logger.error(f"Dashboard: Unexpected error loading data for User {user_id}: {e}", exc_info=True)
         total_focus, total_break, total_sessions = 0, 0, 0
         today_focus, today_sessions = 0, 0
         week_focus, week_sessions = 0, 0
         aware_sessions = []
         total_points = user.total_points if user else 0
         # flash('An unexpected error occurred while loading the dashboard.', 'error')


    # Get chat enabled status from app config
    chat_enabled = current_app.config.get('FEATURE_CHAT_ENABLED', False)
    current_app.logger.debug(f"Dashboard: Rendering for User {user_id}. Chat enabled: {chat_enabled}")

    # Pass all stats and session list to the template.
    return render_template('main/dashboard.html',
                           # Add total points
                           total_points=total_points,
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