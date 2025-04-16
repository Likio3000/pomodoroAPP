# pomodoro_app/main/logic.py
# Contains helper functions and business logic for the main blueprint.

from datetime import datetime, timedelta, timezone, date
from flask import current_app

# Import models used by logic functions (avoids circular imports with routes)
# It's generally safe for logic modules to import models.
from pomodoro_app.models import User, PomodoroSession, ActiveTimerState

# --- Constants ---
# POINTS_PER_MINUTE can be fetched from config where needed: current_app.config.get('POINTS_PER_MINUTE', 10)
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
    if not user: # Safety check
        return 1.0

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

# +++ NEW FUNCTION +++
def get_active_multiplier_rules(user, work_duration_this_session=0):
    """Determines which multiplier rules are currently met."""
    active_rule_ids = set()
    if not user:
        return active_rule_ids

    # Base rate is always applicable conceptually during work, add it
    active_rule_ids.add('base')

    # --- Check each rule condition ---
    # Planned Session Duration
    if work_duration_this_session > 25:
        active_rule_ids.add('focus25')
    if work_duration_this_session > 45:
        active_rule_ids.add('focus45') # Note: If 45 is active, 25 is also active

    # Consistency Streak
    if user.consecutive_sessions >= 3:
        active_rule_ids.add('consecutive3')
    if user.consecutive_sessions >= 5:
        active_rule_ids.add('consecutive5') # Note: If 5 is active, 3 is also active

    # Daily Streak
    if user.daily_streak >= 3:
        active_rule_ids.add('daily3')
    if user.daily_streak >= 7:
        active_rule_ids.add('daily7') # Note: If 7 is active, 3 is also active

    current_app.logger.debug(f"Active Rule IDs for User {user.id} (Duration: {work_duration_this_session}): {active_rule_ids}")
    return active_rule_ids
# +++ END NEW FUNCTION +++


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