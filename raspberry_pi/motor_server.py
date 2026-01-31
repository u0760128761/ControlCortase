import socket
import RPi.GPIO as GPIO
import time
import threading
import subprocess
import os
from flask import Flask, render_template_string, request, redirect, url_for

# --- GPIO Configuration (L298N) ---
# Adjust these pins according to your wiring
ENA = 25  # PWM Speed Motor 1
IN1 = 23  # Motor 1 Direction A
IN2 = 24  # Motor 1 Direction B

ENB = 18  # PWM Speed Motor 2
IN3 = 17  # Motor 2 Direction A
IN4 = 27  # Motor 2 Direction B

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(ENA, GPIO.OUT)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)

GPIO.setup(ENB, GPIO.OUT)
GPIO.setup(IN3, GPIO.OUT)
GPIO.setup(IN4, GPIO.OUT)

# Setup PWM
pwm_m1 = GPIO.PWM(ENA, 1000) # 1kHz
pwm_m2 = GPIO.PWM(ENB, 1000)
pwm_m1.start(0)
pwm_m2.start(0)

current_speed = 50 # Default 0-100 duty cycle (will map from 0-255 input)

# --- Global State for Web Interface ---
BT_STATUS = "Disconnected"
BT_CLIENT_INFO = None

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Motor Server Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --primary: #26c6da;
            --primary-dark: #00acc1;
            --bg: #f5f7fa;
            --card-bg: #ffffff;
            --text-main: #37474f;
            --text-sub: #78909c;
            --success: #66bb6a;
            --danger: #ef5350;
            --shadow: 0 10px 25px rgba(0,0,0,0.05);
        }
        
        body { 
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
            background-color: var(--bg); 
            color: var(--text-main);
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }

        .header {
            width: 100%;
            background: var(--primary);
            color: white;
            padding: 40px 0 60px 0;
            text-align: center;
            border-radius: 0 0 30px 30px;
            box-shadow: 0 4px 15px rgba(38, 198, 218, 0.3);
            margin-bottom: -40px;
            position: relative;
        }

        .lang-switcher {
            position: absolute;
            top: 15px;
            right: 20px;
            display: flex;
            gap: 10px;
            background: rgba(255,255,255,0.2);
            padding: 5px 10px;
            border-radius: 20px;
        }

        .lang-btn {
            font-size: 1.2rem;
            cursor: pointer;
            filter: grayscale(0.8);
            transition: 0.3s;
            line-height: 1;
        }
        .lang-btn.active { filter: grayscale(0); transform: scale(1.2); }

        h1 { margin: 0; font-size: 1.8rem; font-weight: 600; }
        .subtitle { font-size: 0.9rem; opacity: 0.9; margin-top: 5px; }

        .container { 
            width: 90%;
            max-width: 500px;
            z-index: 10;
        }

        .card { 
            background: var(--card-bg);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
            transition: transform 0.2s;
        }

        .status-card {
            border-left: 8px solid var(--danger);
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .status-card.connected { border-left-color: var(--success); }

        .status-icon {
            font-size: 2.5rem;
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f0f4f8;
            border-radius: 15px;
        }

        .status-info { flex: 1; }
        .status-label { font-size: 0.8rem; color: var(--text-sub); text-transform: uppercase; letter-spacing: 1px; }
        .status-value { font-size: 1.2rem; font-weight: bold; margin-top: 2px; }
        .client-info { font-size: 0.85rem; color: var(--text-sub); margin-top: 5px; }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        .action-card {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            cursor: pointer;
            border: none;
            background: var(--card-bg);
            width: 100%;
            text-decoration: none;
            color: inherit;
            font-family: inherit;
        }
        .action-card:hover { transform: translateY(-5px); }
        .action-card:active { transform: scale(0.95); }

        .action-icon { font-size: 2rem; margin-bottom: 10px; }
        .action-label { font-weight: 600; font-size: 0.95rem; }

        /* Floating Refresh Control */
        .refresh-control {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--card-bg);
            padding: 10px 15px;
            border-radius: 50px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.85rem;
            z-index: 100;
            border: 1px solid #eee;
        }

        select {
            border: none;
            background: #f0f2f5;
            padding: 5px 10px;
            border-radius: 10px;
            font-weight: bold;
            color: var(--primary-dark);
            cursor: pointer;
            outline: none;
        }

        @media (max-width: 400px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="lang-switcher">
            <span class="lang-btn" id="lang-ru" onclick="changeLang('ru')" title="Русский">🇷🇺</span>
            <span class="lang-btn" id="lang-en" onclick="changeLang('en')" title="English">🇺🇸</span>
            <span class="lang-btn" id="lang-es" onclick="changeLang('es')" title="Español">🇪🇸</span>
        </div>
        <h1 data-t="app_name">Control Cortase</h1>
        <div class="subtitle" data-t="dashboard_subtitle">Motor Server Dashboard</div>
    </div>

    <div class="container">
        <!-- Status Card -->
        <div class="card status-card {{ 'connected' if connected else '' }}">
            <div class="status-icon">
                {{ '📱' if connected else '💤' }}
            </div>
            <div class="status-info">
                <div class="status-label" data-t="bt_status_label">Bluetooth Status</div>
                <div class="status-value" data-t-status="{{ 'connected' if connected else 'disconnected' }}">{{ 'Connected' if connected else 'Disconnected' }}</div>
                {% if client %}
                <div class="client-info">{{ client }}</div>
                {% endif %}
            </div>
        </div>

        <!-- Action Grid -->
        <div class="grid">
            <form action="/update" method="post">
                <button type="submit" class="card action-card">
                    <div class="action-icon">🔄</div>
                    <div class="action-label" data-t="btn_update">Update (Deploy)</div>
                </button>
            </form>

            <form action="/restart" id="restartForm" method="post">
                <button type="button" class="card action-card" onclick="confirmRestart()">
                    <div class="action-icon">⚠️</div>
                    <div class="action-label" data-t="btn_restart">Restart Pi</div>
                </button>
            </form>
        </div>
    </div>

    <!-- Floating Auto-Refresh -->
    <div class="refresh-control">
        <span data-t="auto_refresh">⏱️ Автообновление:</span>
        <select id="refreshSelect" onchange="updateRefresh()">
            <option value="0" data-t="off">Выкл</option>
            <option value="5" data-t-suffix="s">5с</option>
            <option value="10" data-t-suffix="s">10с</option>
            <option value="15" data-t-suffix="s">15с</option>
            <option value="30" data-t-suffix="s">30с</option>
            <option value="60" data-t-suffix="m">1м</option>
            <option value="300" data-t-suffix="m">5м</option>
        </select>
    </div>

    <script>
        const translations = {
            ru: {
                app_name: "Control Cortase",
                dashboard_subtitle: "Панель управления сервером",
                bt_status_label: "Статус Bluetooth",
                bt_connected: "Подключено",
                bt_disconnected: "Отключено",
                btn_update: "Обновить (Deploy)",
                btn_restart: "Перезагрузить Pi",
                auto_refresh: "⏱️ Автообновление:",
                off: "Выкл",
                s: "с",
                m: "м",
                confirm_restart: "Вы уверены, что хотите перезагрузить устройство?"
            },
            en: {
                app_name: "Control Cortase",
                dashboard_subtitle: "Motor Server Dashboard",
                bt_status_label: "Bluetooth Status",
                bt_connected: "Connected",
                bt_disconnected: "Disconnected",
                btn_update: "Update (Deploy)",
                btn_restart: "Restart Pi",
                auto_refresh: "⏱️ Auto-refresh:",
                off: "Off",
                s: "s",
                m: "m",
                confirm_restart: "Are you sure you want to restart the device?"
            },
            es: {
                app_name: "Control Cortase",
                dashboard_subtitle: "Panel de control del motor",
                bt_status_label: "Estado de Bluetooth",
                bt_connected: "Conectado",
                bt_disconnected: "Desconectado",
                btn_update: "Actualizar (Deploy)",
                btn_restart: "Reiniciar Pi",
                auto_refresh: "⏱️ Auto-refresco:",
                off: "Apagado",
                s: "s",
                m: "m",
                confirm_restart: "¿Está seguro de que desea reiniciar el dispositivo?"
            }
        };

        function applyTranslations() {
            const lang = localStorage.getItem('appLang') || 'ru';
            const t = translations[lang];

            // Set active flag
            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(`lang-${lang}`).classList.add('active');

            // Translate static elements
            document.querySelectorAll('[data-t]').forEach(el => {
                const key = el.getAttribute('data-t');
                if (t[key]) el.textContent = t[key];
            });

            // Translate options with suffixes
            document.querySelectorAll('[data-t-suffix]').forEach(el => {
                const suffix = el.getAttribute('data-t-suffix');
                const val = el.value === "60" ? "1" : (el.value === "300" ? "5" : el.value);
                el.textContent = `${val}${t[suffix]}`;
            });

            // Status value
            const statusEl = document.querySelector('[data-t-status]');
            if (statusEl) {
                const key = statusEl.getAttribute('data-t-status') === 'connected' ? 'bt_connected' : 'bt_disconnected';
                statusEl.textContent = t[key];
            }
        }

        function changeLang(lang) {
            localStorage.setItem('appLang', lang);
            applyTranslations();
        }

        function confirmRestart() {
            const lang = localStorage.getItem('appLang') || 'ru';
            if (confirm(translations[lang].confirm_restart)) {
                document.getElementById('restartForm').submit();
            }
        }

        let refreshTimer = null;
        function startRefresh(seconds) {
            if (refreshTimer) clearInterval(refreshTimer);
            if (seconds > 0) {
                refreshTimer = setInterval(() => {
                    location.reload();
                }, seconds * 1000);
            }
        }

        function updateRefresh() {
            const val = document.getElementById('refreshSelect').value;
            localStorage.setItem('refreshInterval', val);
            startRefresh(parseInt(val));
        }

        window.onload = () => {
            // Lang
            applyTranslations();
            // Refresh
            const saved = localStorage.getItem('refreshInterval') || "0";
            document.getElementById('refreshSelect').value = saved;
            startRefresh(parseInt(saved));
        };
    </script>
</body>
</html>
"""



@app.route('/')
def index():
    is_connected = BT_STATUS == "Connected"
    return render_template_string(HTML_TEMPLATE, status=BT_STATUS, client=BT_CLIENT_INFO, connected=is_connected)

@app.route('/update', methods=['POST'])
def update():
    try:
        # Run deploy.sh from the current directory
        # Assuming deploy.sh is in the same folder as this script, or one level up?
        # Based on file structure, it seems to be in the same folder as motor_server.py is in raspberry_pi/
        # Wait, the user said "deploy.sh" is available. Let's assume relative path "./deploy.sh" in CWD.
        subprocess.Popen(["./deploy.sh"], shell=True)
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error starting update: {e}", 500

@app.route('/restart', methods=['POST'])
def restart():
    try:
        # Restart the Raspberry Pi
        subprocess.Popen(["sudo", "reboot"])
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error restarting: {e}", 500

def run_flask():
    # Run on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def map_speed(val):
    # App sends 0-255, RPi.GPIO PWM expects 0-100
    duty = (val / 255.0) * 100
    return max(0, min(100, duty))

def set_motor(motor, state):
    if motor == 1:
        if state == "FORWARD":
            GPIO.output(IN1, GPIO.HIGH)
            GPIO.output(IN2, GPIO.LOW)
        elif state == "BACKWARD":
            GPIO.output(IN1, GPIO.LOW)
            GPIO.output(IN2, GPIO.HIGH)
        elif state == "STOP":
            GPIO.output(IN1, GPIO.LOW)
            GPIO.output(IN2, GPIO.LOW)
    elif motor == 2:
        if state == "FORWARD":
            GPIO.output(IN3, GPIO.HIGH)
            GPIO.output(IN4, GPIO.LOW)
        elif state == "BACKWARD":
            GPIO.output(IN3, GPIO.LOW)
            GPIO.output(IN4, GPIO.HIGH)
        elif state == "STOP":
            GPIO.output(IN3, GPIO.LOW)
            GPIO.output(IN4, GPIO.LOW)

def server_loop():
    global BT_STATUS, BT_CLIENT_INFO

    # Use standard socket instead of PyBluez
    server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    
    # Bind to any adapter on channel 1
    # Check if we need to release the port or reuse address
    # server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Generally not needed for RFCOMM in the same way
    
    try:
        server_sock.bind((socket.BDADDR_ANY, 1))
    except PermissionError:
        print("Error: Permission denied. Try running with sudo.")
        return
    except OSError as e:
        print(f"Error binding to port: {e}")
        return

    server_sock.listen(1)

    port = 1 # We explicitly bound to channel 1
    
    print(f"Waiting for connection on RFCOMM channel {port}...")
    print("Ensure your Android app is connecting to this device's MAC address on UUID/Channel 1")
    
    # NOTE: advertise_service is removed as it caused issues and SD is strictly not necessary if we connect by MAC
    
    while True:
        try:
            client_sock, client_info = server_sock.accept()
            print("Accepted connection from", client_info)
            BT_STATUS = "Connected"
            BT_CLIENT_INFO = str(client_info)
            
            try:
                while True:
                    data = client_sock.recv(1024)
                    if not data:
                        break
                    
                    try:
                        cmd_str = data.decode("utf-8").strip()
                    except:
                        print("Decode error")
                        continue
                        
                    print("Received:", cmd_str)
                    
                    # Protocol Handling
                    if cmd_str == "M1_FORWARD":
                        set_motor(1, "FORWARD")
                    elif cmd_str == "M1_BACKWARD":
                        set_motor(1, "BACKWARD")
                    elif cmd_str == "M1_STOP":
                        set_motor(1, "STOP")
                    elif cmd_str == "M2_FORWARD":
                        set_motor(2, "FORWARD")
                    elif cmd_str == "M2_BACKWARD":
                        set_motor(2, "BACKWARD")
                    elif cmd_str == "M2_STOP":
                        set_motor(2, "STOP")
                    elif cmd_str.startswith("SPEED:"):
                        try:
                            val = int(cmd_str.split(":")[1])
                            duty = map_speed(val)
                            pwm_m1.ChangeDutyCycle(duty)
                            pwm_m2.ChangeDutyCycle(duty)
                            print(f"Speed set to {duty}%")
                        except ValueError:
                            print("Invalid Speed Value")
                    
            except IOError:
                print("Connection disconnected")
                BT_STATUS = "Disconnected"
                BT_CLIENT_INFO = None
            
            client_sock.close()
            print("Client closed. Waiting for new connection...")
            # Stop motors on disconnect for safety
            set_motor(1, "STOP")
            set_motor(2, "STOP")
            
        except KeyboardInterrupt:
            print("Stopping Server")
            break
        except Exception as e:
             print(f"Error accepting connection: {e}")

    server_sock.close()
    GPIO.cleanup()

if __name__ == "__main__":
    # Start Web Server in a background thread
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    print("Web Interface started at http://<IP>:5000")

    server_loop()
