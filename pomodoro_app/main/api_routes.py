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

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    # Note: current_app may not be available at import time.
    # Logging of this issue is performed later in the code.

# Import blueprint object, database instance, limiter, and models
from . import main  # This is the blueprint registered in __init__.py
from pomodoro_app import db, limiter
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

# Import helper functions from logic.py
from .logic import calculate_current_multiplier, update_streaks

# --- OpenAI Client (initialized at module level) ---
openai_client = None
_openai_initialized = False

# --- TTS AUDIO FILE DIRECTORY ---
AUDIO_TEMP_DIR = os.path.join(tempfile.gettempdir(), "pomodoro_agent_audio")
os.makedirs(AUDIO_TEMP_DIR, exist_ok=True)


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

        current_multiplier = calculate_current_multiplier(user, work_minutes)
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
        user = db.session.query(User).filter_by(id=user_id).with_for_update().first()
        server_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()

        if not user:
            current_app.logger.error(f"API Complete: Cannot find User {user_id} to complete phase.")
            return jsonify({'error': 'User not found.'}), 500

        if not server_state:
            current_app.logger.warning(
                f"API Complete: No active timer state found for User {user_id} during phase completion."
            )
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

        if getattr(end_time, 'tzinfo', None) is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        grace_period = timedelta(seconds=2)
        if now_utc < (end_time - grace_period):
            time_diff = end_time - now_utc
            current_app.logger.warning(
                f"API Complete: User {user_id} attempted to complete phase too early. Remaining: {int(time_diff.total_seconds())} seconds."
            )
            return jsonify({
                'error': f'Timer not finished yet! {int(time_diff.total_seconds())}s remaining.',
                'total_points': user.total_points
            }), 400

        # If there is a phase mismatch, log and continue with the DB phase.
        if server_state.phase != phase_completed:
            current_app.logger.warning(
                f"API Complete: Phase mismatch for User {user_id} (client sent '{phase_completed}', DB is '{server_state.phase}')."
            )
            phase_completed = server_state.phase

        points_earned_this_phase = 0
        next_phase_status = 'unknown'
        new_total_points = user.total_points

        if phase_completed == 'work':
            planned_work_duration = server_state.work_duration_minutes
            current_app.logger.info(
                f"API Complete: User {user_id} completed WORK phase (duration: {planned_work_duration} min)."
            )
            final_multiplier = calculate_current_multiplier(user, planned_work_duration)
            if abs(final_multiplier - server_state.current_multiplier) > 0.01:
                current_app.logger.info(
                    f"API Complete: Multiplier updated for User {user.id} from {server_state.current_multiplier:.2f} to {final_multiplier:.2f}."
                )
            if isinstance(points_per_minute, (int, float)) and points_per_minute >= 0:
                points_earned_this_phase = int(round(planned_work_duration * points_per_minute * final_multiplier))
            else:
                current_app.logger.error(f"API Complete: Invalid POINTS_PER_MINUTE ({points_per_minute}).")
            new_total_points += points_earned_this_phase
            current_app.logger.info(
                f"API Complete: User {user_id} earned {points_earned_this_phase} points for work. Total now: {new_total_points}"
            )
            update_streaks(user, now_utc)
            user.total_points = new_total_points

            try:
                work_start_time = server_state.start_time
                if work_start_time and getattr(work_start_time, 'tzinfo', None) is None:
                    work_start_time = work_start_time.replace(tzinfo=timezone.utc)
                log_entry = PomodoroSession(
                    user_id=user_id,
                    work_duration=planned_work_duration,
                    break_duration=server_state.break_duration_minutes,
                    points_earned=points_earned_this_phase,
                    timestamp=work_start_time
                )
                db.session.add(log_entry)
            except Exception as log_err:
                current_app.logger.error(
                    f"API Complete: Failed to log PomodoroSession for User {user_id}: {log_err}", exc_info=True
                )

            # Transition to break phase.
            break_minutes = server_state.break_duration_minutes
            break_end_time_utc = now_utc + timedelta(minutes=break_minutes)
            server_state.phase = 'break'
            server_state.start_time = now_utc
            server_state.end_time = break_end_time_utc
            server_state.current_multiplier = 1.0
            current_app.logger.debug(
                f"API Complete: Timer state transitioned to BREAK for User {user_id}, ending at {break_end_time_utc.isoformat()}."
            )
            next_phase_status = 'break_started'

        elif phase_completed == 'break':
            planned_break_duration = server_state.break_duration_minutes
            current_app.logger.info(
                f"API Complete: User {user_id} completed BREAK phase (duration: {planned_break_duration} min)."
            )
            if isinstance(points_per_minute, (int, float)) and points_per_minute >= 0:
                points_earned_this_phase = int(round(planned_break_duration * points_per_minute))
            else:
                current_app.logger.error(f"API Complete: Invalid POINTS_PER_MINUTE ({points_per_minute}).")
            new_total_points += points_earned_this_phase
            user.total_points = new_total_points
            current_app.logger.info(
                f"API Complete: User {user_id} earned {points_earned_this_phase} points for break. Total now: {new_total_points}"
            )
            db.session.delete(server_state)
            next_phase_status = 'session_complete'

        else:
            current_app.logger.error(
                f"API Complete: Invalid phase '{phase_completed}' received for User {user_id}. Clearing state."
            )
            db.session.delete(server_state)
            db.session.commit()
            return jsonify({'error': f'Invalid phase specified: {phase_completed}', 'total_points': user.total_points}), 400

        db.session.commit()
        current_app.logger.info(
            f"API Complete: Updated state for User {user_id}. Status: {next_phase_status}, Total Points: {new_total_points}"
        )
        return jsonify({'status': next_phase_status, 'total_points': new_total_points}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"API Complete: Database error during phase completion for User {user_id}: {e}", exc_info=True
        )
        current_points = 0
        try:
            user_after_error = db.session.get(User, user_id)
            current_points = user_after_error.total_points if user_after_error else 0
        except Exception:
            pass
        return jsonify({'error': 'Database error processing phase completion.', 'total_points': current_points}), 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"API Complete: Unexpected error for User {user_id}: {e}", exc_info=True
        )
        current_points = 0
        try:
            user_after_error = db.session.get(User, user_id)
            current_points = user_after_error.total_points if user_after_error else 0
        except Exception:
            pass
        return jsonify({'error': 'An unexpected server error occurred.', 'total_points': current_points}), 500


@main.route('/api/timer/reset', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_reset_timer():
    """Clears the active timer state on the server."""
    user_id = current_user.id
    current_app.logger.info(f"API Reset: Received reset request from User {user_id}")
    try:
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


@main.route('/api/timer/resume', methods=['POST'])
@login_required
@limiter.limit("15 per minute")
def api_resume_timer():
    """Adjusts the timer's end time on the server after a client pause."""
    data = request.get_json()
    if not data or 'pause_duration_ms' not in data:
        current_app.logger.warning(f"API Resume: Missing pause_duration_ms from User {current_user.id}")
        return jsonify({'error': 'Missing pause duration information'}), 400

    try:
        pause_duration_ms = int(data['pause_duration_ms'])
        if pause_duration_ms < 0:
            raise ValueError("Pause duration cannot be negative.")
    except (ValueError, TypeError):
        current_app.logger.warning(
            f"API Resume: Invalid pause_duration_ms from User {current_user.id}: {data.get('pause_duration_ms')}"
        )
        return jsonify({'error': 'Invalid pause duration value'}), 400

    user_id = current_user.id
    current_app.logger.info(f"API Resume: User {user_id} resuming. Adjusting end time by {pause_duration_ms}ms.")
    try:
        active_state = db.session.query(ActiveTimerState).filter_by(user_id=user_id).with_for_update().first()
        if not active_state:
            current_app.logger.warning(f"API Resume: No active timer state for User {user_id}")
            return jsonify({'status': 'no_active_state', 'error': 'No active timer found on server to resume.'}), 404

        if not active_state.end_time:
            current_app.logger.error(f"API Resume: Timer state for User {user_id} has no end_time. Cannot resume.")
            db.session.delete(active_state)
            db.session.commit()
            return jsonify({'error': 'Cannot resume timer due to inconsistent server state.'}), 500

        original_end_time = active_state.end_time
        if getattr(original_end_time, 'tzinfo', None) is None:
            original_end_time = original_end_time.replace(tzinfo=timezone.utc)

        new_end_time = original_end_time + timedelta(milliseconds=pause_duration_ms)
        active_state.end_time = new_end_time
        db.session.commit()

        new_end_time_iso = new_end_time.isoformat()
        current_app.logger.info(f"API Resume: Updated end time for User {user_id} to {new_end_time_iso}")
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
    Supports agent personalities and generates TTS audio for the response.
    """
    initialize_openai_client()

    if not current_app.config.get('FEATURE_CHAT_ENABLED', False):
        current_app.logger.warning(f"API Chat: Chat feature disabled for User {current_user.id}.")
        return jsonify({'error': 'Chat feature is not configured or available.'}), 501

    if not openai_client:
        current_app.logger.error(f"API Chat: OpenAI client unavailable for User {current_user.id}.")
        return jsonify({'error': 'Chat service client is not available.'}), 503

    data = request.get_json()
    if not data or 'prompt' not in data or 'dashboard_data' not in data:
        current_app.logger.warning(f"API Chat: Missing prompt or dashboard_data from User {current_user.id}.")
        return jsonify({'error': 'Missing prompt or dashboard_data in request'}), 400

    user_prompt = data.get('prompt', '').strip()
    if not user_prompt:
        return jsonify({'error': 'Prompt cannot be empty.'}), 400

    dashboard_data = data.get('dashboard_data', {})
    agent_type = data.get('agent_type', 'default')

    current_app.logger.info(f"API Chat: Processing prompt for User {current_user.id} (agent: {agent_type})")

    def get_data(key, default='N/A'):
        val = dashboard_data.get(key)
        return str(val) if val is not None and val != '' else default

    user_points = str(getattr(current_user, 'total_points', 'N/A'))

    # Define agent personalities and corresponding TTS voices
    agent_prompts = {
        "motivator": "You are a motivating productivity coach. Always encourage the user, celebrate their wins, and offer positive reinforcement.",
        "coach": "You are a wise productivity coach. Offer practical advice and help the user reflect on their habits.",
        "default": "You are a helpful and encouraging productivity assistant for a web app that uses the Pomodoro technique and a points system."
    }
    agent_voices = {
        "motivator": "nova",
        "coach": "shimmer",
        "default": "alloy"
    }
    agent_persona = agent_prompts.get(agent_type, agent_prompts['default'])
    tts_voice = agent_voices.get(agent_type, agent_voices['default'])

    context = f"""
{agent_persona}
The user '{current_user.name}' (ID: {current_user.id}) is asking a question. Their current stats are:
- Total Points: {user_points}
- Total Focus Time (all time, minutes): {get_data('total_focus')}
- Total Break Time (all time, minutes): {get_data('total_break')}
- Total Pomodoro Sessions Completed (all time): {get_data('total_sessions')}
- Today's Focus Time (minutes, UTC): {get_data('today_focus')}
- Today's Sessions Completed (UTC): {get_data('today_sessions')}
- This Week's Focus Time (minutes, starting Monday UTC): {get_data('week_focus')}
- This Week's Sessions Completed (starting Monday UTC): {get_data('week_sessions')}
Please answer based solely on these stats and general knowledge about the Pomodoro technique.
Keep your response positive, concise (1–4 sentences), and use Markdown formatting.
If the question is unrelated to productivity, politely decline.
"""

    try:
        chat_completion = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-4o-mini",
            max_tokens=180,
            temperature=0.6,
            user=f"user-{current_user.id}"
        )
        ai_response = chat_completion.choices[0].message.content.strip()
        current_app.logger.info(f"API Chat: OpenAI response generated for User {current_user.id}.")

        audio_url = None
        if ai_response:
            try:
                tts_response = openai_client.audio.speech.create(
                    model="tts-1",
                    voice=tts_voice,
                    input=ai_response
                )
                audio_filename = f"agent_{uuid.uuid4().hex}.mp3"
                audio_path = os.path.join(AUDIO_TEMP_DIR, audio_filename)
                # Stream the audio content to file.
                tts_response.stream_to_file(audio_path)
                audio_url = url_for('main.serve_agent_audio', filename=audio_filename, _external=False)
                current_app.logger.info(f"API Chat: TTS audio generated for User {current_user.id} at {audio_url}.")
            except Exception as tts_e:
                current_app.logger.error(f"API Chat: Error generating TTS audio: {tts_e}", exc_info=True)
                audio_url = None
        else:
            current_app.logger.info(f"API Chat: Empty AI response for User {current_user.id}; skipping TTS generation.")

        return jsonify({'response': ai_response, 'audio_url': audio_url})
    except Exception as e:
        current_app.logger.error(f"API Chat: Error during OpenAI API call for User {current_user.id}: {e}", exc_info=True)
        return jsonify({'error': 'Sorry, I encountered an issue contacting the AI service. Please try again later.'}), 500


@main.route('/api/agent_audio/<path:filename>')
@login_required
@limiter.limit("30 per minute")
def serve_agent_audio(filename):
    """Serves TTS audio files for agent chat, ensuring safe file access."""
    # Prevent directory traversal.
    if '..' in filename or filename.startswith('/'):
        current_app.logger.warning(f"Audio access attempt blocked: {filename}")
        return abort(404)
    audio_path = os.path.join(AUDIO_TEMP_DIR, filename)
    audio_path = os.path.abspath(audio_path)
    if not audio_path.startswith(os.path.abspath(AUDIO_TEMP_DIR)):
        current_app.logger.error(f"Audio file path escape attempt: {audio_path}")
        return abort(404)
    if not os.path.isfile(audio_path):
        current_app.logger.error(f"Agent audio file not found: {audio_path}")
        return abort(404)
    current_app.logger.debug(f"Serving agent audio file: {audio_path}")
    mimetype = mimetypes.guess_type(audio_path)[0] or 'audio/mpeg'
    return send_file(audio_path, mimetype=mimetype)


def cleanup_old_agent_audio_files(max_age_seconds=3600):
    """
    Removes agent audio files older than max_age_seconds from AUDIO_TEMP_DIR.
    This function can be scheduled to run periodically.
    """
    if not os.path.exists(AUDIO_TEMP_DIR):
        return
    try:
        now = time.time()
        cleaned_count = 0
        error_count = 0
        for fname in os.listdir(AUDIO_TEMP_DIR):
            fpath = os.path.join(AUDIO_TEMP_DIR, fname)
            try:
                if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > max_age_seconds:
                    os.remove(fpath)
                    cleaned_count += 1
            except Exception as e:
                error_count += 1
                current_app.logger.error(f"Error cleaning up audio file {fpath}: {e}")
        current_app.logger.info(
            f"Audio cleanup complete: Removed {cleaned_count} files, encountered {error_count} errors."
        )
    except Exception as e:
        current_app.logger.error(f"Error during audio cleanup: {e}")
