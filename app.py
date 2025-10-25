import os
import threading
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from bot_logic import run_bot_instance
from collections import deque

# --- ROBUST PATH SETUP ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CACHE_DIR = os.path.join(BASE_DIR, 'my_browser_cache')
LOG_FILE = os.path.join(BASE_DIR, 'bot_log.txt')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# --- CREATE THE FLASK APP and SOCKETIO OBJECTS ---
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
app.config['SECRET_KEY'] = 'a_very_secret_key'
# --- !! CHANGE 1: REMOVED async_mode !! ---
# We will let SocketIO choose the best mode, which will be compatible.
socketio = SocketIO(app)

# --- Central State Management ---
APP_STATE = {'bot_running': False,
             'auto_bet_enabled': False, 'conditions_met_count': 0}
bot_thread = None
stop_event = threading.Event()

# --- ROUTES AND EVENT HANDLERS ---


def broadcast_state():
    socketio.emit('update_state', APP_STATE)


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    print("Client connected. Sending initial state and log history.")
    try:
        with open(LOG_FILE, 'r') as f:
            last_lines = deque(f, 200)
        socketio.emit('log_history', {'data': list(last_lines)})
    except FileNotFoundError:
        socketio.emit('log_message', {'data': 'Welcome! No log history yet.'})
    broadcast_state()


@socketio.on('start_bot')
def handle_start_bot():
    global bot_thread
    if not APP_STATE['bot_running']:
        print("Received start command. Starting bot thread.")
        APP_STATE['bot_running'] = True
        APP_STATE['conditions_met_count'] = 0
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
        print("Received stop command.")
        stop_event.set()


@socketio.on('toggle_auto_bet')
def handle_toggle_auto_bet():
    if APP_STATE['bot_running']:
        APP_STATE['auto_bet_enabled'] = not APP_STATE['auto_bet_enabled']
        print(
            f"Auto-betting toggled to: {'ENABLED' if APP_STATE['auto_bet_enabled'] else 'DISABLED'}")
        broadcast_state()


@socketio.on('clear_logs')
def handle_clear_logs():
    print("Received clear logs command.")
    socketio.emit('log_message', {
                  'data': '--- Log history has been cleared. ---', 'clear': True})
    if os.path.exists(LOG_FILE):
        try:
            open(LOG_FILE, 'w').close()
        except Exception as e:
            print(f"Error clearing log file: {e}")


# --- FINALLY, RUN THE APP ---
if __name__ == '__main__':
    print("Starting Flask-SocketIO server.")
    print("Open your browser and navigate to http://127.0.0.1:5000")
    # --- !! CHANGE 2: USE THE DEFAULT SERVER !! ---
    # We remove the host='0.0.0.0' for now, as Flask's development server is simpler.
    # It will be accessible on your local machine at the printed address.
    socketio.run(app, port=5000, allow_unsafe_werkzeug=True)
