import socket
import threading
import subprocess
import os
import queue
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from gpiozero import Motor, DistanceSensor
import json

# --- Configuration Persistence ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "motors": {
        "left": {"forward": 17, "backward": 18, "enable": 23},
        "right": {"forward": 27, "backward": 22, "enable": 24}
    },
    "sensor": {"trigger": 20, "echo": 21} # Default placeholder pins
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

# --- Motor & Sensor Initialization ---
current_config = load_config()
left_motor = None
right_motor = None
distance_sensor = None

def init_peripherals():
    global left_motor, right_motor, distance_sensor, current_config
    
    # Clean up existing objects if any
    if left_motor: left_motor.close()
    if right_motor: right_motor.close()
    if distance_sensor: distance_sensor.close()

    m = current_config["motors"]
    s = current_config["sensor"]
    
    try:
        left_motor = Motor(forward=m["left"]["forward"], backward=m["left"]["backward"], enable=m["left"]["enable"])
        right_motor = Motor(forward=m["right"]["forward"], backward=m["right"]["backward"], enable=m["right"]["enable"])
        print(f"Motors initialized: L({m['left']}), R({m['right']})")
    except Exception as e:
        print(f"Error initializing motors: {e}")

    try:
        if s.get("trigger") and s.get("echo"):
            distance_sensor = DistanceSensor(trigger=s["trigger"], echo=s["echo"])
            print(f"Sensor initialized: Trigger={s['trigger']}, Echo={s['echo']}")
    except Exception as e:
        print(f"Error initializing sensor: {e}")

init_peripherals()

current_speed = 0.5 # Default 0.0-1.0

# --- Global State for Web Interface ---
BT_STATUS = "Disconnected"
BT_CLIENT_INFO = None
BT_DEVICE_NAME = None

# --- Maintenance State ---
log_queue = queue.Queue(maxsize=100)
is_updating = False

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
        /* Terminal Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 2000;
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: #1e1e1e;
            width: 90%;
            max-width: 600px;
            height: 70vh;
            border-radius: 15px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
        }
        .modal-header {
            padding: 15px 20px;
            background: #333;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .terminal-body {
            flex: 1;
            padding: 15px;
            color: #00ff00;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.85rem;
            overflow-y: auto;
            white-space: pre-wrap;
            background: #000;
        }
        .close-btn { cursor: pointer; font-size: 1.5rem; }

        /* Reboot Overlay */
        .reboot-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: var(--primary);
            z-index: 3000;
            color: white;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid rgba(255,255,255,0.3);
            border-top: 5px solid white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .config-grid { display: grid; grid-template-columns: 1fr; gap: 15px; }
        .config-card { background: white; border-radius: 15px; padding: 15px; box-shadow: var(--shadow); }
        .config-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .config-label { font-weight: 600; font-size: 0.9rem; }
        .config-input { width: 60px; padding: 5px; border: 1px solid #ddd; border-radius: 5px; text-align: center; }
        .btn-scan { background: var(--primary); color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; }
        .btn-save { background: var(--success); color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 10px; }
        .scan-result { margin-top: 15px; padding: 10px; background: #e0f2f1; border-radius: 10px; font-size: 0.85rem; display: none; }
        
        /* Admin Dropdown */
        .admin-dropdown { position: relative; display: inline-block; cursor: pointer; }
        .dropdown-content {
            display: none;
            position: absolute;
            right: 0;
            background-color: white;
            min-width: 160px;
            box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
            z-index: 1000;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }
        .dropdown-content a {
            color: black;
            padding: 12px 16px;
            text-decoration: none;
            display: block;
            font-size: 0.9rem;
            text-align: left;
        }
        .dropdown-content a:hover { background-color: #f1f1f1; }
        .admin-dropdown:hover .dropdown-content { display: block; }
    </style>
</head>
<body>
    <div id="terminalModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <span data-t="modal_update_title">System Update</span>
                <span class="close-btn" onclick="closeTerminal()">&times;</span>
            </div>
            <div id="terminalBody" class="terminal-body"></div>
        </div>
    </div>

    <div id="rebootOverlay" class="reboot-overlay">
        <div class="spinner"></div>
        <h2 data-t="rebooting_title">System Rebooting...</h2>
        <p data-t="rebooting_msg">Please wait while the system starts up. Page will reload automatically.</p>
    </div>

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
            <div style="flex: 1; text-align: right;">
                <div class="admin-dropdown">
                    <span style="font-size: 1.5rem; opacity: 0.8;">⚙️</span>
                    <div class="dropdown-content">
                        <a href="#" onclick="startUpdate()" data-t="btn_update">Update (Deploy)</a>
                        <a href="#" onclick="confirmRestart()" data-t="btn_restart">Restart Pi</a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="nav-tabs">
        <div class="tab-link active" onclick="showTab('control')" data-t="tab_control">Управление</div>
        <div class="tab-link" onclick="showTab('config')" data-t="tab_config">Конфигурация</div>
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
                        <div class="motor-pins">
                            <span data-t="pin_fwd">Fwd</span>:{{ config.motors.left.forward }}, 
                            <span data-t="pin_bwd">Bwd</span>:{{ config.motors.left.backward }}, 
                            <span data-t="pin_spd">Spd</span>:{{ config.motors.left.enable }}
                        </div>
                    </div>
                    <div class="motor-side">
                        <div data-t="m_right">Правый мотор</div>
                        <div class="motor-pins">
                            <span data-t="pin_fwd">Fwd</span>:{{ config.motors.right.forward }}, 
                            <span data-t="pin_bwd">Bwd</span>:{{ config.motors.right.backward }}, 
                            <span data-t="pin_spd">Spd</span>:{{ config.motors.right.enable }}
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Configuration Tab -->
        <div id="config" class="tab-content">
            <div class="config-grid">
                <div class="config-card">
                    <h3 style="margin-top:0" data-t="m_left">Левый мотор</h3>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_fwd">Вперед</span>
                        <input type="number" class="config-input" id="cfg_m1_fwd" value="{{ config.motors.left.forward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_bwd">Назад</span>
                        <input type="number" class="config-input" id="cfg_m1_bwd" value="{{ config.motors.left.backward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_spd">Скорость</span>
                        <input type="number" class="config-input" id="cfg_m1_en" value="{{ config.motors.left.enable }}">
                    </div>
                </div>

                <div class="config-card">
                    <h3 style="margin-top:0" data-t="m_right">Правый мотор</h3>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_fwd">Вперед</span>
                        <input type="number" class="config-input" id="cfg_m2_fwd" value="{{ config.motors.right.forward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_bwd">Назад</span>
                        <input type="number" class="config-input" id="cfg_m2_bwd" value="{{ config.motors.right.backward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_spd">Скорость</span>
                        <input type="number" class="config-input" id="cfg_m2_en" value="{{ config.motors.right.enable }}">
                    </div>
                </div>

                <div class="config-card">
                    <h3 style="margin-top:0" data-t="tab_config_sensor">Датчик HC-SR04</h3>
                    <div class="config-row">
                        <span class="config-label">Trigger</span>
                        <input type="number" class="config-input" id="cfg_s_trig" value="{{ config.sensor.trigger }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label">Echo</span>
                        <input type="number" class="config-input" id="cfg_s_echo" value="{{ config.sensor.echo }}">
                    </div>
                    <button class="btn-scan" onclick="scanHCSR04()" data-t="btn_scan">Сканировать HC-SR04</button>
                    <div id="scanResult" class="scan-result"></div>
                </div>

                <button class="btn-save" onclick="saveConfig()" data-t="btn_save">Сохранить и Применить</button>
            </div>
        </div>

        <!-- Admin Tab Removed and moved to Header Dropdown -->

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
                m_right: "Правый мотор",
                modal_update_title: "Обновление системы",
                rebooting_title: "Система перезагружается...",
                rebooting_msg: "Пожалуйста, подождите. Страница обновится автоматически.",
                error_update: "Ошибка при запуске обновления",
                pin_fwd: "Вперед",
                pin_bwd: "Назад",
                pin_spd: "Скорость",
                tab_config: "Конфигурация",
                tab_config_sensor: "Датчик HC-SR04",
                btn_scan: "Сканировать HC-SR04",
                btn_save: "Сохранить и Применить",
                scanning: "Сканирование...",
                scan_not_found: "Устройства не найдены",
                config_saved: "Конфигурация сохранена!"
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
                m_right: "Right Motor",
                modal_update_title: "System Update",
                rebooting_title: "System Rebooting...",
                rebooting_msg: "Please wait. Page will reload automatically.",
                error_update: "Error starting update",
                pin_fwd: "Fwd",
                pin_bwd: "Bwd",
                pin_spd: "Spd",
                tab_config: "Configuration",
                tab_config_sensor: "HC-SR04 Sensor",
                btn_scan: "Scan HC-SR04",
                btn_save: "Save & Apply",
                scanning: "Scanning...",
                scan_not_found: "No devices found",
                config_saved: "Configuration saved!"
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
                m_right: "Motor Derecho",
                modal_update_title: "Actualización del Sistema",
                rebooting_title: "Sistema Reiniciando...",
                rebooting_msg: "Por favor, espere. La página se recargará automáticamente.",
                error_update: "Error al iniciar la actualización",
                pin_fwd: "Avance",
                pin_bwd: "Retro",
                pin_spd: "Veloc",
                tab_config: "Configuración",
                tab_config_sensor: "Sensor HC-SR04",
                btn_scan: "Escanear HC-SR04",
                btn_save: "Guardar y Aplicar",
                scanning: "Escaneando...",
                scan_not_found: "No se encontraron dispositivos",
                config_saved: "¡Configuración guardada!"
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

        let eventSource = null;
        function startUpdate() {
            const terminal = document.getElementById('terminalBody');
            terminal.innerHTML = "";
            document.getElementById('terminalModal').style.display = 'flex';
            
            fetch('/update', { method: 'POST' })
                .then(r => {
                    if (r.ok) {
                        if (eventSource) eventSource.close();
                        eventSource = new EventSource('/stream_logs');
                        eventSource.onmessage = (e) => {
                            terminal.innerText += e.data;
                            terminal.scrollTop = terminal.scrollHeight;
                            if (e.data.includes("DONE")) {
                                eventSource.close();
                            }
                        };
                    } else {
                        const lang = localStorage.getItem('appLang') || 'ru';
                        alert(translations[lang].error_update);
                    }
                });
        }

        function closeTerminal() {
            document.getElementById('terminalModal').style.display = 'none';
            if (eventSource) eventSource.close();
        }

        function confirmRestart() {
            const lang = localStorage.getItem('appLang') || 'ru';
            if (confirm(translations[lang].confirm_restart)) {
                document.getElementById('rebootOverlay').style.display = 'flex';
                fetch('/restart', { method: 'POST' })
                    .then(() => {
                        // Wait for reboot
                        setTimeout(checkServer, 10000);
                    });
            }
        }

        function checkServer() {
            fetch('/')
                .then(r => {
                    if (r.ok) location.reload();
                    else setTimeout(checkServer, 2000);
                })
                .catch(() => setTimeout(checkServer, 2000));
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

        function scanHCSR04() {
            const btn = document.querySelector('.btn-scan');
            const res = document.getElementById('scanResult');
            const lang = localStorage.getItem('appLang') || 'ru';
            
            btn.disabled = true;
            res.style.display = 'block';
            res.textContent = translations[lang].scanning;

            fetch('/config/scan', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success' && data.results.length > 0) {
                        res.innerHTML = "<strong>Найдены устройства:</strong><br>" + 
                            data.results.map(r => `Trigger: ${r.trigger}, Echo: ${r.echo}`).join('<br>');
                        // Suggest first result
                        document.getElementById('cfg_s_trig').value = data.results[0].trigger;
                        document.getElementById('cfg_s_echo').value = data.results[0].echo;
                    } else {
                        res.textContent = translations[lang].scan_not_found;
                    }
                })
                .finally(() => btn.disabled = false);
        }

        function saveConfig() {
            const config = {
                motors: {
                    left: {
                        forward: parseInt(document.getElementById('cfg_m1_fwd').value),
                        backward: parseInt(document.getElementById('cfg_m1_bwd').value),
                        enable: parseInt(document.getElementById('cfg_m1_en').value)
                    },
                    right: {
                        forward: parseInt(document.getElementById('cfg_m2_fwd').value),
                        backward: parseInt(document.getElementById('cfg_m2_bwd').value),
                        enable: parseInt(document.getElementById('cfg_m2_en').value)
                    }
                },
                sensor: {
                    trigger: parseInt(document.getElementById('cfg_s_trig').value),
                    echo: parseInt(document.getElementById('cfg_s_echo').value)
                }
            };

            fetch('/config/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'success') {
                    const lang = localStorage.getItem('appLang') || 'ru';
                    alert(translations[lang].config_saved);
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            });
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
    return render_template_string(HTML_TEMPLATE, status=BT_STATUS, client=BT_CLIENT_INFO, device_name=BT_DEVICE_NAME, connected=is_connected, config=current_config)

@app.route('/config', methods=['GET'])
def get_config():
    return jsonify(current_config)

@app.route('/config/save', methods=['POST'])
def api_save_config():
    global current_config
    new_config = request.json
    save_config(new_config)
    current_config = new_config
    init_peripherals()
    return jsonify({"status": "success"})

@app.route('/config/scan', methods=['POST'])
def api_scan_sensor():
    import time
    from gpiozero import DigitalOutputDevice, DigitalInputDevice
    
    results = []
    # Simplified scan for demo - in reality, we'd loop through possible GPIO pins
    # Common Trigger/Echo candidates
    candidates = [14, 15, 18, 23, 24, 25, 8, 7, 12, 16, 20, 21]
    
    # Let's say we only check a few pairs to avoid hanging
    for trig in [20]:
        for echo in [21]:
            try:
                t = DigitalOutputDevice(trig)
                e = DigitalInputDevice(echo, pull_up=False)
                
                t.on()
                time.sleep(0.00001)
                t.off()
                
                start = time.time()
                timeout = start + 0.1
                while e.value == 0 and time.time() < timeout: pass
                pulse_start = time.time()
                while e.value == 1 and time.time() < timeout: pass
                pulse_end = time.time()
                
                t.close()
                e.close()
                
                if pulse_end - pulse_start > 0:
                    results.append({"trigger": trig, "echo": echo})
            except:
                pass
                
    return jsonify({"status": "success", "results": results})

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
    global is_updating
    if is_updating:
        return "Update already in progress", 400
    
    def run_update():
        global is_updating
        is_updating = True
        try:
            # Clear old logs
            while not log_queue.empty(): log_queue.get()
            
            process = subprocess.Popen(["./deploy.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False)
            for line in process.stdout:
                log_queue.put(line)
            process.wait()
            log_queue.put("DONE\n")
        except Exception as e:
            log_queue.put(f"ERROR: {e}\n")
            log_queue.put("DONE\n")
        finally:
            is_updating = False

    threading.Thread(target=run_update).start()
    return "OK", 200

@app.route('/stream_logs')
def stream_logs():
    def generate():
        while True:
            line = log_queue.get()
            yield f"data: {line}\n\n"
            if line == "DONE\n":
                break
    return Response(generate(), mimetype='text/event-stream')

@app.route('/restart', methods=['POST'])
def restart():
    try:
        def do_reboot():
            import time
            time.sleep(1) # Delay to allow Flask to return response
            subprocess.run(["sudo", "reboot"])
            
        threading.Thread(target=do_reboot).start()
        return "OK", 200
    except Exception as e:
        return f"Error: {e}", 500

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

def process_update_bt(sock):
    global is_updating
    is_updating = True
    try:
        # Clear old logs
        while not log_queue.empty(): log_queue.get()
        
        process = subprocess.Popen(["./deploy.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False)
        for line in process.stdout:
            log_queue.put(line)
            try:
                sock.send(line.encode())
            except:
                pass # Client might have closed
        process.wait()
        log_queue.put("DONE\n")
        try: sock.send("DONE\n".encode())
        except: pass
    except Exception as e:
        err = f"ERROR: {e}\n"
        log_queue.put(err)
        try: sock.send(err.encode())
        except: pass
        log_queue.put("DONE\n")
        try: sock.send("DONE\n".encode())
        except: pass
    finally:
        is_updating = False

def server_loop():
    global BT_STATUS, BT_CLIENT_INFO, BT_DEVICE_NAME

    # Use standard socket instead of PyBluez
    server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    
    # Bind to any adapter on channel 1
    
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
                    elif cmd_str == "UPDATE":
                        print("Update requested via BT")
                        if not is_updating:
                            threading.Thread(target=process_update_bt, args=(client_sock,), daemon=True).start()
                        else:
                            client_sock.send("Update already in progress\n".encode())
                        threading.Thread(target=do_reboot_bt, daemon=True).start()
                    elif cmd_str == "GET_CONFIG":
                        print("Config requested via BT")
                        client_sock.send((json.dumps(current_config) + "\n").encode())
                    elif cmd_str.startswith("SAVE_CONFIG:"):
                        print("Config save requested via BT")
                        try:
                            config_json = cmd_str.split("SAVE_CONFIG:")[1]
                            new_config = json.loads(config_json)
                            save_config(new_config)
                            current_config = new_config
                            init_peripherals()
                            client_sock.send("CONFIG_SAVED\n".encode())
                        except Exception as e:
                            client_sock.send(f"ERROR_SAVING_CONFIG:{e}\n".encode())
                    elif cmd_str == "SCAN_CONFIG":
                        print("Scan requested via BT")
                        # We recycle the scan logic from api_scan_sensor
                        import time
                        from gpiozero import DigitalOutputDevice, DigitalInputDevice
                        results = []
                        # For brevity in BT loop, just check the default/current sensor pins
                        trig, echo = 20, 21
                        try:
                            t = DigitalOutputDevice(trig)
                            e = DigitalInputDevice(echo, pull_up=False)
                            t.on()
                            time.sleep(0.00001)
                            t.off()
                            start = time.time()
                            timeout = start + 0.1
                            while e.value == 0 and time.time() < timeout: pass
                            pulse_start = time.time()
                            while e.value == 1 and time.time() < timeout: pass
                            pulse_end = time.time()
                            t.close()
                            e.close()
                            if pulse_end - pulse_start > 0:
                                results.append({"trigger": trig, "echo": echo})
                        except: pass
                        client_sock.send((json.dumps({"status": "success", "results": results}) + "\n").encode())
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
