# pomodoro_app/main/api_routes.py
# Handles all API endpoints for the main blueprint.

from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
import os
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Import database functions and specific exceptions
from sqlalchemy.exc import SQLAlchemyError

# Import blueprint object, database instance, limiter, and models
from . import main # Import the blueprint registered in __init__.py
from pomodoro_app import db, limiter
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

# Import helper functions from logic.py
from .logic import calculate_current_multiplier, update_streaks

# --- OpenAI Client (Initialize as None at module level) ---
# We will create the actual client instance inside the route if needed.
openai_client = None
_openai_initialized = False # Flag to avoid re-initializing repeatedly within the same process

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

        # Calculate multiplier applicable for this session START using the helper
        current_multiplier = calculate_current_multiplier(user, work_minutes)

        current_state = db.session.get(ActiveTimerState, user_id)

        if current_state:
            current_app.logger.info(f"API Start: Updating existing timer state for User {user_id}. New Mult: {current_multiplier}")
            current_state.phase = 'work'
            current_state.start_time = now_utc
            current_state.end_time = end_time_utc
            current_state.work_duration_minutes = work_minutes
            current_state.break_duration_minutes = break_minutes
            current_state.current_multiplier = current_multiplier
        else:
            current_app.logger.info(f"API Start: Creating new timer state for User {user_id}. Mult: {current_multiplier}")
            new_state = ActiveTimerState(
                user_id=user_id,
                phase='work',
                start_time=now_utc,
                end_time=end_time_utc,
                work_duration_minutes=work_minutes,
                break_duration_minutes=break_minutes,
                current_multiplier=current_multiplier
            )
            db.session.add(new_state)

        db.session.commit()
        current_app.logger.debug(f"API Start: Timer state saved for User {user_id}. Phase: work, Mult: {current_multiplier}, Ends: {end_time_utc.isoformat()}")

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
    # Get points per minute from config *within the request context*
    points_per_minute = current_app.config.get('POINTS_PER_MINUTE', 10)

    try:
        server_state = db.session.get(ActiveTimerState, user_id)
        user = db.session.get(User, user_id) # Get user

        if not user:
            current_app.logger.error(f"API Complete: Cannot find User {user_id} to complete phase.")
            if server_state: db.session.delete(server_state); db.session.commit()
            return jsonify({'error': 'User not found.'}), 500

        if not server_state:
            current_app.logger.warning(f"API Complete: User {user_id} reported phase '{phase_completed}' completion, but NO active timer state found. Acknowledging.")
            return jsonify({'status': 'acknowledged_no_state', 'total_points': user.total_points}), 200

        # --- State exists, proceed ---
        current_app.logger.debug(f"API Complete: Processing '{phase_completed}' completion for User {user_id}. DB phase: '{server_state.phase}', Start Mult: {server_state.current_multiplier}")

        if server_state.phase != phase_completed:
            current_app.logger.warning(f"API Complete: Phase mismatch for User {user_id}. Client says '{phase_completed}' done, DB is '{server_state.phase}'. Trusting client signal.")

        points_earned_this_phase = 0
        next_phase_status = 'unknown'
        new_total_points = user.total_points # Start with current total

        if phase_completed == 'work':
            planned_work_duration = server_state.work_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed WORK phase. Logging session, calculating points based on PLANNED duration ({planned_work_duration}min), updating streaks.")

            # --- Recalculate multiplier using the helper ---
            final_multiplier = calculate_current_multiplier(user, planned_work_duration)
            if final_multiplier != server_state.current_multiplier:
                current_app.logger.info(f"API Complete: User {user.id} final multiplier {final_multiplier} (Initial was {server_state.current_multiplier}). Using final.")

            # --- Calculate points ---
            points_earned_this_phase = int(round(planned_work_duration * points_per_minute * final_multiplier))
            new_total_points += points_earned_this_phase
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for work ({planned_work_duration}min * {points_per_minute} * {final_multiplier:.2f}x). New total: {new_total_points}")

            # --- Update streaks using the helper ---
            update_streaks(user, now_utc)
            user.total_points = new_total_points

            # Log the completed PomodoroSession
            try:
                log_entry = PomodoroSession(
                    user_id=user_id,
                    work_duration=planned_work_duration,
                    break_duration=server_state.break_duration_minutes,
                    points_earned=points_earned_this_phase,
                    timestamp=server_state.start_time # Use work phase start time
                )
                db.session.add(log_entry)
            except Exception as log_err:
                current_app.logger.error(f"API Complete: Failed to create PomodoroSession object for User {user_id}: {log_err}", exc_info=True)

            # Update server state to Break
            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc
            server_state.end_time = break_end_time_utc
            server_state.current_multiplier = 1.0 # Reset multiplier for break
            current_app.logger.debug(f"API Complete: Updated timer state to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}.")
            next_phase_status = 'break_started'

        elif phase_completed == 'break':
            planned_break_duration = server_state.break_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed BREAK phase. Awarding points based on PLANNED duration ({planned_break_duration}min), clearing state.")

            # --- Calculate points (Base rate only for breaks) ---
            points_earned_this_phase = planned_break_duration * points_per_minute
            new_total_points += points_earned_this_phase
            user.total_points = new_total_points # Update user total
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for break ({planned_break_duration} min). New total: {new_total_points}")

            # Clear server state
            db.session.delete(server_state)
            current_app.logger.info(f"API Complete: Cleared active timer state from DB for User {user_id}.")
            next_phase_status = 'session_complete'

        else:
            current_app.logger.error(f"API Complete: User {user_id} sent an invalid phase '{phase_completed}'.")
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': 'Invalid phase specified', 'total_points': user.total_points}), 400

        # Commit changes
        db.session.add(user) # Ensure updated user is staged
        db.session.commit()
        current_app.logger.info(f"API Complete: User {user_id} state committed. Status: {next_phase_status}")

        return jsonify({'status': next_phase_status, 'total_points': new_total_points}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Complete: Database error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        current_points = 0
        try: user_after_error = db.session.get(User, user_id); current_points = user_after_error.total_points if user_after_error else 0
        except Exception: pass
        return jsonify({'error': 'Database error processing phase completion.', 'total_points': current_points}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Complete: Unexpected error for User {user_id} processing phase '{phase_completed}': {e}", exc_info=True)
        current_points = 0
        try: user_after_error = db.session.get(User, user_id); current_points = user_after_error.total_points if user_after_error else 0
        except Exception: pass
        return jsonify({'error': 'An unexpected server error occurred.', 'total_points': current_points}), 500


@main.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_chat():
    """API endpoint for the AI productivity assistant chat."""
    global openai_client, _openai_initialized # Allow modification of global variables

    # Check config flag first (safe to do within request context)
    if not current_app.config.get('FEATURE_CHAT_ENABLED', False):
        current_app.logger.warning(f"API Chat: Attempt by User {current_user.id} when chat feature is disabled.")
        return jsonify({'error': 'Chat feature is not configured or available.'}), 501 # 501 Not Implemented

    # --- Lazy Initialization of OpenAI Client ---
    # Initialize only if the library exists and hasn't been tried yet
    if OpenAI and not _openai_initialized:
        api_key = current_app.config.get('OPENAI_API_KEY')
        if api_key:
            try:
                openai_client = OpenAI(api_key=api_key)
                current_app.logger.info("OpenAI client initialized successfully inside API route.")
            except Exception as e:
                current_app.logger.error(f"Failed to initialize OpenAI client inside API route: {e}")
                openai_client = None # Ensure client is None if init fails
        else:
             current_app.logger.warning("FEATURE_CHAT_ENABLED is True, but OPENAI_API_KEY is not set (checked in route).")
        _openai_initialized = True # Mark as tried, even if it failed

    # Check if client is available *after* attempting initialization
    if not openai_client:
        # Log the reason if it wasn't just disabled by config
        if _openai_initialized: # It was tried but failed or key was missing
             current_app.logger.error(f"API Chat: Attempt by User {current_user.id} but OpenAI client is unavailable (initialization failed or no key).")
        return jsonify({'error': 'Chat service client is not available.'}), 503 # 503 Service Unavailable
    # --- End OpenAI Client Handling ---


    data = request.get_json()
    if not data or 'prompt' not in data or 'dashboard_data' not in data:
         current_app.logger.warning(f"API Chat: Bad request from User {current_user.id}. Missing prompt or dashboard_data.")
         return jsonify({'error': 'Missing prompt or dashboard_data in request'}), 400

    user_prompt = data.get('prompt', '').strip()
    dashboard_data = data.get('dashboard_data', {})

    if not user_prompt:
         return jsonify({'error': 'Prompt cannot be empty.'}), 400

    current_app.logger.info(f"API Chat: User {current_user.id} prompt (truncated): '{user_prompt[:100]}...'")

    # --- Construct Enhanced Context for AI ---
    def get_data(key, default='N/A'):
        val = dashboard_data.get(key)
        return str(val) if val is not None else default # Ensure string representation

    user_points = "N/A"
    try:
        user = db.session.get(User, current_user.id)
        user_points = str(user.total_points) if user else "N/A"
    except Exception as e:
        current_app.logger.error(f"API Chat: Failed to get user points for context: {e}")

    context = f"""
    You are a helpful productivity assistant for a Pomodoro timer web app that uses a points system.
    User '{current_user.name}' (ID: {current_user.id}) is asking a question. Their current stats are:

    - Total Points: {user_points}
    - Total Focus Time (minutes): {get_data('total_focus')}
    - Total Break Time (minutes): {get_data('total_break')}
    - Total Pomodoro Sessions: {get_data('total_sessions')}
    - Today's Focus Time (minutes, UTC): {get_data('today_focus')}
    - Today's Sessions (UTC): {get_data('today_sessions')}
    - This Week's Focus Time (minutes, UTC): {get_data('week_focus')}
    - This Week's Sessions (UTC): {get_data('week_sessions')}

    Answer the user's question based ONLY on these stats and general knowledge about the Pomodoro technique, productivity, and interpreting simple metrics like points and session counts. Be encouraging. Keep responses concise (around 1-3 sentences usually). Do not invent data. If the question is unrelated to productivity or their stats, politely decline to answer.
    """
    # --- End of Enhanced Context ---

    try:
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4o-mini", # Specify the model
            max_tokens=150, # Limit response length
            temperature=0.5, # Slightly more focused
            user=f"user-{current_user.id}"
        )

        ai_response = chat_completion.choices[0].message.content.strip()
        current_app.logger.info(f"API Chat: OpenAI response generated successfully for User {current_user.id}.")
        return jsonify({'response': ai_response})

    except Exception as e:
        # Catch specific OpenAI errors if desired, otherwise generic is ok
        current_app.logger.error(f"API Chat: Error calling OpenAI API for User {current_user.id}: {e}", exc_info=True)
        return jsonify({'error': 'Sorry, I encountered an issue contacting the AI service.'}), 500