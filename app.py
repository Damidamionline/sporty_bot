import os
import threading
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from bot_logic import run_bot_instance
from collections import deque

# --- ROBUST PATH SETUP ---
# Get the absolute path of the directory where this script is located.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CACHE_DIR = os.path.join(BASE_DIR, 'my_browser_cache')
LOG_FILE = os.path.join(BASE_DIR, 'bot_log.txt')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Explicitly tell Flask where to find the templates folder to avoid pathing issues.
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
app.config['SECRET_KEY'] = 'a_very_secret_key'
socketio = SocketIO(app, async_mode='eventlet')

# --- Central State Management ---
APP_STATE = {'bot_running': False, 'auto_bet_enabled': False}
bot_thread = None
stop_event = threading.Event()


def broadcast_state():
    """Sends the current state to all clients."""
    socketio.emit('update_state', APP_STATE)


@socketio.on('connect')
def handle_connect():
    """When a new user connects, send them the current state and recent log history."""
    print("Client connected. Sending initial state and log history.")
    try:
        with open(LOG_FILE, 'r') as f:
            last_lines = deque(f, 200)  # Send the last 200 lines
        socketio.emit('log_history', {'data': list(last_lines)})
    except FileNotFoundError:
        socketio.emit('log_message', {'data': 'Welcome! No log history yet.'})
    broadcast_state()


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('start_bot')
def handle_start_bot():
    global bot_thread
    if not APP_STATE['bot_running']:
        print("Received start command. Starting bot thread.")
        APP_STATE['bot_running'] = True
        broadcast_state()
        stop_event.clear()

        bot_thread = socketio.start_background_task(
            target=run_bot_instance,
            socketio=socketio,
            user_data_path=CACHE_DIR,
            stop_event=stop_event,
            app_state=APP_STATE,
            log_file=LOG_FILE
        )


@socketio.on('stop_bot')
def handle_stop_bot():
    if APP_STATE['bot_running']:
        print("Received stop command. Signaling bot to stop.")
        socketio.emit('log_message', {
                      'data': '--- Sending stop signal to bot... ---'})
        stop_event.set()


@socketio.on('toggle_auto_bet')
def handle_toggle_auto_bet():
    if APP_STATE['bot_running']:
        APP_STATE['auto_bet_enabled'] = not APP_STATE['auto_bet_enabled']
        status = "ENABLED" if APP_STATE['auto_bet_enabled'] else "DISABLED"
        print(f"Auto-betting toggled to: {status}")
        broadcast_state()


if __name__ == '__main__':
    print("Starting Flask-SocketIO server.")
    print("Open your browser and navigate to http://127.0.0.1:5000")
    socketio.run(app, host='0.0.0.0', port=5000)
