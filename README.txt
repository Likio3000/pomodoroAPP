Pomodoro on Steroids

A professional Pomodoro Timer web application built with Flask.
This project is designed to boost your productivity by combining the Pomodoro technique with additional features like user authentication, session tracking, and an analytics dashboard with an optional AI assistant.

Features:
- User Authentication: Secure registration and login using Flask-Login.
- Customizable Sessions: Set your own work and break durations.
- Session Tracking: Log each Pomodoro session in a SQLite database.
- Analytics Dashboard: View statistics such as total focused time, break time, and session history.
- AI Productivity Assistant (Optional): Chat with an OpenAI-powered assistant on the dashboard for tips and insights based on your stats (requires API key).
- Live Countdown Timer: An interactive, JavaScript-powered timer with audio notifications.
- Responsive Design: Clean, mobile-friendly layout built with HTML and CSS.
- Modular Structure: Organized using Flask Blueprints for authentication and main app functionality.
- Automatic cleanup of old AI-generated audio files (configurable with MAX_AUDIO_FILE_AGE).

Project Structure:
pomodoro_app/
├── __init__.py         # Application factory and extension initialization
├── models.py           # Database models (User, PomodoroSession)
├── forms.py            # WTForms classes for registration and login
├── auth/               # Authentication blueprint
│   ├── __init__.py
│   └── routes.py       # Routes for login, registration, logout
├── main/               # Main application blueprint
│   ├── __init__.py
│   └── routes.py       # Routes for timer, session logging, dashboard, and chat API
├── static/             # Static files (CSS, JS, images, alarm audio)
│   ├── style.css
│   ├── js/
│   │   └── timer.js
│   └── alarm.mp3
└── templates/          # Jinja2 templates
    ├── base.html       # Base layout template
    ├── index.html      # Landing page template
    ├── 429.html        # Rate limit error page
    ├── auth/
    │   ├── login.html  # Login form template
    │   └── register.html  # Registration form template
    └── main/
        ├── timer.html      # Pomodoro timer page template
        └── dashboard.html  # Analytics dashboard template (with chat UI)

Installation:

1. Clone the Repository:
   git clone https://github.com/Likio3000/pomodoroAPP.git
   cd your-repo

2. Create and Activate a Virtual Environment:
   python3 -m venv venv
   source venv/bin/activate  (On Windows: venv\Scripts\activate)

3. Install Dependencies:
   pip install Flask flask-sqlalchemy flask-login flask-wtf email-validator openai # Added openai
   # OR install directly from the updated requirements file:
   pip install -r requirements.txt

4. Set Environment Variables:
   # Use the provided sample file for local development
   cp .env.example .env
   # then edit .env with your settings, or export the variables manually:
   export FLASK_APP=pomodoro_app:create_app
   export FLASK_ENV=development
   export SECRET_KEY='your-very-secret-flask-key' # IMPORTANT: Set a strong secret key
   # Never deploy with the sample SECRET_KEY.
   # Generate at least 32 random bytes using:
   #   flask secrets generate-key
   export DATABASE_URL='sqlite:///pomodoro.db' # Or your preferred DB connection string
   export OPENAI_API_KEY='your_openai_api_key_here' # Add your OpenAI key (required for chat feature)
   export MAX_AUDIO_FILE_AGE=3600  # Optional: age in seconds for cleaning old agent audio

5. Initialize the Database:
   The app will create the SQLite database (pomodoro.db) on first run, or run:
   flask shell
   >>> from pomodoro_app import db
   >>> db.create_all()
   >>> exit()

6. Run the Application:
   flask run
   Visit http://127.0.0.1:5000 in your browser.

Usage:
- Register: Navigate to /register to create a new account.
- Login: Use /login to sign in.
- Start a Session: Use the Timer page to set your durations and start a Pomodoro.
- View Analytics: Check the Dashboard for session statistics.
- Chat (Optional): If configured, interact with the AI assistant on the dashboard.

AI Profile
----------
Use the **Settings** page to configure your AI profile. These values help the assistant tailor its responses to you:

- **Preferred Work Minutes**: Default length of a focused work block. The timer uses this when you start a new session.
- **Productivity Goal**: Short statement describing what you want to achieve overall. The AI refers to this when giving encouragement.
- **Daily Focus Goal (minutes)**: Optional daily target for time spent in focus mode. Helpful for tracking progress.
- **Focus Description**: Optional details about what you intend to focus on today or this week.

The AI assistant reads these fields to provide more relevant suggestions during chats and in motivational prompts.

Running Tests:
  pytest
  # The tests use the built-in TestingConfig and do not require any
  # environment variables to be set.

API Clients and CSRF
--------------------
Browser pages include a `<meta name="csrf-token">` tag with a token
generated by Flask-WTF. JavaScript clients read this value and send it
in the `X-CSRFToken` header. Mobile or other non-browser clients should
first perform a GET request to any page (for example `/auth/login`) to
obtain the token from this meta tag or the `csrf_token` cookie. That
token must be sent with subsequent POST requests to endpoints such as
`/api/timer/start`.

Contributing:
Fork the repository, create a feature branch, commit your changes, and open a pull request.

License:
This project is licensed under the MIT License.