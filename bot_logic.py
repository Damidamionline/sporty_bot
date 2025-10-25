import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, expect

# The line "from bot_logic import run_bot_instance" has been REMOVED from here.

# --- CONFIGURATION ---
BET_COOLDOWN_SECONDS = 300
TRIGGER_MULTIPLIER = 150.0


def parse_multiplier(text: str) -> float:
    try:
        return float(text.lower().replace('x', '').strip())
    except (ValueError, AttributeError):
        return 0.0


def parse_balance(text: str) -> str:
    try:
        match = re.search(r'[\d,.]+', text)
        if match:
            return match.group(0).replace(',', '')
        return "0"
    except (ValueError, AttributeError):
        return "0"


def run_bot_instance(socketio, user_data_path, stop_event, app_state, log_file):
    def log(message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        with open(log_file, 'a') as f:
            f.write(log_entry + '\n')
        socketio.emit('log_message', {'data': log_entry})

    try:
        with sync_playwright() as p:
            # ... (The rest of the file is unchanged and correct) ...
            browser = p.chromium.launch_persistent_context(
                user_data_path, headless=True, slow_mo=100, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', viewport={'width': 1280, 'height': 800})
            page = browser.pages[0] if browser.pages else browser.new_page()
            log("Navigating directly to login page...")
            page.goto("https://www.sportybet.com/ng/login",
                      timeout=0, wait_until='domcontentloaded')
            log("Attempting login...")
            page.get_by_placeholder("Mobile Number").fill("7043031993")
            page.get_by_placeholder("Password").fill("damilare10")
            page.get_by_role("button", name="Login").click()
            expect(page.locator("#header_nav_games")).to_be_visible(timeout=0)
            log("--- LOGIN CONFIRMED ---")
            page.locator("#header_nav_games").click()
            games_iframe = page.locator("#games-lobby")
            expect(games_iframe).to_be_visible(timeout=0)
            game_frame = games_iframe.frame_locator(':scope')
            aviator_in_frame = game_frame.locator('#game_item19 img').first
            expect(aviator_in_frame).to_be_visible(timeout=0)
            aviator_in_frame.click()
            log("--- AVIATOR LAUNCHED ---")
            log("Waiting for game controls...")
            aviator_game_frame = page.frame_locator(
                "#games-lobby").frame_locator("iframe").first
            auto_tab_button = aviator_game_frame.get_by_role(
                "button", name="Auto").first
            expect(auto_tab_button).to_be_visible(timeout=0)
            log("Configuring Auto-Bet Settings...")
            auto_tab_button.click()
            aviator_game_frame.locator(
                ".cash-out-switcher .oval").first.click()
            cashout_input = aviator_game_frame.get_by_role("textbox").nth(1)
            cashout_input.click()
            cashout_input.fill("1.05")
            log("--- Auto-Bet Settings Configured Successfully! ---\n")
            log(f"--- BOT MONITORING STARTED ---")

            last_processed_result = None
            last_bet_timestamp = 0

            while not stop_event.is_set():
                current_result_text = aviator_game_frame.locator(
                    "div.payouts-wrapper .payout").first.inner_text()
                if current_result_text and current_result_text != last_processed_result:
                    last_processed_result = current_result_text
                    latest_multiplier = parse_multiplier(current_result_text)
                    log(f"New result: {latest_multiplier}x")

                    if latest_multiplier > TRIGGER_MULTIPLIER:
                        app_state['conditions_met_count'] += 1
                        socketio.emit('update_state', app_state)

                        log(
                            f"[!!] CONDITION MET ({app_state['conditions_met_count']} times): Last result was {latest_multiplier}x!")

                        if app_state['auto_bet_enabled']:
                            seconds_since_last_bet = time.time() - last_bet_timestamp
                            if seconds_since_last_bet > BET_COOLDOWN_SECONDS:
                                log("[$$] Placing bet...")
                                balance_text = page.locator(
                                    "#j_balance").inner_text()
                                balance_to_bet = parse_balance(balance_text)

                                if float(balance_to_bet) > 0:
                                    stake_input = aviator_game_frame.locator(
                                        "app-bet-controls input[type='text']").first
                                    stake_input.fill(balance_to_bet)
                                    stake_input.press("Tab")
                                    time.sleep(0.5)
                                    bet_button = aviator_game_frame.locator(
                                        "app-bet-controls app-bet-control:first-child button.btn-success.bet")
                                    bet_button.click()
                                    last_bet_timestamp = time.time()
                                    log(
                                        f"[>>] AUTO-BET PLACED for {balance_to_bet} NGN!")
                                else:
                                    log("[!!] Balance is zero. Cannot bet.")
                            else:
                                remaining_cooldown = BET_COOLDOWN_SECONDS - last_bet_timestamp
                                log(f"[--] In cooldown ({remaining_cooldown:.0f}s left).")
                        else:
                            log("[--] Auto-Bet is DISABLED. No action taken.")

                socketio.sleep(2)

    except Exception as e:
        log(f"!!!!!!!! A FATAL ERROR OCCURRED: {e} !!!!!!!!")
    finally:
        log("\n--- Bot thread is shutting down. ---")
        app_state['bot_running'] = False
        app_state['auto_bet_enabled'] = False
        socketio.emit('update_state', app_state)
