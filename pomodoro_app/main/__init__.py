# pomodoro_app/main/__init__.py
from flask import Blueprint

# Define the blueprint for the 'main' section of the application
main = Blueprint('main', __name__)

# Import the route modules AFTER the blueprint object 'main' is created.
# This registers the routes defined in those files with the 'main' blueprint.
from . import routes, api_routes
# logic.py contains helper functions and doesn't need to be imported here
# unless other parts of the main package initialization require it.