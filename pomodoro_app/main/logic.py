# pomodoro_app/main/logic.py
from datetime import timedelta, timezone, date
from flask import current_app
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

# --- Constants ---
MULTIPLIER_RULES = [
    {'id': 'base',          'condition': 'Base Rate (Work)',        'bonus': 0.0, 'details': 'Active during focused work.'},
    {'id': 'focus25',       'condition': 'Work Block > 25 Min',     'bonus': 0.1, 'details': 'Complete >25 mins in one work session.'},
    {'id': 'focus45',       'condition': 'Work Block > 45 Min',     'bonus': 0.2, 'details': 'Complete >45 mins in one work session.'},
    {'id': 'consecutive3',  'condition': '3+ Consecutive Sessions', 'bonus': 0.1, 'details': 'Complete 3+ work/break cycles.'},
    {'id': 'consecutive5',  'condition': '5+ Consecutive Sessions', 'bonus': 0.2, 'details': 'Complete 5+ work/break cycles.'},
    {'id': 'daily3',        'condition': '3+ Day Usage Streak',     'bonus': 0.1, 'details': 'Use timer 3+ days running.'},
    {'id': 'daily7',        'condition': '7+ Day Usage Streak',     'bonus': 0.2, 'details': 'Use timer 7+ days running.'},
]
MAX_CONSISTENCY_GAP_HOURS = 2

def calculate_current_multiplier(user, work_duration_this_session=0):
    """
    Fully additive multiplier: bonuses stack.
    """
    if not user:
        return 1.0

    total_bonus = 0.0

    # Duration bonuses (additive)
    if work_duration_this_session > 25:
        total_bonus += 0.1
    if work_duration_this_session > 45:
        total_bonus += 0.2

    # Consistency streak bonuses (additive)
    if user.consecutive_sessions >= 3:
        total_bonus += 0.1
    if user.consecutive_sessions >= 5:
        total_bonus += 0.2

    # Daily streak bonuses (additive)
    if user.daily_streak >= 3:
        total_bonus += 0.1
    if user.daily_streak >= 7:
        total_bonus += 0.2

    total_multiplier = 1.0 + total_bonus
    current_app.logger.debug(
        f"User {user.id}: bonus={total_bonus:.2f} → multiplier={total_multiplier:.2f}"
    )
    return round(total_multiplier, 2)

def get_active_multiplier_rules(user, work_duration_this_session=0):
    """
    Return all rule IDs that currently apply (matches additive model).
    """
    active_rule_ids = set()
    if not user:
        return active_rule_ids

    active_rule_ids.add('base')

    # Duration
    if work_duration_this_session > 25:
        active_rule_ids.add('focus25')
    if work_duration_this_session > 45:
        active_rule_ids.add('focus45')

    # Consistency
    if user.consecutive_sessions >= 3:
        active_rule_ids.add('consecutive3')
    if user.consecutive_sessions >= 5:
        active_rule_ids.add('consecutive5')

    # Daily
    if user.daily_streak >= 3:
        active_rule_ids.add('daily3')
    if user.daily_streak >= 7:
        active_rule_ids.add('daily7')

    current_app.logger.debug(
        f"User {user.id}: active rules @ {work_duration_this_session}m → {active_rule_ids}"
    )
    return active_rule_ids


def update_streaks(user, now_utc):
    """Updates daily and consistency streaks based on the current time. Called on WORK phase completion."""
    if not user: # Safety check
        return

    today_utc = now_utc.date()
    points_per_minute = current_app.config.get('POINTS_PER_MINUTE', 10) # Get from config

    # --- Daily Streak ---
    if user.last_active_date != today_utc:
        if user.last_active_date:
            days_diff = (today_utc - user.last_active_date).days
            if days_diff == 1:
                user.daily_streak += 1
                current_app.logger.info(f"User {user.id}: Daily streak continued ({user.daily_streak} days).")
            elif days_diff > 1:
                user.daily_streak = 1
                current_app.logger.info(f"User {user.id}: Daily streak reset (gap > 1 day). New streak: 1.")
        else:
            user.daily_streak = 1
            current_app.logger.info(f"User {user.id}: Daily streak started (1 day).")
        user.last_active_date = today_utc

    # --- Consistency Streak ---
    reset_consistency = True
    if user.last_session_timestamp:
        aware_last_session_timestamp = user.last_session_timestamp
        # Ensure timezone awareness (handle naive datetimes, assuming UTC if naive)
        if getattr(aware_last_session_timestamp, 'tzinfo', None) is None:
            aware_last_session_timestamp = aware_last_session_timestamp.replace(tzinfo=timezone.utc)
            current_app.logger.debug(f"Update Streaks: Made naive last_session_timestamp UTC-aware.")

        time_diff = now_utc - aware_last_session_timestamp
        if time_diff <= timedelta(hours=MAX_CONSISTENCY_GAP_HOURS):
            user.consecutive_sessions += 1
            reset_consistency = False
            current_app.logger.info(f"User {user.id}: Consistency streak continued ({user.consecutive_sessions} sessions). Timediff: {time_diff}")
        else:
             current_app.logger.info(f"User {user.id}: Consistency streak broken. Timediff: {time_diff} > {MAX_CONSISTENCY_GAP_HOURS} hours.")

    if reset_consistency:
        user.consecutive_sessions = 1
        current_app.logger.info(f"User {user.id}: Consistency streak started/reset (1 session).")

    # Update timestamp AFTER calculating streak
    user.last_session_timestamp = now_utc

# Note: No Flask blueprint-specific imports (request, jsonify etc.) are needed here.
# These functions operate on data passed to them.