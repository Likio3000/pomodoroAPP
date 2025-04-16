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

# --- MODIFIED FUNCTION: Fully Additive Calculation ---
def calculate_current_multiplier(user, work_duration_this_session=0):
    """
    Calculates the applicable multiplier based on user streaks AND PLANNED session duration.
    Bonuses are fully additive.
    """
    if not user: # Safety check
        return 1.0

    total_bonus = 0.0

    # Duration Bonuses (Additive - higher duration implies lower one is also met)
    if work_duration_this_session > 25:
        total_bonus += 0.1 # Add bonus for > 25 mins
    if work_duration_this_session > 45:
        total_bonus += 0.2 # Add *additional* bonus for > 45 mins (0.1 + 0.1 = 0.2 total)

    # Consistency Streak Bonuses (Additive)
    if user.consecutive_sessions >= 3:
        total_bonus += 0.1 # Add bonus for 3+
    if user.consecutive_sessions >= 5:
        total_bonus += 0.2 # Add *additional* bonus for 5+ (0.1 + 0.1 = 0.2 total)

    # Daily Streak Bonuses (Additive)
    if user.daily_streak >= 3:
        total_bonus += 0.1 # Add bonus for 3+
    if user.daily_streak >= 7:
        total_bonus += 0.2 # Add *additional* bonus for 7+ (0.1 + 0.1 = 0.2 total)

    # Base multiplier is always 1.0
    base_multiplier = 1.0
    total_multiplier = base_multiplier + total_bonus

    # Optional: Cap the multiplier if desired (e.g., max 2.5x)
    # total_multiplier = min(total_multiplier, 2.5)

    current_app.logger.debug(f"Additive Multiplier Calc for User {user.id}: Total Bonus={total_bonus:.1f} -> Total Multiplier={total_multiplier:.1f}")
    return round(total_multiplier, 2) # Round to avoid float issues
# --- END MODIFIED FUNCTION ---


# --- REVERTED FUNCTION: Show all met rules ---
def get_active_multiplier_rules(user, work_duration_this_session=0):
    """
    Determines which multiplier rule conditions are currently met.
    Returns all rule IDs that apply, matching the additive calculation.
    """
    active_rule_ids = set()
    if not user:
        return active_rule_ids

    # Base rate is always applicable conceptually during work
    active_rule_ids.add('base')

    # --- Check each rule condition ---
    # Session Duration (Both can be active if > 45)
    if work_duration_this_session > 25:
        active_rule_ids.add('focus25')
    if work_duration_this_session > 45:
        active_rule_ids.add('focus45')

    # Consistency Streak (Both can be active if >= 5)
    if user.consecutive_sessions >= 3:
        active_rule_ids.add('consecutive3')
    if user.consecutive_sessions >= 5:
        active_rule_ids.add('consecutive5')

    # Daily Streak (Both can be active if >= 7)
    if user.daily_streak >= 3:
        active_rule_ids.add('daily3')
    if user.daily_streak >= 7:
        active_rule_ids.add('daily7')

    current_app.logger.debug(f"All Met Rule IDs for User {user.id} (Duration: {work_duration_this_session}): {active_rule_ids}")
    return active_rule_ids
# --- END REVERTED FUNCTION ---


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