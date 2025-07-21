# pomodoro_app/main/routes.py

from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for,
    session, current_app, flash, abort
)
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta, timezone, date

# --- app / DB objects ---------------------------------------------------------
from . import main                           # The blueprint created in __init__.py
from pomodoro_app import db, limiter
from pomodoro_app.models import (
    User, PomodoroSession, ActiveTimerState, ChatMessage   # <- NO Message import
)
from pomodoro_app.forms import SettingsForm

# --- helpers ------------------------------------------------------------------
from .logic import (
    MULTIPLIER_RULES, calculate_current_multiplier, get_active_multiplier_rules
)

# --- HTML Routes ---

@main.route('/')
@limiter.limit("10 per minute")
def index():
    """Root page: redirect logged-in users to dashboard or timer."""
    if current_user.is_authenticated:
        try:
            active_state = db.session.get(ActiveTimerState, current_user.id)
            return redirect(url_for('main.timer' if active_state else 'main.dashboard'))
        except Exception:
            return redirect(url_for('main.dashboard'))

    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    """Displays the timer page with points and multiplier info."""
    user_id = current_user.id
    active_multiplier = 1.0
    total_points = 0
    user = None
    active_rule_ids = set() # Initialize empty set for active rules
    relevant_work_duration = 0 # Default for idle state

    try:
        user = db.session.get(User, user_id)
        if not user:
             current_app.logger.error(f"Timer Route: Could not find logged in user {user_id} in DB.")
             return redirect(url_for('auth.logout')) # Log out if user record missing

        total_points = user.total_points
        active_state = db.session.get(ActiveTimerState, user_id) # Get current state

        if active_state:
             # Use the multiplier stored in the state for the current phase
             active_multiplier = getattr(active_state, 'current_multiplier', 1.0)
             # Determine the relevant work duration for calculating *active* rules
             # Use work_duration_minutes regardless of phase (work/break) as that's what multipliers apply to
             relevant_work_duration = active_state.work_duration_minutes
             current_app.logger.debug(f"Timer Route: Found active state for User {user_id}. Phase: {active_state.phase}. Multiplier: {active_multiplier}. Relevant duration for rules: {relevant_work_duration}")
        else:
            # Calculate potential multiplier for *next* session using the helper
            # Use 0 duration for potential calculation to avoid showing duration bonus before start
            relevant_work_duration = 0
            active_multiplier = calculate_current_multiplier(user, relevant_work_duration, 0)
            current_app.logger.debug(
                f"Timer Route: No active state for User {user_id}. Potential next multiplier: {active_multiplier}. Relevant duration for rules: {relevant_work_duration}"
            )

        # Call the function to get the set of active rule IDs based on current user state and the relevant duration
        active_rule_ids = get_active_multiplier_rules(user, relevant_work_duration, getattr(active_state, 'break_duration_minutes', 0))

    except SQLAlchemyError as e:
        current_app.logger.error(f"Timer Route: Database error loading data for User {user_id}: {e}", exc_info=True)
        # Attempt to get points even on error if user object was fetched earlier
        total_points = getattr(user, 'total_points', 0)
        # Keep active_rule_ids empty on error
    except Exception as e:
         current_app.logger.error(f"Timer Route: Unexpected error for User {user_id}: {e}", exc_info=True)
         total_points = getattr(user, 'total_points', 0)
         # Keep active_rule_ids empty on error

    # Get points per minute from config
    points_per_min_config = current_app.config.get('POINTS_PER_MINUTE', 10)

    return render_template(
        'main/timer.html',
        total_points=total_points,
        active_multiplier=active_multiplier,
        multiplier_rules=MULTIPLIER_RULES, # Pass rules definitions
        active_rule_ids=active_rule_ids, # Pass the set of active rule IDs
        config={'POINTS_PER_MINUTE': points_per_min_config} # Pass config needed by template
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
    today_focus, today_sessions, today_points = 0, 0, 0
    week_focus, week_sessions, week_points = 0, 0, 0
    aware_sessions = [] # Initialize as empty list

    try:
        user = db.session.get(User, user_id)
        if not user:
            current_app.logger.error(f"Dashboard: Could not find logged in user {user_id} in DB.")
            return redirect(url_for('auth.logout'))

        total_points = user.total_points

        # --- Aggregate Stat Calculations ---
        # Use coalesce to handle cases where sum might return None (no sessions)
        total_focus = db.session.query(func.coalesce(func.sum(PomodoroSession.work_duration), 0)).filter(PomodoroSession.user_id == user_id).scalar()
        total_break = db.session.query(func.coalesce(func.sum(PomodoroSession.break_duration), 0)).filter(PomodoroSession.user_id == user_id).scalar()
        # Count only sessions where work was done (break-only sessions shouldn't count)
        total_sessions = db.session.query(func.count(PomodoroSession.id)).filter(PomodoroSession.user_id == user_id, PomodoroSession.work_duration > 0).scalar()
        current_app.logger.debug(f"Dashboard: User {user_id} Overall Stats - Focus: {total_focus}, Break: {total_break}, Sessions: {total_sessions}, Points: {total_points}")

        # --- Time-based Stats (UTC) ---
        now_utc = datetime.now(timezone.utc)
        # Start of today in UTC
        today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        # Start of the week (assuming Monday is day 0) in UTC
        start_of_week_utc = today_start_utc - timedelta(days=now_utc.weekday())

        # Today's Stats (Sessions started today UTC)
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

        # This Week's Stats (Sessions started this week UTC)
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

        # --- Points for Today and This Week ---
        today_points = db.session.query(
            func.coalesce(func.sum(PomodoroSession.points_earned), 0)
        ).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.timestamp >= today_start_utc
        ).scalar()

        week_points = db.session.query(
            func.coalesce(func.sum(PomodoroSession.points_earned), 0)
        ).filter(
            PomodoroSession.user_id == user_id,
            PomodoroSession.timestamp >= start_of_week_utc
        ).scalar()

        current_app.logger.debug(
            f"Dashboard: User {user_id} Points - Today: {today_points}, Week: {week_points}"
        )

        # --- Fetch Session History (Limit results for performance) ---
        sessions_from_db = db.session.query(PomodoroSession).filter_by(user_id=user_id).order_by(PomodoroSession.timestamp.desc()).limit(100).all()
        current_app.logger.debug(f"Dashboard: Fetched {len(sessions_from_db)} session history entries for User {user_id}")

        # Ensure timezone awareness for display (Handle potential naive datetimes from DB)
        for sess in sessions_from_db:
            if sess.timestamp and getattr(sess.timestamp, 'tzinfo', None) is None:
                try:
                    # Assume stored naive datetimes are UTC
                    sess.timestamp = sess.timestamp.replace(tzinfo=timezone.utc)
                except Exception as tz_err:
                    current_app.logger.error(f"Dashboard: Could not make timestamp tz-aware for session {sess.id}: {tz_err}")
                    # Optionally handle the error, e.g., skip the session or mark it
            aware_sessions.append(sess) # Append even if tz conversion failed, JS can show raw ISO

    except SQLAlchemyError as e:
        current_app.logger.error(f"Dashboard: Database error loading stats/history for User {user_id}: {e}", exc_info=True)
        # Stats already initialized to 0, total_points might be stale if user object fetched earlier
        total_points = getattr(user, 'total_points', 0) # Safely get points if user exists
    except Exception as e:
         current_app.logger.error(f"Dashboard: Unexpected error loading data for User {user_id}: {e}", exc_info=True)
         total_points = getattr(user, 'total_points', 0) # Safely get points if user exists

    chat_enabled = current_app.config.get('FEATURE_CHAT_ENABLED', False)
    current_app.logger.debug(f"Dashboard: Rendering for User {user_id}. Chat enabled: {chat_enabled}")

    sessions_data = [
        {
            'timestamp': sess.timestamp.isoformat(timespec='seconds') if sess.timestamp else '',
            'work_duration': sess.work_duration,
            'break_duration': sess.break_duration,
            'points_earned': sess.points_earned or 0,
        }
        for sess in aware_sessions
    ]


    return render_template('main/dashboard.html',
                           total_points=total_points,
                           total_focus=total_focus,
                           total_break=total_break,
                           total_sessions=total_sessions,
                           today_focus=today_focus,
                           today_sessions=today_sessions,
                           today_points=today_points,
                           week_focus=week_focus,
                           week_sessions=week_sessions,
                           week_points=week_points,
                           sessions=aware_sessions,  # For table display
                           sessions_data=sessions_data,  # JSON-serializable list
                           chat_enabled=chat_enabled)


@main.route('/leaderboard')
def leaderboard():
    """Display leaderboard of users ordered by points."""
    try:
        users = db.session.query(User).order_by(User.total_points.desc()).limit(10).all()
    except SQLAlchemyError as e:
        current_app.logger.error(f"Leaderboard: DB error: {e}", exc_info=True)
        users = []
    return render_template('main/leaderboard.html', users=users)


@main.route('/mydata')
@login_required
def my_data():
    """Show the user’s stored chat messages."""
    try:
        messages = (ChatMessage.query
                               .filter_by(user_id=current_user.id)
                               .order_by(ChatMessage.timestamp.asc())
                               .all())
    except SQLAlchemyError as e:
        current_app.logger.error(f"MyData: DB error for user {current_user.id}: {e}")
        messages = []

    return render_template('main/my_data.html', messages=messages)



@main.route('/mydata/delete_pair/<int:message_id>', methods=['POST'])
@login_required
def delete_message_pair(message_id):
    """Delete a user message and the next assistant message."""
    msg = ChatMessage.query.get_or_404(message_id)

    if msg.user_id != current_user.id:
        abort(403)

    if msg.role != 'user':
        flash('Can only delete pairs starting from a user message.', 'error')
        return redirect(url_for('main.my_data'))

    try:
        next_msg = (
            ChatMessage.query
            .filter(ChatMessage.user_id == current_user.id,
                    ChatMessage.timestamp > msg.timestamp)
            .order_by(ChatMessage.timestamp.asc())
            .first()
        )
        if next_msg and next_msg.role == 'assistant':
            db.session.delete(next_msg)
        db.session.delete(msg)
        db.session.commit()
        flash('Message pair deleted.', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"MyData: DB error deleting pair starting with {message_id}: {e}")
        flash('Database error; message pair not deleted.', 'error')

    return redirect(url_for('main.my_data'))


@main.route('/mydata/delete_all', methods=['POST'])
@login_required
def delete_all_messages():
    """Delete all chat history for the current user."""
    try:
        ChatMessage.query.filter_by(user_id=current_user.id).delete(synchronize_session=False)
        db.session.commit()
        flash('All chat history deleted.', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(
            f"MyData: DB error deleting all messages for user {current_user.id}: {e}"
        )
        flash('Database error; messages not deleted.', 'error')

    return redirect(url_for('main.my_data'))


@main.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Edit AI profile and productivity preferences."""
    form = SettingsForm(obj=current_user)
    if form.validate_on_submit():
        current_user.preferred_work_minutes = form.preferred_work_minutes.data
        current_user.productivity_goal = form.productivity_goal.data
        current_user.daily_focus_goal = form.daily_focus_goal.data
        current_user.focus_description = form.focus_description.data
        try:
            db.session.commit()
            flash('Settings updated.', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Settings: DB error for user {current_user.id}: {e}")
            flash('Could not update settings.', 'error')
        return redirect(url_for('main.settings'))

    return render_template('main/settings.html', form=form)