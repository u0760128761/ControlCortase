import socket
import threading
import subprocess
import os
from flask import Flask, render_template_string, request, redirect, url_for
from gpiozero import Motor

# --- Motor Configuration (L298N + gpiozero) ---
# Left Motor (M1): Forward=17, Backward=18, Speed Control (Enable)=23
left_motor = Motor(forward=17, backward=18, enable=23)

# Right Motor (M2): Forward=27, Backward=22, Speed Control (Enable)=24
right_motor = Motor(forward=27, backward=22, enable=24)

current_speed = 0.5 # Default 0.0-1.0

# --- Global State for Web Interface ---
BT_STATUS = "Disconnected"
BT_CLIENT_INFO = None
BT_DEVICE_NAME = None

def get_bt_device_name(mac):
    try:
        # Resolve MAC address to a friendly name using bluetoothctl
        result = subprocess.run(["bluetoothctl", "info", mac], capture_output=True, text=True, timeout=2)
        for line in result.stdout.splitlines():
            if "Name:" in line:
                return line.split("Name:")[1].strip()
    except Exception as e:
        print(f"Error resolving BT name: {e}")
    return "Unknown Device"

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Motor Server Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
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
            --warning: #ffa726;
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
            overflow-x: hidden;
        }

        /* Header */
        .header {
            width: 100%;
            background: var(--primary);
            color: white;
            padding: 20px 0 30px 0;
            text-align: center;
            border-radius: 0 0 30px 30px;
            box-shadow: 0 4px 15px rgba(38, 198, 218, 0.3);
            position: relative;
            z-index: 100;
        }

        .lang-switcher {
            position: absolute;
            top: 15px;
            right: 15px;
            display: flex;
            gap: 8px;
            background: rgba(255,255,255,0.2);
            padding: 4px 8px;
            border-radius: 15px;
        }

        .lang-btn {
            font-size: 1rem;
            cursor: pointer;
            filter: grayscale(0.8);
            transition: 0.3s;
        }
        .lang-btn.active { filter: grayscale(0); transform: scale(1.1); }

        .bt-header-status {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            margin-top: 10px;
            background: rgba(0,0,0,0.05);
            padding: 10px 20px;
            margin-left: 20px;
            margin-right: 20px;
            border-radius: 15px;
            font-size: 0.9rem;
        }

        .bt-dot {
            width: 10px;
            height: 10px;
            background: var(--danger);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--danger);
        }
        .bt-dot.connected {
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
        }

        .device-info-compact { text-align: left; }
        .device-name-header { font-weight: bold; }
        .device-mac-header { font-size: 0.75rem; opacity: 0.8; }

        /* Tabs */
        .nav-tabs {
            width: 100%;
            display: flex;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            margin-top: 10px;
            justify-content: space-around;
        }

        .tab-link {
            padding: 15px 20px;
            cursor: pointer;
            font-weight: 600;
            color: var(--text-sub);
            border-bottom: 3px solid transparent;
            transition: 0.3s;
            flex: 1;
            text-align: center;
            font-size: 0.9rem;
        }

        .tab-link.active {
            color: var(--primary-dark);
            border-bottom-color: var(--primary-dark);
        }

        /* Content */
        .container { 
            width: 95%;
            max-width: 500px;
            padding-top: 20px;
            flex: 1;
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.3s; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .card { 
            background: var(--card-bg);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }

        /* Remote Control D-Pad */
        .control-grid {
            display: grid;
            grid-template-areas: 
                ". up ."
                "left stop right"
                ". down .";
            gap: 15px;
            justify-content: center;
            align-content: center;
            margin: 20px auto;
            width: 260px;
            height: 260px;
        }

        .ctrl-btn {
            width: 80px;
            height: 80px;
            border-radius: 20px;
            border: none;
            background: #f0f4f8;
            color: var(--text-main);
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            transition: 0.2s;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }

        .ctrl-btn:active { transform: scale(0.9); background: #e2e8f0; }
        .ctrl-btn.up { grid-area: up; }
        .ctrl-btn.down { grid-area: down; }
        .ctrl-btn.left { grid-area: left; }
        .ctrl-btn.right { grid-area: right; }
        .ctrl-btn.stop { 
            grid-area: stop; 
            background: var(--danger); 
            color: white; 
            border-radius: 50%;
            font-weight: bold;
            font-size: 1.1rem;
        }
        .ctrl-btn.stop:active { background: #d32f2f; }

        /* Motor Info Info */
        .motor-info {
            display: flex;
            justify-content: space-around;
            font-size: 0.75rem;
            color: var(--text-sub);
            padding-top: 15px;
            border-top: 1px solid #f0f4f8;
            margin-top: 5px;
        }
        .motor-side { text-align: center; }
        .motor-pins { font-weight: bold; color: var(--primary-dark); }

        /* Admin Buttons */
        .admin-grid { display: grid; grid-template-columns: 1fr; gap: 15px; }
        .action-card {
            display: flex;
            align-items: center;
            padding: 20px;
            cursor: pointer;
            border: none;
            background: var(--card-bg);
            border-radius: 20px;
            box-shadow: var(--shadow);
            width: 100%;
            text-align: left;
            gap: 15px;
        }
        .action-icon { font-size: 1.5rem; width: 40px; }
        .action-label { font-weight: 600; flex: 1; }

        /* Refresh Control */
        .refresh-control {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--card-bg);
            padding: 8px 12px;
            border-radius: 50px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.8rem;
            z-index: 100;
        }

        select { border: none; background: #f0f2f5; padding: 4px 8px; border-radius: 10px; font-weight: bold; outline: none; }

        .placeholder-text { text-align: center; color: var(--text-sub); padding: 40px 0; }
    </style>
</head>
<body>
    <div class="header">
        <div class="lang-switcher">
            <span class="lang-btn" id="lang-ru" onclick="changeLang('ru')">🇷🇺</span>
            <span class="lang-btn" id="lang-en" onclick="changeLang('en')">🇺🇸</span>
            <span class="lang-btn" id="lang-es" onclick="changeLang('es')">🇪🇸</span>
        </div>
        <h1 data-t="app_name">Control Cortase</h1>
        
        <div class="bt-header-status">
            <div class="bt-dot {{ 'connected' if connected else '' }}"></div>
            <div class="device-info-compact">
                <div class="device-name-header">
                    {% if connected %}
                        {{ device_name if device_name else 'MiotLinkAp_DAFA' }}
                    {% else %}
                        <span data-t="bt_disconnected">Disconnected</span>
                    {% endif %}
                </div>
                {% if connected and client %}
                <div class="device-mac-header">{{ client }}</div>
                {% endif %}
            </div>
            <div style="flex: 1; text-align: right; opacity: 0.7;">
                {{ '📱' if connected else '💤' }}
            </div>
        </div>
    </div>

    <div class="nav-tabs">
        <div class="tab-link active" onclick="showTab('control')" data-t="tab_control">Управление</div>
        <div class="tab-link" onclick="showTab('admin')" data-t="tab_admin">Админ</div>
        <div class="tab-link" onclick="showTab('maps')" data-t="tab_maps">Карты</div>
    </div>

    <div class="container">
        <!-- Control Tab -->
        <div id="control" class="tab-content active">
            <div class="card">
                <div class="control-grid">
                    <button class="ctrl-btn up" onclick="sendCommand('forward')">▲</button>
                    <button class="ctrl-btn left" onclick="sendCommand('left')">◀</button>
                    <button class="ctrl-btn stop" onclick="sendCommand('stop')">STOP</button>
                    <button class="ctrl-btn right" onclick="sendCommand('right')">▶</button>
                    <button class="ctrl-btn down" onclick="sendCommand('backward')">▼</button>
                </div>
                <div class="motor-info">
                    <div class="motor-side">
                        <div data-t="m_left">Левый мотор</div>
                        <div class="motor-pins">GPIO 17, 18, 23</div>
                    </div>
                    <div class="motor-side">
                        <div data-t="m_right">Правый мотор</div>
                        <div class="motor-pins">GPIO 27, 22, 24</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Admin Tab -->
        <div id="admin" class="tab-content">
            <div class="admin-grid">
                <form action="/update" method="post">
                    <button type="submit" class="action-card">
                        <div class="action-icon">🔄</div>
                        <div class="action-label" data-t="btn_update">Update (Deploy)</div>
                    </button>
                </form>

                <form action="/restart" id="restartForm" method="post">
                    <button type="button" class="action-card" onclick="confirmRestart()">
                        <div class="action-icon">⚠️</div>
                        <div class="action-label" data-t="btn_restart">Restart Pi</div>
                    </button>
                </form>
            </div>
        </div>

        <!-- Maps Tab -->
        <div id="maps" class="tab-content">
            <div class="card">
                <div class="placeholder-text">
                    <div style="font-size: 3rem; margin-bottom: 10px;">🗺️</div>
                    <div data-t="maps_placeholder">Карты в разработке...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Floating Auto-Refresh -->
    <div class="refresh-control">
        <select id="refreshSelect" onchange="updateRefresh()">
            <option value="0" data-t="off">Off</option>
            <option value="5" data-t-suffix="s">5s</option>
            <option value="10" data-t-suffix="s">10s</option>
            <option value="15" data-t-suffix="s">15s</option>
            <option value="30" data-t-suffix="s">30s</option>
            <option value="60" data-t-suffix="m">1m</option>
            <option value="300" data-t-suffix="m">5m</option>
        </select>
    </div>

    <script>
        const translations = {
            ru: {
                app_name: "Control Cortase",
                tab_control: "Управление",
                tab_admin: "Администрирование",
                tab_maps: "Карты",
                bt_disconnected: "Отключено",
                btn_update: "Обновить (Deploy)",
                btn_restart: "Перезагрузить Pi",
                auto_refresh: "⏱️:",
                off: "Выкл",
                s: "с",
                m: "м",
                confirm_restart: "Вы уверены, что хотите перезагрузить устройство?",
                maps_placeholder: "Карты в разработке...",
                m_left: "Левый мотор",
                m_right: "Правый мотор"
            },
            en: {
                app_name: "Control Cortase",
                tab_control: "Control",
                tab_admin: "Admin",
                tab_maps: "Maps",
                bt_disconnected: "Disconnected",
                btn_update: "Update (Deploy)",
                btn_restart: "Restart Pi",
                auto_refresh: "⏱️:",
                off: "Off",
                s: "s",
                m: "m",
                confirm_restart: "Are you sure you want to restart the device?",
                maps_placeholder: "Maps under development...",
                m_left: "Left Motor",
                m_right: "Right Motor"
            },
            es: {
                app_name: "Control Cortase",
                tab_control: "Control",
                tab_admin: "Admin",
                tab_maps: "Mapas",
                bt_disconnected: "Desconectado",
                btn_update: "Actualizar (Deploy)",
                btn_restart: "Reiniciar Pi",
                auto_refresh: "⏱️:",
                off: "Apagado",
                s: "s",
                m: "m",
                confirm_restart: "¿Está seguro de что desea reiniciar el dispositivo?",
                maps_placeholder: "Mapas en desarrollo...",
                m_left: "Motor Izquierdo",
                m_right: "Motor Derecho"
            }
        };

        function applyTranslations() {
            const lang = localStorage.getItem('appLang') || 'ru';
            const t = translations[lang];

            document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(`lang-${lang}`).classList.add('active');

            document.querySelectorAll('[data-t]').forEach(el => {
                const key = el.getAttribute('data-t');
                if (t[key]) el.textContent = t[key];
            });

            document.querySelectorAll('[data-t-suffix]').forEach(el => {
                const suffix = el.getAttribute('data-t-suffix');
                const val = el.value === "60" ? "1" : (el.value === "300" ? "5" : el.value);
                el.textContent = `${val}${t[suffix]}`;
            });
        }

        function changeLang(lang) {
            localStorage.setItem('appLang', lang);
            applyTranslations();
        }

        function showTab(id) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            if (event) {
                event.target.classList.add('active');
            }
            localStorage.setItem('activeTab', id);
        }

        function sendCommand(dir) {
            fetch(`/move/${dir}`, { method: 'POST' })
                .then(r => console.log('Action:', dir))
                .catch(e => console.error('Error:', e));
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
                refreshTimer = setInterval(() => location.reload(), seconds * 1000);
            }
        }

        function updateRefresh() {
            const val = document.getElementById('refreshSelect').value;
            localStorage.setItem('refreshInterval', val);
            startRefresh(parseInt(val));
        }

        window.onload = () => {
            applyTranslations();
            const savedRefresh = localStorage.getItem('refreshInterval') || "0";
            document.getElementById('refreshSelect').value = savedRefresh;
            startRefresh(parseInt(savedRefresh));
            
            const savedTab = localStorage.getItem('activeTab') || 'control';
            showTab(savedTab);
            const activeLink = document.querySelector(`.tab-link[onclick*="${savedTab}"]`);
            if (activeLink) activeLink.classList.add('active');
        };
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    is_connected = BT_STATUS == "Connected"
    return render_template_string(HTML_TEMPLATE, status=BT_STATUS, client=BT_CLIENT_INFO, device_name=BT_DEVICE_NAME, connected=is_connected)

@app.route('/move/<direction>', methods=['POST'])
def move(direction):
    process_movement_cmd(direction.upper())
    return "OK", 200

def process_movement_cmd(cmd):
    print(f"Executing: {cmd}")
    if cmd == "FORWARD":
        set_motor(1, "FORWARD")
        set_motor(2, "FORWARD")
    elif cmd == "BACKWARD":
        set_motor(1, "BACKWARD")
        set_motor(2, "BACKWARD")
    elif cmd == "LEFT":
        set_motor(1, "BACKWARD")
        set_motor(2, "FORWARD")
    elif cmd == "RIGHT":
        set_motor(1, "FORWARD")
        set_motor(2, "BACKWARD")
    elif cmd == "STOP":
        set_motor(1, "STOP")
        set_motor(2, "STOP")
    elif cmd == "M1_FORWARD": set_motor(1, "FORWARD")
    elif cmd == "M1_BACKWARD": set_motor(1, "BACKWARD")
    elif cmd == "M1_STOP": set_motor(1, "STOP")
    elif cmd == "M2_FORWARD": set_motor(2, "FORWARD")
    elif cmd == "M2_BACKWARD": set_motor(2, "BACKWARD")
    elif cmd == "M2_STOP": set_motor(2, "STOP")

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

def map_speed(val255):
    # Map 0-255 value to 0.0-1.0 for gpiozero
    return max(0.0, min(1.0, val255 / 255.0))

def set_motor(motor_id, direction):
    motor = left_motor if motor_id == 1 else right_motor
    
    if direction == "FORWARD":
        motor.forward(current_speed)
    elif direction == "BACKWARD":
        motor.backward(current_speed)
    elif direction == "STOP":
        motor.stop()

def server_loop():
    global BT_STATUS, BT_CLIENT_INFO, BT_DEVICE_NAME

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
            mac = client_info[0]
            BT_CLIENT_INFO = mac
            BT_DEVICE_NAME = get_bt_device_name(mac)
            
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
                    if cmd_str.startswith("SPEED:"):
                        try:
                            val = int(cmd_str.split(":")[1])
                            current_speed = map_speed(val)
                            # Re-apply current speed to motors if they are moving
                            if left_motor.is_active:
                                left_motor.value = (left_motor.value / abs(left_motor.value)) * current_speed if left_motor.value != 0 else 0
                            if right_motor.is_active:
                                right_motor.value = (right_motor.value / abs(right_motor.value)) * current_speed if right_motor.value != 0 else 0
                            print(f"Speed set to {current_speed*100}%")
                        except ValueError:
                            print("Invalid Speed Value")
                    else:
                        process_movement_cmd(cmd_str)
                    
            except IOError:
                print("Connection disconnected")
                BT_STATUS = "Disconnected"
                BT_CLIENT_INFO = None
                BT_DEVICE_NAME = None
            
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

if __name__ == "__main__":
    # Start Web Server in a background thread
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()
    print("Web Interface started at http://<IP>:5000")

    server_loop()
