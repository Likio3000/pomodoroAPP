import json
from flask import current_app


def load_personas():
    """Load agent personas from the configured JSON file."""
    file_path = current_app.config.get('AGENT_PERSONA_FILE')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        current_app.logger.error(f"Agent persona file not found: {file_path}")
        return {}
    except json.JSONDecodeError as e:
        current_app.logger.error(f"Invalid JSON in persona file {file_path}: {e}")
        return {}


def save_personas(data):
    """Save agent personas back to the configured JSON file."""
    file_path = current_app.config.get('AGENT_PERSONA_FILE')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return True
