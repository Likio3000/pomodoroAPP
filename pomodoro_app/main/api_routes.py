# pomodoro_app/main/api_routes.py
# Handles all API endpoints for the main blueprint.

from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone # Ensure timedelta is imported
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
openai_client = None
_openai_initialized = False

# --- API Endpoints ---

@main.route('/api/timer/state', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def api_get_timer_state():
    """API endpoint to fetch the current timer state for the logged-in user."""
    user_id = current_user.id
    try:
        active_state = db.session.get(ActiveTimerState, user_id)
        if not active_state:
            current_app.logger.debug(f"API Timer State GET: No active state for User {user_id}")
            return jsonify({'active': False}), 200

        end_time_iso = None
        if active_state.end_time:
            end_time = active_state.end_time
            if getattr(end_time, 'tzinfo', None) is None:
                 end_time = end_time.replace(tzinfo=timezone.utc)
            end_time_iso = end_time.isoformat()

        start_time_iso = None
        if active_state.start_time:
             start_time = active_state.start_time
             if getattr(start_time, 'tzinfo', None) is None:
                 start_time = start_time.replace(tzinfo=timezone.utc)
             start_time_iso = start_time.isoformat()

        current_app.logger.debug(f"API Timer State GET: Found active state for User {user_id}: Phase {active_state.phase}, Ends {end_time_iso}")
        return jsonify({
            'active': True,
            'phase': active_state.phase,
            'start_time': start_time_iso,
            'end_time': end_time_iso,
            'work_duration_minutes': active_state.work_duration_minutes,
            'break_duration_minutes': active_state.break_duration_minutes,
            'current_multiplier': getattr(active_state, 'current_multiplier', 1.0)
        }), 200
    except SQLAlchemyError as e:
        current_app.logger.error(f"API Timer State GET: DB Error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error fetching timer state.'}), 500
    except Exception as e:
        current_app.logger.error(f"API Timer State GET: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred fetching state.'}), 500


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
        user = db.session.get(User, user_id)
        if not user:
             current_app.logger.error(f"API Start: Cannot find User {user_id} to start timer.")
             return jsonify({'error': 'User not found.'}), 500

        current_multiplier = calculate_current_multiplier(user, work_minutes)
        current_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

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
            'end_time': end_time_utc.isoformat()
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
    points_per_minute = current_app.config.get('POINTS_PER_MINUTE', 10)

    try:
        user = db.session.query(User).filter_by(id=user_id).with_for_update().first()
        server_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if not user:
            current_app.logger.error(f"API Complete: Cannot find User {user_id} to complete phase.")
            return jsonify({'error': 'User not found.'}), 500

        if not server_state:
            current_app.logger.warning(f"API Complete: User {user_id} reported phase '{phase_completed}' completion, but NO active timer state found. Acknowledging.")
            return jsonify({'status': 'acknowledged_no_state', 'total_points': user.total_points}), 200

        current_app.logger.debug(f"API Complete: Processing '{phase_completed}' completion for User {user_id}. DB phase: '{server_state.phase}', Start Mult: {server_state.current_multiplier}")

        end_time = server_state.end_time
        if end_time is None:
             current_app.logger.error(f"API Complete: ActiveTimerState for User {user_id} has no end_time!")
             db.session.delete(server_state); db.session.commit()
             return jsonify({'error': 'Inconsistent timer state found on server.'}), 500

        if getattr(end_time, 'tzinfo', None) is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        grace_period = timedelta(seconds=2)
        if now_utc < (end_time - grace_period):
            time_diff = end_time - now_utc
            current_app.logger.warning(
                f"API Complete: User {user_id} tried to complete phase '{phase_completed}' too early. "
                f"Now: {now_utc.isoformat()}, End: {end_time.isoformat()}, Diff: {time_diff}"
            )
            return jsonify({
                'error': f'Timer not finished yet! {int(time_diff.total_seconds())}s remaining.',
                'total_points': user.total_points
                }), 400

        if server_state.phase != phase_completed:
            current_app.logger.warning(f"API Complete: Phase mismatch for User {user_id}. Client says '{phase_completed}' done, DB is '{server_state.phase}'. Trusting client signal BUT using DB phase '{server_state.phase}' for logic.")
            phase_completed = server_state.phase

        points_earned_this_phase = 0
        next_phase_status = 'unknown'
        new_total_points = user.total_points

        if phase_completed == 'work':
            planned_work_duration = server_state.work_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed WORK phase. Logging session, calculating points based on PLANNED duration ({planned_work_duration}min), updating streaks.")

            final_multiplier = calculate_current_multiplier(user, planned_work_duration)
            if abs(final_multiplier - server_state.current_multiplier) > 0.01:
                current_app.logger.info(f"API Complete: User {user.id} final multiplier {final_multiplier:.2f} (Initial was {server_state.current_multiplier:.2f}). Using final.")

            if points_per_minute is None or not isinstance(points_per_minute, (int, float)) or points_per_minute < 0:
                 current_app.logger.error(f"API Complete: Invalid POINTS_PER_MINUTE configuration ({points_per_minute}). Skipping point award for work.")
                 points_earned_this_phase = 0
            else:
                points_earned_this_phase = int(round(planned_work_duration * points_per_minute * final_multiplier))

            new_total_points += points_earned_this_phase
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for work ({planned_work_duration}min * {points_per_minute} * {final_multiplier:.2f}x). New total: {new_total_points}")

            update_streaks(user, now_utc)
            user.total_points = new_total_points

            try:
                work_start_time = server_state.start_time
                if work_start_time and getattr(work_start_time, 'tzinfo', None) is None:
                    work_start_time = work_start_time.replace(tzinfo=timezone.utc)
                log_entry = PomodoroSession(
                    user_id=user_id, work_duration=planned_work_duration,
                    break_duration=server_state.break_duration_minutes,
                    points_earned=points_earned_this_phase, timestamp=work_start_time
                )
                db.session.add(log_entry)
            except Exception as log_err:
                current_app.logger.error(f"API Complete: Failed to create PomodoroSession object for User {user_id}: {log_err}", exc_info=True)

            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc
            server_state.end_time = break_end_time_utc
            server_state.current_multiplier = 1.0
            current_app.logger.debug(f"API Complete: Updated timer state to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}.")
            next_phase_status = 'break_started'

        elif phase_completed == 'break':
            planned_break_duration = server_state.break_duration_minutes
            current_app.logger.info(f"API Complete: User {user_id} completed BREAK phase. Awarding points based on PLANNED duration ({planned_break_duration}min), clearing state.")

            if points_per_minute is None or not isinstance(points_per_minute, (int, float)) or points_per_minute < 0:
                current_app.logger.error(f"API Complete: Invalid POINTS_PER_MINUTE configuration ({points_per_minute}). Skipping point award for break.")
                points_earned_this_phase = 0
            else:
                points_earned_this_phase = int(round(planned_break_duration * points_per_minute))

            new_total_points += points_earned_this_phase
            user.total_points = new_total_points
            current_app.logger.info(f"API Complete: User {user_id} earned {points_earned_this_phase} points for break ({planned_break_duration} min). New total: {new_total_points}")

            db.session.delete(server_state)
            current_app.logger.info(f"API Complete: Cleared active timer state from DB for User {user_id}.")
            next_phase_status = 'session_complete'

        else:
            current_app.logger.error(f"API Complete: User {user_id} sent an invalid phase '{phase_completed}'. DB state was '{server_state.phase}'. Clearing state.")
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': f'Invalid phase specified: {phase_completed}', 'total_points': user.total_points}), 400

        if 'log_entry' in locals() and log_entry: db.session.add(log_entry)
        db.session.commit()
        current_app.logger.info(f"API Complete: User {user_id} state committed. Status: {next_phase_status}, Points: {new_total_points}")

        return jsonify({'status': next_phase_status, 'total_points': new_total_points}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Complete: Database error for User {user_id} processing phase '{data.get('phase_completed', 'unknown')}': {e}", exc_info=True)
        current_points = 0
        try:
            user_after_error = db.session.get(User, user_id)
            current_points = user_after_error.total_points if user_after_error else 0
        except Exception: pass
        return jsonify({'error': 'Database error processing phase completion.', 'total_points': current_points}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Complete: Unexpected error for User {user_id} processing phase '{data.get('phase_completed', 'unknown')}': {e}", exc_info=True)
        current_points = 0
        try:
            user_after_error = db.session.get(User, user_id)
            current_points = user_after_error.total_points if user_after_error else 0
        except Exception: pass
        return jsonify({'error': 'An unexpected server error occurred.', 'total_points': current_points}), 500


@main.route('/api/timer/reset', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_reset_timer():
    """API endpoint to clear the active timer state on the server."""
    user_id = current_user.id
    current_app.logger.info(f"API Reset: Received request from User {user_id}")
    try:
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if active_state:
            db.session.delete(active_state)
            db.session.commit()
            current_app.logger.info(f"API Reset: Successfully deleted active timer state for User {user_id}")
            return jsonify({'status': 'reset_success'}), 200
        else:
            current_app.logger.info(f"API Reset: No active timer state found to delete for User {user_id}")
            return jsonify({'status': 'no_state_to_reset'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Reset: Database error deleting timer state for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred during reset.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Reset: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred during reset.'}), 500


@main.route('/api/timer/resume', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_resume_timer():
    """API endpoint to adjust server end time after a client pause."""
    data = request.get_json()
    if not data or 'pause_duration_ms' not in data:
        current_app.logger.warning(f"API Resume: Bad request from User {current_user.id}. Missing pause_duration_ms.")
        return jsonify({'error': 'Missing pause duration information'}), 400

    try:
        pause_duration_ms = int(data['pause_duration_ms'])
        if pause_duration_ms < 0:
             raise ValueError("Pause duration cannot be negative.")
    except (ValueError, TypeError):
        current_app.logger.warning(f"API Resume: Bad request from User {current_user.id}. Invalid pause_duration_ms: {data.get('pause_duration_ms')}")
        return jsonify({'error': 'Invalid pause duration value'}), 400

    user_id = current_user.id
    current_app.logger.info(f"API Resume: User {user_id} resuming. Adjusting end time by {pause_duration_ms}ms.")

    try:
        # Lock the row for update
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if not active_state:
            current_app.logger.warning(f"API Resume: User {user_id} tried to resume, but no active timer state found.")
            return jsonify({'status': 'no_active_state', 'error': 'No active timer found on server to resume.'}), 404 # Not Found

        if not active_state.end_time:
            current_app.logger.error(f"API Resume: Active state for User {user_id} exists but has no end_time! Cannot resume.")
            db.session.delete(active_state); db.session.commit() # Clean up invalid state
            return jsonify({'error': 'Cannot resume timer due to inconsistent server state.'}), 500

        # --- Calculate and Update End Time ---
        original_end_time = active_state.end_time
        # Ensure original end time is timezone-aware (assume UTC if naive)
        if getattr(original_end_time, 'tzinfo', None) is None:
            original_end_time = original_end_time.replace(tzinfo=timezone.utc)

        # Calculate the new end time by adding the pause duration
        new_end_time = original_end_time + timedelta(milliseconds=pause_duration_ms)

        active_state.end_time = new_end_time
        db.session.commit()

        new_end_time_iso = new_end_time.isoformat()
        current_app.logger.info(f"API Resume: Successfully updated end time for User {user_id} to {new_end_time_iso}")

        # Respond with success and the *new* end time
        return jsonify({
            'status': 'resume_success',
            'new_end_time': new_end_time_iso # Send adjusted end time back to client
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Resume: Database error updating end time for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred during resume.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Resume: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred during resume.'}), 500


@main.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_chat():
    """API endpoint for the AI productivity assistant chat."""
    global openai_client, _openai_initialized

    if not current_app.config.get('FEATURE_CHAT_ENABLED', False):
        current_app.logger.warning(f"API Chat: Attempt by User {current_user.id} when chat feature is disabled.")
        return jsonify({'error': 'Chat feature is not configured or available.'}), 501

    if OpenAI and not _openai_initialized:
        api_key = current_app.config.get('OPENAI_API_KEY')
        if api_key:
            try:
                openai_client = OpenAI(api_key=api_key)
                current_app.logger.info("OpenAI client initialized successfully inside API route.")
            except Exception as e:
                current_app.logger.error(f"Failed to initialize OpenAI client inside API route: {e}")
                openai_client = None
        else:
             current_app.logger.warning("FEATURE_CHAT_ENABLED is True, but OPENAI_API_KEY is not set (checked in route).")
        _openai_initialized = True

    if not openai_client:
        if _openai_initialized:
             current_app.logger.error(f"API Chat: Attempt by User {current_user.id} but OpenAI client is unavailable (initialization failed or no key).")
        return jsonify({'error': 'Chat service client is not available.'}), 503


    data = request.get_json()
    if not data or 'prompt' not in data or 'dashboard_data' not in data:
         current_app.logger.warning(f"API Chat: Bad request from User {current_user.id}. Missing prompt or dashboard_data.")
         return jsonify({'error': 'Missing prompt or dashboard_data in request'}), 400

    user_prompt = data.get('prompt', '').strip()
    dashboard_data = data.get('dashboard_data', {})

    if not user_prompt:
         return jsonify({'error': 'Prompt cannot be empty.'}), 400

    current_app.logger.info(f"API Chat: User {current_user.id} prompt (truncated): '{user_prompt[:100]}...'")

    def get_data(key, default='N/A'):
        val = dashboard_data.get(key); return str(val) if val is not None else default
    user_points = "N/A"
    try:
        user = db.session.get(User, current_user.id)
        user_points = str(user.total_points) if user else "N/A"
    except Exception as e:
        current_app.logger.error(f"API Chat: Failed to get user points for context: {e}")

    context = f"""
You are a helpful and encouraging productivity assistant for a web app that uses the Pomodoro technique and a points system.
The user '{current_user.name}' (ID: {current_user.id}) is asking a question. Their current stats are:
- Total Points: {user_points}
- Total Focus Time (all time, minutes): {get_data('total_focus')}
- Total Break Time (all time, minutes): {get_data('total_break')}
- Total Pomodoro Sessions Completed (all time): {get_data('total_sessions')}
- Today's Focus Time (minutes, UTC): {get_data('today_focus')}
- Today's Sessions Completed (UTC): {get_data('today_sessions')}
- This Week's Focus Time (minutes, starting Monday UTC): {get_data('week_focus')}
- This Week's Sessions Completed (starting Monday UTC): {get_data('week_sessions')}

Please follow these instructions carefully:
1. Answer the user's question based *only* on the provided stats and general knowledge about the Pomodoro technique, time management, and interpreting simple productivity metrics (like points, session counts, focus time).
2. Be positive and encouraging in your tone.
3. Keep your responses concise and easy to understand (typically 1-4 sentences).
4. Do *not* invent data or statistics not provided above. If you don't have the information, say so.
5. If the question is unrelated to productivity, the Pomodoro technique, or interpreting their stats, politely decline to answer and gently redirect towards productivity topics.
6. Format your response using Markdown (e.g., bolding, lists) where it enhances clarity.
"""

    try:
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4o-mini", max_tokens=180, temperature=0.6, user=f"user-{current_user.id}"
        )
        ai_response = chat_completion.choices[0].message.content.strip()
        current_app.logger.info(f"API Chat: OpenAI response generated successfully for User {current_user.id}.")
        return jsonify({'response': ai_response})

    except Exception as e:
        current_app.logger.error(f"API Chat: Error calling OpenAI API for User {current_user.id}: {e}", exc_info=True)
        return jsonify({'error': 'Sorry, I encountered an issue contacting the AI service. Please try again later.'}), 500