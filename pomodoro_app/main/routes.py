# pomodoro_app/main/routes.py
# Handles user-facing HTML page routes for the main blueprint.

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app
)
from flask_login import login_required, current_user
from sqlalchemy import func # Keep func if used directly for dashboard stats
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta, timezone, date

# Import blueprint object, database instance, limiter, and models
from . import main # Import the blueprint registered in __init__.py
from pomodoro_app import db, limiter
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

# Import constants and helpers needed by these routes specifically
from .logic import MULTIPLIER_RULES, calculate_current_multiplier

# --- HTML Routes ---

@main.route('/')
@limiter.limit("10 per minute")
def index():
    """Handles the root URL. Redirects authenticated users."""
    if current_user.is_authenticated:
        try:
            active_state = db.session.get(ActiveTimerState, current_user.id)
            if active_state:
                 current_app.logger.debug(f"User {current_user.id} has active timer state, redirecting to timer page.")
                 return redirect(url_for('main.timer'))
            else:
                 current_app.logger.debug(f"User {current_user.id} has no active timer state, redirecting to dashboard.")
                 return redirect(url_for('main.dashboard'))
        except SQLAlchemyError as e:
             current_app.logger.error(f"Database error checking active timer for user {current_user.id} on index: {e}", exc_info=True)
             return redirect(url_for('main.dashboard')) # Fallback
        except Exception as e:
             current_app.logger.error(f"Unexpected error checking active timer for user {current_user.id} on index: {e}", exc_info=True)
             return redirect(url_for('main.dashboard')) # Fallback
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    """Displays the timer page with points and multiplier info."""
    user_id = current_user.id
    active_multiplier = 1.0
    total_points = 0
    active_state_info = None
    user = None

    try:
        user = db.session.get(User, user_id)
        if not user:
             current_app.logger.error(f"Timer Route: Could not find logged in user {user_id} in DB.")
             return redirect(url_for('auth.logout'))

        total_points = user.total_points
        active_state = db.session.get(ActiveTimerState, user_id)

        if active_state:
             active_multiplier = active_state.current_multiplier
             active_state_info = {
                  'phase': active_state.phase,
                  'endTime': active_state.end_time.isoformat(),
                  'workMins': active_state.work_duration_minutes,
                  'breakMins': active_state.break_duration_minutes,
                  'multiplier': active_state.current_multiplier
             }
             current_app.logger.debug(f"Timer Route: Found active state for User {user_id}. Phase: {active_state.phase}, Mult: {active_multiplier}")
        else:
             # Calculate potential multiplier for *next* session using the helper
             active_multiplier = calculate_current_multiplier(user, 0) # Pass 0 duration for potential calc
             current_app.logger.debug(f"Timer Route: No active state for User {user_id}. Potential next multiplier: {active_multiplier}")

    except SQLAlchemyError as e:
        current_app.logger.error(f"Timer Route: Database error loading data for User {user_id}: {e}", exc_info=True)
    except Exception as e:
         current_app.logger.error(f"Timer Route: Unexpected error for User {user_id}: {e}", exc_info=True)

    # Get points per minute from config
    points_per_min_config = current_app.config.get('POINTS_PER_MINUTE', 10)

    return render_template(
        'main/timer.html',
        total_points=total_points,
        active_multiplier=active_multiplier,
        multiplier_rules=MULTIPLIER_RULES, # Pass rules from logic.py
        active_state_info=active_state_info,
        # Pass config directly needed by the template itself
        config={'POINTS_PER_MINUTE': points_per_min_config}
    )

@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    """Displays user dashboard with session history and stats."""
    user_id = current_user.id
    current_app.logger.debug(f"Dashboard: Loading data for User {user_id}")
    user = None
    total_points = 0
    # Initialize stats to 0
    total_focus, total_break, total_sessions = 0, 0, 0
    today_focus, today_sessions = 0, 0
    week_focus, week_sessions = 0, 0
    aware_sessions = []

    try:
        user = db.session.get(User, user_id)
        if not user:
            current_app.logger.error(f"Dashboard: Could not find logged in user {user_id} in DB.")
            return redirect(url_for('auth.logout'))

        total_points = user.total_points

        # --- Aggregate Stat Calculations ---
        total_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user_id).scalar()
        total_break = db.session.query(func.coalesce(func.sum(PomodoroSession.break_duration), 0)).filter(PomodoroSession.user_id == user_id).scalar()
        total_sessions = db.session.query(func.count(PomodoroSession.id)).filter(PomodoroSession.user_id == user_id, PomodoroSession.work_duration > 0).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Overall Stats - Focus: {total_focus}, Break: {total_break}, Sessions: {total_sessions}, Points: {total_points}")

        # --- Time-based Stats (UTC) ---
        now_utc = datetime.now(timezone.utc)
        today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week_utc = today_start_utc - timedelta(days=now_utc.weekday())

        # Today's Stats
        today_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user_id, PomodoroSession.timestamp >= today_start_utc).scalar()
        today_sessions = db.session.query(func.count(PomodoroSession.id)).filter(PomodoroSession.user_id == user_id, PomodoroSession.work_duration > 0, PomodoroSession.timestamp >= today_start_utc).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Today Stats - Focus: {today_focus}, Sessions: {today_sessions}")

        # This Week's Stats
        week_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user_id, PomodoroSession.timestamp >= start_of_week_utc).scalar()
        week_sessions = db.session.query(func.count(PomodoroSession.id)).filter(PomodoroSession.user_id == user_id, PomodoroSession.work_duration > 0, PomodoroSession.timestamp >= start_of_week_utc).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Week Stats - Focus: {week_focus}, Sessions: {week_sessions}")

        # --- Fetch Session History ---
        sessions_from_db = db.session.query(PomodoroSession).filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).limit(100).all()
        current_app.logger.debug(f"Dashboard: Fetched {len(sessions_from_db)} session history entries for User {user_id}")

        # Ensure timezone awareness for display
        for sess in sessions_from_db:
            if sess.timestamp and getattr(sess.timestamp, 'tzinfo', None) is None:
                try: sess.timestamp = sess.timestamp.replace(tzinfo=timezone.utc)
                except Exception as tz_err: current_app.logger.error(f"Dashboard: Could not make timestamp tz-aware for session {sess.id}: {tz_err}")
            aware_sessions.append(sess)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Dashboard: Database error loading stats/history for User {user_id}: {e}", exc_info=True)
        # Stats already initialized to 0, total_points might be stale if user object fetched earlier
        total_points = user.total_points if user else 0
    except Exception as e:
         current_app.logger.error(f"Dashboard: Unexpected error loading data for User {user_id}: {e}", exc_info=True)
         total_points = user.total_points if user else 0

    chat_enabled = current_app.config.get('FEATURE_CHAT_ENABLED', False)
    current_app.logger.debug(f"Dashboard: Rendering for User {user_id}. Chat enabled: {chat_enabled}")

    return render_template('main/dashboard.html',
                           total_points=total_points,
                           total_focus=total_focus,
                           total_break=total_break,
                           total_sessions=total_sessions,
                           today_focus=today_focus,
                           today_sessions=today_sessions,
                           week_focus=week_focus,
                           week_sessions=week_sessions,
                           sessions=aware_sessions,
                           chat_enabled=chat_enabled)