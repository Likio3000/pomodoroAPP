# pomodoro_app/main/api_routes.py
"""
Handles all API endpoints for the main blueprint.
"""

import os
import tempfile
import uuid
import mimetypes
import time
from datetime import datetime, timedelta, timezone

from flask import request, jsonify, current_app, send_file, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from pomodoro_app.agent_config import load_personas

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    # Note: current_app may not be available at import time.
    # Logging of this issue is performed later in the code.

# Import blueprint object, database instance, limiter, and models
from . import main  # This is the blueprint registered in __init__.py
from pomodoro_app import db, limiter
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState, ChatMessage

# Import helper functions from logic.py
from .logic import (
    calculate_current_multiplier,
    update_streaks,
    MULTIPLIER_RULES,
)

# --- OpenAI Client (initialized at module level) ---
openai_client = None
_openai_initialized = False

# --- TTS AUDIO FILE DIRECTORY ---
AUDIO_TEMP_DIR = os.path.join(tempfile.gettempdir(), "pomodoro_agent_audio")
os.makedirs(AUDIO_TEMP_DIR, exist_ok=True)


def trim_chat_history(user_id, keep=15):
    """Remove oldest chat messages beyond the keep limit for a user."""
    try:
        old_ids = [
            mid
            for (mid,) in (
                db.session.query(ChatMessage.id)
                .filter_by(user_id=user_id)
                .order_by(ChatMessage.timestamp.desc())
                .offset(keep)
                .all()
            )
        ]
        if old_ids:
            ChatMessage.query.filter(ChatMessage.id.in_(old_ids)).delete(
                synchronize_session=False
            )
            db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"Chat history trim error for user {user_id}: {e}", exc_info=True
        )


def initialize_openai_client():
    """Initializes the OpenAI client if not already done."""
    global openai_client, _openai_initialized
    if OpenAI and not _openai_initialized:
        api_key = current_app.config.get('OPENAI_API_KEY')
        if api_key:
            try:
                openai_client = OpenAI(api_key=api_key)
                current_app.logger.info("OpenAI client initialized successfully.")
            except Exception as e:
                current_app.logger.error(f"Failed to initialize OpenAI client: {e}")
                openai_client = None
        else:
            current_app.logger.warning("FEATURE_CHAT_ENABLED is True, but OPENAI_API_KEY is not set.")
            openai_client = None
        _openai_initialized = True
    elif not OpenAI:
        current_app.logger.debug("OpenAI library not installed, skipping client initialization.")
        _openai_initialized = True


# --- API Endpoints ---

@main.route('/api/timer/state', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def api_get_timer_state():
    """Fetches the current timer state for the logged-in user."""
    user_id = current_user.id
    try:
        active_state = db.session.get(ActiveTimerState, user_id)
        if not active_state:
            current_app.logger.debug(f"API Timer State GET: No active state for User {user_id}")
            return jsonify({'active': False}), 200

        # Ensure datetimes are timezone-aware (assume UTC if naive)
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

        current_app.logger.debug(
            f"API Timer State GET: Found active state for User {user_id}: Phase {active_state.phase}, Ends {end_time_iso}"
        )
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
    """
    Signals the start/restart of a timer.
    Calculates the work multiplier and creates or updates an ActiveTimerState.
    """
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
        # Lock the user row for update
        user = db.session.query(User).filter_by(id=user_id).with_for_update().first()
        if not user:
            current_app.logger.error(f"API Start: Cannot find User {user_id} to start timer.")
            return jsonify({'error': 'User not found.'}), 500

        current_multiplier = calculate_current_multiplier(user, work_minutes, break_minutes)
        current_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if current_state:
            current_app.logger.info(
                f"API Start: Updating existing timer state for User {user_id}. New Mult: {current_multiplier}"
            )
            current_state.phase = 'work'
            current_state.start_time = now_utc
            current_state.end_time = end_time_utc
            current_state.work_duration_minutes = work_minutes
            current_state.break_duration_minutes = break_minutes
            current_state.current_multiplier = current_multiplier
        else:
            current_app.logger.info(
                f"API Start: Creating new timer state for User {user_id}. Mult: {current_multiplier}"
            )
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
        current_app.logger.debug(
            f"API Start: Timer state saved for User {user_id}. Phase: work, Mult: {current_multiplier}, Ends: {end_time_utc.isoformat()}"
        )
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
    """
    Completes a phase of the timer.
    Calculates and awards points based on the planned duration,
    updates user stats and streaks, and transitions the timer state.
    Automatically starts the next work session after a break.
    """
    data = request.get_json()
    if not data or 'phase_completed' not in data:
        current_app.logger.warning(f"API Complete: Missing phase_completed field from User {current_user.id}.")
        return jsonify({'error': 'Missing phase_completed field'}), 400

    phase_completed = data.get('phase_completed')
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)
    points_per_minute = current_app.config.get('POINTS_PER_MINUTE', 10)

    try:
        # Use with_for_update() for locking during the read-modify-write cycle
        user = db.session.query(User).filter_by(id=user_id).with_for_update().first()
        server_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if not user:
            current_app.logger.error(f"API Complete: Cannot find User {user_id} to complete phase.")
            return jsonify({'error': 'User not found.'}), 500

        if not server_state:
            current_app.logger.warning(
                f"API Complete: No active timer state found for User {user_id} during phase completion."
            )
            # Return current points even if state is missing
            return jsonify({'status': 'acknowledged_no_state', 'total_points': user.total_points}), 200

        current_app.logger.debug(
            f"API Complete: Processing '{phase_completed}' for User {user_id}. DB phase: '{server_state.phase}', "
            f"Current multiplier: {getattr(server_state, 'current_multiplier', 'N/A')}"
        )

        end_time = server_state.end_time
        if end_time is None:
            current_app.logger.error(f"API Complete: Timer state for User {user_id} has no end_time!")
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': 'Inconsistent timer state found on server.', 'total_points': user.total_points}), 500

        # Ensure timezone awareness
        if getattr(end_time, 'tzinfo', None) is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Allow completion within a grace period (e.g., 2 seconds)
        grace_period = timedelta(seconds=2)
        if now_utc < (end_time - grace_period):
            time_diff = end_time - now_utc
            current_app.logger.warning(
                f"API Complete: User {user_id} attempted to complete phase too early. Remaining: {int(time_diff.total_seconds())} seconds."
            )
            return jsonify({
                'error': f'Timer not finished yet! {int(time_diff.total_seconds())}s remaining.',
                'total_points': user.total_points # Return current points on early completion attempt
            }), 400

        # Check for phase mismatch, but prioritize server state
        if server_state.phase != phase_completed:
            current_app.logger.warning(
                f"API Complete: Phase mismatch for User {user_id} (client sent '{phase_completed}', DB is '{server_state.phase}'). Using DB phase."
            )
            phase_completed = server_state.phase # Correct the phase based on server state

        points_earned_this_phase = 0
        next_phase_status = 'unknown'
        new_total_points = user.total_points # Start with current points
        response_payload = {} # To hold extra data for specific responses

        if phase_completed == 'work':
            planned_work_duration = server_state.work_duration_minutes
            current_app.logger.info(
                f"API Complete: User {user_id} completed WORK phase (duration: {planned_work_duration} min)."
            )
            # Use the multiplier stored when the work phase started
            final_multiplier = getattr(server_state, 'current_multiplier', 1.0)
            if isinstance(points_per_minute, (int, float)) and points_per_minute >= 0:
                points_earned_this_phase = int(round(planned_work_duration * points_per_minute * final_multiplier))
            else:
                current_app.logger.error(f"API Complete: Invalid POINTS_PER_MINUTE ({points_per_minute}). Using 0 points.")
                points_earned_this_phase = 0

            new_total_points += points_earned_this_phase
            current_app.logger.info(
                f"API Complete: User {user_id} earned {points_earned_this_phase} points for work (Mult: {final_multiplier:.2f}). Total now: {new_total_points}"
            )
            # Update streaks and last session time only AFTER successful work completion
            update_streaks(user, now_utc)
            user.total_points = new_total_points # Update user's total points

            # Log the completed session
            try:
                work_start_time = server_state.start_time
                # Ensure timezone awareness for logging timestamp
                if work_start_time and getattr(work_start_time, 'tzinfo', None) is None:
                    work_start_time = work_start_time.replace(tzinfo=timezone.utc)
                log_entry = PomodoroSession(
                    user_id=user_id,
                    work_duration=planned_work_duration,
                    break_duration=server_state.break_duration_minutes, # Log planned break
                    points_earned=points_earned_this_phase,
                    timestamp=work_start_time or now_utc # Use start time if available, fallback to now
                )
                db.session.add(log_entry)
            except Exception as log_err:
                current_app.logger.error(
                    f"API Complete: Failed to log PomodoroSession for User {user_id}: {log_err}", exc_info=True
                )
                # Continue even if logging fails, points/streaks are more critical

            # Transition to break state
            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc
            server_state.end_time = break_end_time_utc
            # *** IMPORTANT: Preserve the multiplier that applied to the WORK we just completed. ***
            # Breaks inherit that multiplier when points are awarded at break completion.
            server_state.current_multiplier = final_multiplier
            current_app.logger.debug(
                f"API Complete: Timer state transitioned to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}. Inherited multiplier={final_multiplier:.2f}."
            )
            next_phase_status = 'break_started'
            response_payload['end_time'] = break_end_time_utc.isoformat() # Send break end time
            # Send multiplier so client display stays in sync during break.
            response_payload['active_multiplier'] = final_multiplier

            # NOTE: Points for the break will be awarded when the user (or auto-complete) ends the break phase.

        elif phase_completed == 'break':
            planned_break_duration = server_state.break_duration_minutes
            current_app.logger.info(
                f"API Complete: User {user_id} completed BREAK phase (duration: {planned_break_duration} min)."
            )
            # *** CHANGED: Award full rate × the multiplier from the *preceding work* phase. ***
            inherited_multiplier = getattr(server_state, 'current_multiplier', 1.0)
            if isinstance(points_per_minute, (int, float)) and points_per_minute >= 0:
                 points_earned_this_phase = int(round(planned_break_duration * points_per_minute * inherited_multiplier))
            else:
                 points_earned_this_phase = 0

            new_total_points += points_earned_this_phase
            current_app.logger.info(
                 f"API Complete: User {user_id} earned {points_earned_this_phase} points for break (Inherited mult={inherited_multiplier:.2f}). Total now: {new_total_points}"
            )
            user.total_points = new_total_points

            # --- START: Automatic Work Start Logic ---
            # Instead of deleting, update the state for the next work session
            work_minutes = server_state.work_duration_minutes
            # Recalculate multiplier based on streaks *before* the work session starts
            next_multiplier = calculate_current_multiplier(user, work_minutes, server_state.break_duration_minutes)
            work_end_time_utc = now_utc + timedelta(minutes=work_minutes)

            # Transition into NEW work phase with freshly computed multiplier.
            server_state.phase = 'work'
            server_state.start_time = now_utc
            server_state.end_time = work_end_time_utc
            server_state.current_multiplier = next_multiplier # Set multiplier for the upcoming work phase

            current_app.logger.debug(
                f"API Complete: Break finished. Automatically transitioning to WORK for User {user_id}. "
                f"New Mult: {next_multiplier:.2f}, Ends: {work_end_time_utc.isoformat()}."
            )
            next_phase_status = 'work_started' # New status for client
            response_payload['end_time'] = work_end_time_utc.isoformat()
            response_payload['active_multiplier'] = next_multiplier
            # --- END: Automatic Work Start Logic ---

        else:
            # Should not happen if phase_completed is corrected based on server_state
            current_app.logger.error(
                f"API Complete: Invalid phase '{phase_completed}' encountered despite checks for User {user_id}. Clearing state."
            )
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': f'Invalid phase specified: {phase_completed}', 'total_points': user.total_points}), 400

        # Commit all changes (user points, session log, active timer state update)
        db.session.commit()
        current_app.logger.info(
            f"API Complete: DB commit successful for User {user_id}. Status: {next_phase_status}, Total Points: {new_total_points}"
        )
        # Merge base response with specific payload
        final_response = {'status': next_phase_status, 'total_points': new_total_points}
        final_response.update(response_payload)
        return jsonify(final_response), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"API Complete: Database error during phase completion for User {current_user.id}: {e}", exc_info=True
        )
        # Try to fetch current points after rollback, if possible
        current_points_after_error = 0
        try:
            user_after_error = db.session.get(User, current_user.id)
            if user_after_error:
                current_points_after_error = user_after_error.total_points
        except Exception:
             pass # Ignore error during error handling
        return jsonify({'error': 'Database error processing phase completion.', 'total_points': current_points_after_error}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"API Complete: Unexpected error for User {current_user.id}: {e}", exc_info=True
        )
        current_points_after_error = 0
        try:
             user_after_error = db.session.get(User, current_user.id)
             if user_after_error:
                 current_points_after_error = user_after_error.total_points
        except Exception:
             pass # Ignore error during error handling
        return jsonify({'error': 'An unexpected server error occurred.', 'total_points': current_points_after_error}), 500


@main.route('/api/timer/reset', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_reset_timer():
    """Clears the active timer state on the server."""
    user_id = current_user.id
    current_app.logger.info(f"API Reset: Received reset request from User {user_id}")
    try:
        # Use with_for_update to lock the row during delete check
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()
        if active_state:
            db.session.delete(active_state)
            db.session.commit()
            current_app.logger.info(f"API Reset: Timer state cleared for User {user_id}")
            return jsonify({'status': 'reset_success'}), 200
        else:
            current_app.logger.info(f"API Reset: No active timer state found for User {user_id}")
            return jsonify({'status': 'no_state_to_reset'}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Reset: Database error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred during reset.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Reset: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred during reset.'}), 500


@main.route('/api/timer/pause', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_pause_timer():
    """Records the timestamp when a timer is paused."""
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)
    current_app.logger.info(f"API Pause: User {user_id} pausing at {now_utc.isoformat()}")
    try:
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()
        if not active_state:
            current_app.logger.warning(f"API Pause: No active timer state for User {user_id}")
            return jsonify({'status': 'no_active_state'}), 404

        active_state.pause_start_time = now_utc
        db.session.commit()

        current_app.logger.debug(
            f"API Pause: Stored pause_start_time={now_utc.isoformat()} for User {user_id}"
        )
        return jsonify({'status': 'pause_recorded'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Pause: Database error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred during pause.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Pause: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred during pause.'}), 500


@main.route('/api/timer/resume', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_resume_timer():
    """Resumes a paused timer and recalculates its end time on the server."""
    # Client may optionally send pause_duration_ms but we ignore it to avoid clock drift
    user_id = current_user.id
    now_utc = datetime.now(timezone.utc)
    current_app.logger.info(f"API Resume: User {user_id} resuming at {now_utc.isoformat()}")

    try:
        # Lock the state row for update
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()
        if not active_state:
            current_app.logger.warning(f"API Resume: No active timer state for User {user_id}")
            return jsonify({'status': 'no_active_state', 'error': 'No active timer found on server to resume.'}), 404 # Use 404

        if not active_state.end_time:
            current_app.logger.error(f"API Resume: Timer state for User {user_id} has no end_time. Cannot resume.")
            # Clean up inconsistent state
            db.session.delete(active_state)
            db.session.commit()
            return jsonify({'error': 'Cannot resume timer due to inconsistent server state.'}), 500

        pause_start_time = active_state.pause_start_time
        if not pause_start_time:
            current_app.logger.warning(
                f"API Resume: No pause_start_time stored for User {user_id}. Using existing end_time without adjustment."
            )
            new_end_time = active_state.end_time
            new_end_time_iso = new_end_time.isoformat()
            return jsonify({'status': 'resume_no_pause_found', 'new_end_time': new_end_time_iso}), 200

        if getattr(pause_start_time, 'tzinfo', None) is None:
            pause_start_time = pause_start_time.replace(tzinfo=timezone.utc)
        original_end_time = active_state.end_time
        if getattr(original_end_time, 'tzinfo', None) is None:
            original_end_time = original_end_time.replace(tzinfo=timezone.utc)

        remaining_duration = original_end_time - pause_start_time
        if remaining_duration.total_seconds() < 0:
            remaining_duration = timedelta(seconds=0)

        new_end_time = now_utc + remaining_duration
        active_state.start_time = now_utc
        active_state.end_time = new_end_time
        active_state.pause_start_time = None
        db.session.commit()

        new_end_time_iso = new_end_time.isoformat()
        current_app.logger.info(
            f"API Resume: Recomputed end time for User {user_id} to {new_end_time_iso} (remaining {remaining_duration})"
        )
        return jsonify({'status': 'resume_success', 'new_end_time': new_end_time_iso}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"API Resume: Database error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'Database error occurred during resume.'}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"API Resume: Unexpected error for User {user_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected server error occurred during resume.'}), 500


@main.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_chat():
    """
    Provides chat functionality for the AI productivity assistant.
    Supports agent personalities and generates TTS audio for the response
    ONLY IF requested by the user and enabled by server config.
    """
    initialize_openai_client()

    if not current_app.config.get('FEATURE_CHAT_ENABLED', False):
        current_app.logger.warning(f"API Chat: Chat feature disabled for User {current_user.id}.")
        abort(501, description='Chat feature is not configured or available.') # Pass message via description

    if not openai_client:
        current_app.logger.error(f"API Chat: OpenAI client unavailable for User {current_user.id}.")
        abort(503, description='Chat service client is not available.') # Pass message via description

    data = request.get_json()
    # --- Check for tts_enabled flag from request ---
    if not data or 'prompt' not in data or 'dashboard_data' not in data or 'tts_enabled' not in data:
        current_app.logger.warning(f"API Chat: Missing prompt, dashboard_data, or tts_enabled from User {current_user.id}.")
        return jsonify({'error': 'Missing prompt, dashboard_data, or tts_enabled flag in request'}), 400
    # --- END CHECK ---

    user_prompt = data.get('prompt', '').strip()
    if not user_prompt:
        return jsonify({'error': 'Prompt cannot be empty.'}), 400

    dashboard_data = data.get('dashboard_data', {})
    agent_type = data.get('agent_type', 'default')
    message_count = data.get('message_count')
    # --- Get user's TTS preference from request ---
    user_wants_tts = data.get('tts_enabled', False) # Default to False if missing/invalid
    if not isinstance(user_wants_tts, bool): user_wants_tts = False # Ensure boolean
    # --- END ---

    current_app.logger.info(f"API Chat: Processing prompt for User {current_user.id} (agent: {agent_type}, TTS requested: {user_wants_tts})")

    # Fetch necessary user data from DB instead of relying entirely on potentially stale dashboard_data
    try:
        user = db.session.get(User, current_user.id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404 # Or 500 if internal error

        user_points = str(user.total_points)

        # Example of getting fresh stats - adapt as needed for your context prompt
        total_focus_db = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user.id).scalar()
        total_sessions_db = db.session.query(func.count(PomodoroSession.id)).filter(PomodoroSession.user_id == user.id, PomodoroSession.work_duration > 0).scalar()

    except SQLAlchemyError as db_err:
        current_app.logger.error(f"API Chat: DB error fetching user data for {user.id}: {db_err}")
        return jsonify({'error': 'Could not retrieve user data for context.'}), 500


    # --- Load agent personalities and voices from configuration ---
    personas = load_personas()
    default = personas.get('default', {})
    persona_data = personas.get(agent_type, default)
    agent_persona = persona_data.get('prompt', default.get('prompt', ''))
    tts_voice = persona_data.get('voice', default.get('voice'))

    # --- Construct Context ---
    # Use fresh data fetched from DB where possible
    multiplier_lines = [
        f"- {rule['condition']}: +{rule['bonus']}"
        for rule in MULTIPLIER_RULES
        if rule.get('id') != 'base'
    ]
    multiplier_text = "Multipliers (additive to the base 1.0 rate):\n" + "\n".join(multiplier_lines)

    context = f"""
{agent_persona}
The user '{user.name}' (ID: {user.id}) is asking a question. Their current stats are:
- Total Points: {user_points}
- Total Focus Time (all time, minutes): {total_focus_db}
- Total Pomodoro Sessions Completed (all time): {total_sessions_db}
- Preferred Work Length: {user.preferred_work_minutes} minutes
- Productivity Goal: {user.productivity_goal or 'None set'}
{multiplier_text}
Please answer based solely on these stats and general knowledge about the Pomodoro technique.
Keep your response positive, concise (1–4 sentences), and use Markdown formatting.
If the question is unrelated to productivity, politely decline.
"""

    try:
        # --- Save user message and build history ---
        user_entry = ChatMessage(user_id=user.id, role="user", text=user_prompt)
        db.session.add(user_entry)
        db.session.commit()
        trim_chat_history(user.id, keep=15)

        history = (
            ChatMessage.query.filter_by(user_id=user.id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(10)
            .all()
        )
        history = list(reversed(history))
        messages = [{"role": msg.role, "content": msg.text} for msg in history]
        messages.insert(0, {"role": "system", "content": context})

        chat_completion = openai_client.chat.completions.create(
            messages=messages,
            model="gpt-4o-mini",
            max_tokens=180,
            temperature=0.6,
            user=f"user-{user.id}"
        )
        ai_response = chat_completion.choices[0].message.content.strip()
        current_app.logger.info(f"API Chat: OpenAI response generated for User {user.id}.")

        db.session.add(ChatMessage(user_id=user.id, role="assistant", text=ai_response))
        db.session.commit()
        trim_chat_history(user.id, keep=15)

        # --- TTS Generation (Conditional) ---
        audio_url = None
        server_tts_enabled = current_app.config.get('TTS_ENABLED', True) # Check server config

        # Check BOTH server config AND user request before generating TTS
        if server_tts_enabled and user_wants_tts:
            if ai_response: # Only generate TTS if there's a response
                try:
                    tts_response = openai_client.audio.speech.create(
                        model="tts-1", # Or tts-1-hd
                        voice=tts_voice,
                        input=ai_response
                    )
                    # Generate a unique filename
                    audio_filename = f"agent_{uuid.uuid4().hex}.mp3"
                    audio_path = os.path.join(AUDIO_TEMP_DIR, audio_filename)

                    # Stream the audio content to the temporary file.
                    tts_response.stream_to_file(audio_path)

                    # Generate the URL for the client to fetch the audio
                    audio_url = url_for('main.serve_agent_audio', filename=audio_filename, _external=False) # Use relative URL
                    current_app.logger.info(f"API Chat: TTS audio generated for User {user.id} at {audio_url} (User requested).")

                except Exception as tts_e:
                    current_app.logger.error(f"API Chat: Error generating TTS audio for User {user.id}: {tts_e}", exc_info=True)
                    audio_url = None # Ensure audio_url is None on TTS error
            else:
                current_app.logger.info(f"API Chat: Empty AI response for User {user.id}; skipping TTS generation.")
        elif server_tts_enabled and not user_wants_tts:
            # Log that TTS was skipped due to user preference
            current_app.logger.info(f"API Chat: User {user.id} disabled TTS via toggle for this request. Skipping TTS generation.")
        else: # server_tts_enabled is False
            # Log that TTS is disabled globally
             current_app.logger.info(f"API Chat: TTS is disabled by server configuration. Skipping TTS generation for User {user.id}.")

        # --- Return Response ---
        return jsonify({'response': ai_response, 'audio_url': audio_url}) # audio_url will be null if TTS wasn't generated

    except Exception as e:
        # Catch potential OpenAI API errors or other issues
        current_app.logger.error(f"API Chat: Error during OpenAI API call or processing for User {user.id}: {e}", exc_info=True)
        return jsonify({'error': 'Sorry, I encountered an issue contacting the AI service. Please try again later.'}), 500


@main.route('/api/agent_audio/<path:filename>')
@login_required
@limiter.limit("3 per minute") # Limit audio fetches
def serve_agent_audio(filename):
    """Serves TTS audio files for agent chat, ensuring safe file access."""
    # Basic security checks: prevent path traversal
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        current_app.logger.warning(f"Audio access attempt blocked (path traversal): {filename} by User {current_user.id}")
        return abort(404)

    # Construct the full path and normalize it
    audio_path = os.path.join(AUDIO_TEMP_DIR, filename)
    audio_path = os.path.abspath(audio_path) # Get absolute path

    # Security check: ensure the final path is still within the intended directory
    if not audio_path.startswith(os.path.abspath(AUDIO_TEMP_DIR)):
        current_app.logger.error(f"Audio file path escape attempt: {audio_path} by User {current_user.id}")
        return abort(404) # Not Found - don't reveal directory structure

    # Check if the file exists
    if not os.path.isfile(audio_path):
        current_app.logger.error(f"Agent audio file not found: {audio_path} requested by User {current_user.id}")
        return abort(404)

    # Serve the file
    current_app.logger.debug(f"Serving agent audio file: {audio_path} to User {current_user.id}")
    mimetype = mimetypes.guess_type(audio_path)[0] or 'audio/mpeg' # Guess mimetype or default
    # Consider adding cache control headers if needed
    return send_file(audio_path, mimetype=mimetype, as_attachment=False) # Serve inline


def cleanup_old_agent_audio_files(max_age_seconds=3600):
    """
    Removes agent audio files older than max_age_seconds from AUDIO_TEMP_DIR.
    This function can be scheduled to run periodically (e.g., via APScheduler or cron).
    """
    if not os.path.exists(AUDIO_TEMP_DIR):
        return # Directory doesn't exist, nothing to clean
    try:
        now = time.time()
        cleaned_count = 0
        error_count = 0
        # List files safely
        for fname in os.listdir(AUDIO_TEMP_DIR):
            fpath = os.path.join(AUDIO_TEMP_DIR, fname)
            try:
                # Check if it's a file and if it's old enough
                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                    os.remove(fpath)
                    cleaned_count += 1
            except FileNotFoundError:
                 pass # File might have been deleted between listdir and getmtime/remove
            except OSError as e: # Catch permission errors etc.
                error_count += 1
                # Log specific file error but continue cleanup
                current_app.logger.error(f"Error removing old audio file {fpath}: {e}")
            except Exception as e: # Catch unexpected errors
                 error_count += 1
                 current_app.logger.error(f"Unexpected error cleaning up audio file {fpath}: {e}")

        if cleaned_count > 0 or error_count > 0:
            current_app.logger.info(
                f"Audio cleanup complete: Removed {cleaned_count} old files, encountered {error_count} errors."
            )
        else:
             current_app.logger.debug("Audio cleanup ran: No old files found or removed.")
    except Exception as e:
        # Log error if the cleanup process itself fails (e.g., listing directory)
        current_app.logger.error(f"Error during audio cleanup process: {e}")