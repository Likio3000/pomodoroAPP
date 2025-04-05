Pomodoro on Steroids

A professional Pomodoro Timer web application built with Flask.
This project is designed to boost your productivity by combining the Pomodoro technique with additional features like user authentication, session tracking, and an analytics dashboard.

Features:
- User Authentication: Secure registration and login using Flask-Login.
- Customizable Sessions: Set your own work and break durations.
- Session Tracking: Log each Pomodoro session in a SQLite database.
- Analytics Dashboard: View statistics such as total focused time, break time, and session history.
- Live Countdown Timer: An interactive, JavaScript-powered timer with audio notifications.
- Responsive Design: Clean, mobile-friendly layout built with HTML and CSS.
- Modular Structure: Organized using Flask Blueprints for authentication and main app functionality.

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
│   └── routes.py       # Routes for timer, session logging, and dashboard
├── static/             # Static files (CSS, JS, images, alarm audio)
│   ├── style.css       
│   └── alarm.mp3       
└── templates/          # Jinja2 templates
    ├── base.html       # Base layout template
    ├── index.html      # Landing page template
    ├── auth/           
    │   ├── login.html  # Login form template
    │   └── register.html  # Registration form template
    └── main/
        ├── timer.html      # Pomodoro timer page template
        └── dashboard.html  # Analytics dashboard template

Installation:

1. Clone the Repository:
   git clone https://github.com/Likio3000/pomodoroAPP.git
   cd your-repo

2. Create and Activate a Virtual Environment:
   python3 -m venv venv
   source venv/bin/activate  (On Windows: venv\Scripts\activate)

3. Install Dependencies:
   pip install Flask flask-sqlalchemy flask-login flask-wtf email-validator

4. Set Environment Variables:
   export FLASK_APP=pomodoro_app:create_app
   export FLASK_ENV=development

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

Contributing:
Fork the repository, create a feature branch, commit your changes, and open a pull request.

License:
This project is licensed under the MIT License.
