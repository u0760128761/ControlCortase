import socket
import threading
import subprocess
import os
import queue
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from gpiozero import Motor, DistanceSensor
import json

# --- Global Logging ---
class LogManager:
    def __init__(self):
        self.listeners = []
        self.history = []
        self.lock = threading.Lock()

    def add_listener(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            # Play back history to new listener
            print(f"New log listener added. Playing back {len(self.history)} history lines.")
            for msg in self.history:
                try: q.put(msg, block=False)
                except: pass
            self.listeners.append(q)
        return q

    def remove_listener(self, q):
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def broadcast(self, msg):
        msg_line = f"{msg}" # Raw text without newline
        print(msg) # Still print to console
        with self.lock:
            self.history.append(msg_line)
            if len(self.history) > 50:
                self.history.pop(0)
            for q in self.listeners:
                try:
                    q.put(msg_line, block=False)
                except queue.Full:
                    try: 
                        q.get_nowait()
                        q.put(msg_line)
                    except: pass

log_manager = LogManager()
is_updating = False

def log_msg(msg):
    log_manager.broadcast(msg)

# --- Catalog & Configuration ---
CATALOG = {
    "motor": {"default_name": "Motor", "pins": ["forward", "backward", "enable"]},
    "hcsr04": {"default_name": "HC-SR04 Sensor", "pins": ["trigger", "echo"]}
}

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "devices": [
        {"id": "m1", "type": "motor", "name": "Left Motor", "pins": {"forward": 17, "backward": 18, "enable": 23}, "role": "move_left"},
        {"id": "m2", "type": "motor", "name": "Right Motor", "pins": {"forward": 27, "backward": 22, "enable": 24}, "role": "move_right"},
        {"id": "s1", "type": "hcsr04", "name": "HC-SR04 Sensor", "pins": {"trigger": 20, "echo": 21}}
    ]
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                # Migration: old format had "motors" and "sensor"
                if "devices" not in config:
                    log_msg("Migrating legacy config...")
                    new_devices = []
                    if "motors" in config:
                        m = config["motors"]
                        new_devices.append({"id": "m1", "type": "motor", "name": "Left Motor", "pins": m["left"], "role": "move_left"})
                        new_devices.append({"id": "m2", "type": "motor", "name": "Right Motor", "pins": m["right"], "role": "move_right"})
                    if "sensor" in config:
                        new_devices.append({"id": "s1", "type": "hcsr04", "name": "HC-SR04 Sensor", "pins": config["sensor"]})
                    config = {"devices": new_devices}
                    save_config(config)
                return config
        except Exception as e:
            log_msg(f"Error loading config: {e}")
    return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log_msg(f"Error saving config: {e}")

# --- Peripheral Registry ---
current_config = load_config()
peripherals = {} # Map ID or Role to gpiozero object

def init_peripherals():
    global peripherals, current_config
    
    # Clean up
    for p in peripherals.values():
        try: p.close()
        except: pass
    peripherals = {}

    for dev in current_config.get("devices", []):
        try:
            dtype = dev.get("type")
            pins = dev.get("pins", {})
            p_obj = None
            
            if dtype == "motor":
                p_obj = Motor(forward=pins["forward"], backward=pins["backward"], enable=pins["enable"])
            elif dtype == "hcsr04":
                p_obj = DistanceSensor(trigger=pins["trigger"], echo=pins["echo"])
            
            if p_obj:
                peripherals[dev["id"]] = p_obj
                if dev.get("role"):
                    peripherals[dev["role"]] = p_obj
                log_msg(f"Peripheral initialized: {dev['name']} ({dev['id']})")
        except Exception as e:
            log_msg(f"Error initializing device {dev.get('name')}: {e}")

init_peripherals()

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
        log_msg(f"Error resolving BT name: {e}")
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
        .scan-result { margin-top: 15px; padding: 10px; background: #e0f2f1; border-radius: 10px; font-size: 0.85rem; display: none; }
        
        /* Dynamic Config Cards */
        .config-card { background: white; border-radius: 15px; padding: 15px; box-shadow: var(--shadow); position: relative; }
        .config-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .config-card-title { margin: 0; font-size: 1rem; flex: 1; }
        .config-name-input { border: none; font-weight: bold; font-size: 1rem; width: 100%; color: var(--text-main); }
        .config-name-input:focus { outline: none; border-bottom: 1px solid var(--primary); }
        .btn-delete { color: var(--danger); cursor: pointer; font-size: 1.2rem; opacity: 0.6; transition: 0.2s; }
        .btn-delete:hover { opacity: 1; }
        
        .btn-add { background: var(--primary); color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; font-weight: bold; }
        
        .role-badge { 
            position: absolute; 
            top: -10px; 
            left: 15px; 
            background: var(--warning); 
            color: white; 
            padding: 2px 10px; 
            border-radius: 10px; 
            font-size: 0.7rem; 
            font-weight: bold;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .config-card.has-role { border: 2px solid var(--warning); }
        
        /* Integrated Terminal */
        .terminal-integrated {
            margin-top: 20px;
            background: #000;
            color: #00ff00;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.8rem;
            padding: 10px;
            border-radius: 10px;
            height: 150px;
            overflow-y: auto;
            white-space: pre-wrap;
            border: 1px solid #333;
            box-shadow: inset 0 0 10px rgba(0,255,0,0.1);
        }
        .terminal-header {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
            color: rgba(0,255,0,0.5);
            display: flex;
            justify-content: space-between;
        }
        
        /* Admin Dropdown */
        .admin-dropdown { position: relative; display: inline-block; cursor: pointer; }
        .dropdown-content {
            display: none;
            position: absolute;
            right: 0;
            top: 100%;
            background-color: white;
            min-width: 160px;
            box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
            z-index: 1000;
            border-radius: 10px;
            overflow: hidden;
            padding-top: 5px; /* Visual gap padding */
        }
        /* Hover Bridge to prevent premature closing */
        .admin-dropdown::after {
            content: '';
            position: absolute;
            left: 0;
            right: 0;
            bottom: -15px;
            height: 15px;
            z-index: 999;
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
            <div id="term-update" class="terminal-body"></div>
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
                            {% if m_left %}
                                <span data-t="pin_fwd">Fwd</span>:{{ m_left.pins.forward }}, 
                                <span data-t="pin_bwd">Bwd</span>:{{ m_left.pins.backward }}, 
                                <span data-t="pin_spd">Spd</span>:{{ m_left.pins.enable }}
                            {% else %}
                                <span style="color:red">Role move_left not assigned</span>
                            {% endif %}
                        </div>
                    </div>
                    <div class="motor-side">
                        <div data-t="m_right">Правый мотор</div>
                        <div class="motor-pins">
                            {% if m_right %}
                                <span data-t="pin_fwd">Fwd</span>:{{ m_right.pins.forward }}, 
                                <span data-t="pin_bwd">Bwd</span>:{{ m_right.pins.backward }}, 
                                <span data-t="pin_spd">Spd</span>:{{ m_right.pins.enable }}
                            {% else %}
                                <span style="color:red">Role move_right not assigned</span>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            <div class="terminal-integrated">
                <div class="terminal-header">
                    <span>Terminal / Control</span>
                    <span id="term-status-control">● Live</span>
                </div>
                <div id="term-control"></div>
            </div>
        </div>

        <!-- Configuration Tab -->
        <div id="config" class="tab-content">
            <div class="config-grid" id="configGrid">
                {% for dev in sorted_devices %}
                <div class="config-card {{ 'has-role' if dev.role else '' }}" data-id="{{ dev.id }}" data-type="{{ dev.type }}">
                    {% if dev.role %}
                    <div class="role-badge">PRIMARY CONTROL: {{ dev.role }}</div>
                    {% endif %}
                    <div class="config-card-header">
                        <input type="text" class="config-name-input" value="{{ dev.name }}" onchange="markDirty()">
                        <span class="btn-delete" onclick="deleteDevice('{{ dev.id }}')">&times;</span>
                    </div>
                    
                    {% if dev.type == 'motor' %}
                    <div class="config-row">
                        <span class="config-label" data-t="pin_fwd">Вперед</span>
                        <input type="number" class="config-input" data-pin="forward" value="{{ dev.pins.forward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_bwd">Назад</span>
                        <input type="number" class="config-input" data-pin="backward" value="{{ dev.pins.backward }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label" data-t="pin_spd">Скорость</span>
                        <input type="number" class="config-input" data-pin="enable" value="{{ dev.pins.enable }}">
                    </div>
                    {% elif dev.type == 'hcsr04' %}
                    <div class="config-row">
                        <span class="config-label">Trigger</span>
                        <input type="number" class="config-input" data-pin="trigger" value="{{ dev.pins.trigger }}">
                    </div>
                    <div class="config-row">
                        <span class="config-label">Echo</span>
                        <input type="number" class="config-input" data-pin="echo" value="{{ dev.pins.echo }}">
                    </div>
                    <button class="btn-scan" onclick="scanHCSR04('{{ dev.id }}')" data-t="btn_scan">Сканировать HC-SR04</button>
                    <div id="scanResult_{{ dev.id }}" class="scan-result"></div>
                    {% endif %}

                    {% if dev.role %}
                    <div style="margin-top: 10px; font-size: 0.7rem; color: var(--text-sub);">
                        Role: <strong>{{ dev.role }}</strong>
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>

            <div class="add-device-section">
                <select id="catalogSelect" class="catalog-select">
                    <option value="motor">New Motor</option>
                    <option value="hcsr04">New HC-SR04 Sensor</option>
                </select>
                <button class="btn-add" onclick="addDevice()">+ Add Device</button>
            </div>

            <button class="btn-save" onclick="saveConfig()" data-t="btn_save" style="margin-top: 20px;">Сохранить и Применить</button>

            <div class="terminal-integrated">
                <div class="terminal-header">
                    <span>Terminal / Configuration</span>
                    <span id="term-status-config">● Live</span>
                </div>
                <div id="term-config"></div>
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
            const terminalModal = document.getElementById('term-update');
            terminalModal.innerHTML = "";
            document.getElementById('terminalModal').style.display = 'flex';
            
            fetch('/update', { method: 'POST' })
                .then(r => {
                    if (!r.ok) console.error("Error starting update");
                })
                .catch(e => console.error('Error:', e));
        }

        function initLogStream() {
            const terms = [
                document.getElementById('term-control'),
                document.getElementById('term-config'),
                document.getElementById('term-update')
            ];

            if (eventSource) eventSource.close();
            eventSource = new EventSource('/stream_logs');
            
            eventSource.onmessage = (e) => {
                if (e.data === "HEARTBEAT") return;
                const msg = e.data + "\\n";
                terms.forEach(term => {
                    if (term) {
                        term.innerText += msg;
                        term.scrollTop = term.scrollHeight;
                    }
                });
            };

            eventSource.onerror = (e) => {
                console.warn("Log stream disconnected, retrying...");
                eventSource.close();
                setTimeout(initLogStream, 3000);
            };
        }

        // Initialize log stream on load
        window.addEventListener('load', () => {
            applyTranslations();
            const activeTab = localStorage.getItem('activeTab') || 'control';
            showTab(activeTab);
            initLogStream();
        });

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

        function addDevice() {
            const type = document.getElementById('catalogSelect').value;
            const id = "dev_" + Math.random().toString(36).substr(2, 5);
            const name = type === 'motor' ? 'New Motor' : 'New Sensor';
            
            const grid = document.getElementById('configGrid');
            const card = document.createElement('div');
            card.className = "config-card";
            card.dataset.id = id;
            card.dataset.type = type;

            let pinsHtml = "";
            if (type === 'motor') {
                pinsHtml = `
                    <div class="config-row"><span class="config-label">Fwd</span><input type="number" class="config-input" data-pin="forward" value="0"></div>
                    <div class="config-row"><span class="config-label">Bwd</span><input type="number" class="config-input" data-pin="backward" value="0"></div>
                    <div class="config-row"><span class="config-label">Spd</span><input type="number" class="config-input" data-pin="enable" value="0"></div>
                `;
            } else {
                pinsHtml = `
                    <div class="config-row"><span class="config-label">Trig</span><input type="number" class="config-input" data-pin="trigger" value="0"></div>
                    <div class="config-row"><span class="config-label">Echo</span><input type="number" class="config-input" data-pin="echo" value="0"></div>
                `;
            }

            card.innerHTML = `
                <div class="config-card-header">
                    <input type="text" class="config-name-input" value="${name}">
                    <span class="btn-delete" onclick="deleteDevice('${id}')">&times;</span>
                </div>
                ${pinsHtml}
            `;
            grid.appendChild(card);
        }

        function deleteDevice(id) {
            const card = document.querySelector(`.config-card[data-id="${id}"]`);
            if (card) card.remove();
        }

        function markDirty() { /* Visual feedback for unsaved changes could go here */ }

        function scanHCSR04(id) {
            const res = document.getElementById('scanResult_' + id);
            const lang = localStorage.getItem('appLang') || 'ru';
            if (res) {
                res.style.display = 'block';
                res.textContent = translations[lang].scanning;
            }

            fetch('/config/scan', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.status === 'success' && data.results.length > 0) {
                        const card = document.querySelector(`.config-card[data-id="${id}"]`);
                        card.querySelector('[data-pin="trigger"]').value = data.results[0].trigger;
                        card.querySelector('[data-pin="echo"]').value = data.results[0].echo;
                        if (res) res.textContent = "Done!";
                    } else {
                        if (res) res.textContent = translations[lang].scan_not_found;
                    }
                });
        }

        function saveConfig() {
            const devices = [];
            document.querySelectorAll('.config-card').forEach(card => {
                const dev = {
                    id: card.dataset.id,
                    type: card.dataset.type,
                    name: card.querySelector('.config-name-input').value,
                    pins: {}
                };
                card.querySelectorAll('.config-input').forEach(input => {
                    dev.pins[input.dataset.pin] = parseInt(input.value);
                });
                
                // Preserve roles if they exist
                const roleEl = card.querySelector('strong');
                if (roleEl) dev.role = roleEl.textContent;

                devices.push(dev);
            });

            fetch('/config/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ devices: devices })
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
    # Find motors by role for the Control tab display
    m_left = next((d for d in current_config.get("devices", []) if d.get("role") == "move_left"), None)
    m_right = next((d for d in current_config.get("devices", []) if d.get("role") == "move_right"), None)
    
    # Sort devices so motors with roles are at the top
    sorted_devices = sorted(current_config.get("devices", []), 
                           key=lambda x: (x.get("role") is None, x.get("id")))

    return render_template_string(HTML_TEMPLATE, 
                                status=BT_STATUS, 
                                client=BT_CLIENT_INFO, 
                                device_name=BT_DEVICE_NAME, 
                                connected=is_connected, 
                                config=current_config,
                                m_left=m_left,
                                m_right=m_right,
                                sorted_devices=sorted_devices)

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
    msg = f"Movement CMD: {cmd}"
    log_msg(msg)
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
            process = subprocess.Popen(["./deploy.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False)
            for line in process.stdout:
                log_msg(line.strip())
            process.wait()
            log_msg("DONE")
        except Exception as e:
            log_msg(f"ERROR: {e}")
            log_msg("DONE")
        finally:
            is_updating = False

    threading.Thread(target=run_update).start()
    return "OK", 200

@app.route('/stream_logs')
def stream_logs():
    def generate():
        q = log_manager.add_listener()
        try:
            while True:
                try:
                    line = q.get(timeout=20)
                    yield f"data: {line}\n\n"
                except queue.Empty:
                    yield "data: HEARTBEAT\n\n"
        finally:
            log_manager.remove_listener(q)
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
    # motor_id 1 = move_left, motor_id 2 = move_right (legacy support)
    role = "move_left" if motor_id == 1 else "move_right"
    motor = peripherals.get(role)
    
    if not motor:
        log_msg(f"No motor with role {role} found")
        return

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
        process = subprocess.Popen(["./deploy.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=False)
        for line in process.stdout:
            log_msg(line.strip())
            try:
                sock.send((line.strip() + "\n").encode())
            except:
                pass # Client might have closed
        process.wait()
        log_msg("DONE")
        try: sock.send("DONE\n".encode())
        except: pass
    except Exception as e:
        err = f"ERROR: {e}"
        log_msg(err)
        try: sock.send((err + "\n").encode())
        except: pass
        log_msg("DONE")
        try: sock.send("DONE\n".encode())
        except: pass
    finally:
        is_updating = False

def server_loop():
    global BT_STATUS, BT_CLIENT_INFO, BT_DEVICE_NAME, current_config

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
            log_msg(f"Accepted connection from {client_info}")
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
                        log_msg("Decode error")
                        continue
                        
                    log_msg(f"Received from BT: {cmd_str}")
                    
                    # Protocol Handling
                    if cmd_str.startswith("SPEED:"):
                        global current_speed
                        try:
                            val = int(cmd_str.split(":")[1])
                            current_speed = map_speed(val)
                            # Re-apply current speed to active motors
                            for p in peripherals.values():
                                if isinstance(p, Motor) and p.is_active:
                                    p.value = (p.value / abs(p.value)) * current_speed if p.value != 0 else 0
                            log_msg(f"Speed set to {current_speed*100}%")
                        except ValueError:
                            log_msg("Invalid Speed Value")
                    elif cmd_str == "UPDATE":
                        log_msg("Update requested via BT")
                        if not is_updating:
                            threading.Thread(target=process_update_bt, args=(client_sock,), daemon=True).start()
                        else:
                            client_sock.send("Update already in progress\n".encode())
                        threading.Thread(target=do_reboot_bt, daemon=True).start()
                    elif cmd_str == "GET_CONFIG":
                        log_msg(f"Config requested via BT from {BT_CLIENT_INFO}")
                        cfg_str = json.dumps(current_config)
                        log_msg(f"Sending config (len={len(cfg_str)})")
                        client_sock.send((cfg_str + "\n").encode())
                    elif cmd_str.startswith("SAVE_CONFIG:"):
                        log_msg("Config save requested via BT")
                        try:
                            config_json = cmd_str.split("SAVE_CONFIG:")[1]
                            new_config = json.loads(config_json)
                            save_config(new_config)
                            current_config = new_config
                            init_peripherals()
                            client_sock.send("CONFIG_SAVED\n".encode())
                            log_msg("Config saved and peripherals re-initialized")
                        except Exception as e:
                            client_sock.send(f"ERROR_SAVING_CONFIG:{e}\n".encode())
                    elif cmd_str == "SCAN_CONFIG":
                        log_msg("Scan requested via BT")
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
                log_msg("Connection disconnected")
                BT_STATUS = "Disconnected"
                BT_CLIENT_INFO = None
                BT_DEVICE_NAME = None
            
            client_sock.close()
            log_msg("Client closed. Waiting for new connection...")
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
