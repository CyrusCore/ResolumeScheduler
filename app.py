import json
import time
import requests
import schedule
import threading
import sys
import os
import webview
import socket
import winreg as reg
from datetime import datetime
from flask import Flask, render_template, request, jsonify

def get_base_path():
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_path = get_base_path()
app = Flask(__name__, 
            template_folder=os.path.join(base_path, 'templates'), 
            static_folder=os.path.join(base_path, 'static'))

# ==========================================
# VERSION & GITHUB CONFIG
# ==========================================
APP_VERSION = "1.7.2"
# Format Repo Target: "username/repository-name"
GITHUB_REPO = "CyrusCore/ResolumeScheduler"

# ==========================================
# KONFIGURASI FILE & DIRECTORY
# ==========================================
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
    
SCHEDULE_FILE = os.path.join(application_path, 'schedule.json')
SETTINGS_FILE = os.path.join(application_path, 'settings.json')

def load_settings():
    """Membaca settings resolume dari file dengan dukungan Multi-Server Sync."""
    default_server = {"ip": "127.0.0.1", "port": "8080", "name": "Main", "enabled": True}
    default_settings = {
        "servers": [default_server], 
        "autostart": False, 
        "theme": "blue", 
        "paused": False
    }

    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f, indent=4)
        return default_settings
        
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            # Migrasi dari single IP/Port ke list Servers
            if "servers" not in data:
                old_ip = data.get("ip", "127.0.0.1")
                old_port = data.get("port", "8080")
                data["servers"] = [{"ip": old_ip, "port": old_port, "name": "Main", "enabled": True}]
                if "ip" in data: del data["ip"]
                if "port" in data: del data["port"]
            
            if "autostart" not in data: data["autostart"] = False
            if "paused" not in data: data["paused"] = False
            if "theme" not in data: data["theme"] = "blue"
            return data
    except Exception as e:
        print(f"Error loading settings: {e}")
        return default_settings

def set_autostart(enable=True):
    """Mendaftarkan atau menghapus shortcut startup Windows via Registry"""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "ResolumeScheduler"
    # Dapatkan path executable saat dijalankan ter-compile
    exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
    
    try:
        registry_key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_WRITE)
        if enable:
            reg.SetValueEx(registry_key, app_name, 0, reg.REG_SZ, exe_path)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-Start ENABLED")
        else:
            try:
                reg.DeleteValue(registry_key, app_name)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Auto-Start DISABLED")
            except WindowsError:
                pass # Key tidak ditemukan (sudah mati sebelumnya)
        reg.CloseKey(registry_key)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERR Toggling Auto-Start: {e}")

# Global health status map: { "ip:port": "connected" }
resolume_health = {}

def heartbeat_worker():
    """Thread untuk mengecek koneksi semua server Resolume secara berkala."""
    global resolume_health
    while True:
        settings = load_settings()
        servers = settings.get("servers", [])
        new_health = {}
        
        for srv in servers:
            key = f"{srv['ip']}:{srv['port']}"
            if not srv.get("enabled", True):
                new_health[key] = "disabled"
                continue
                
            try:
                target = f"http://{srv['ip']}:{srv['port']}/api/v1/product"
                response = requests.get(target, timeout=1.5)
                if response.status_code == 200:
                    new_health[key] = "connected"
                else:
                    new_health[key] = "disconnected"
            except:
                new_health[key] = "disconnected"
        
        resolume_health = new_health
        time.sleep(5)


def trigger_clip(layer_index, clip_index, target_time=None, item_id=None, is_follow_up=False):
    """Memicu klip ke SEMUA server Resolume (Broadcast Sync)."""
    settings = load_settings()
    if settings.get("paused", False) and not is_follow_up:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] SKIP TRIGGER (Paused) -> Layer {layer_index} Clip {clip_index}")
        return
        
    servers = settings.get("servers", [])
    
    def send_request(srv):
        if not srv.get("enabled", True): return
        endpoint = f"http://{srv['ip']}:{srv['port']}/api/v1/composition/layers/{layer_index}/clips/{clip_index}/connect"
        try:
            requests.post(endpoint, timeout=3)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] SUCCESS -> {srv['name']} ({srv['ip']})")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] FAILED -> {srv['name']} ({srv['ip']}): {e}")

    # Broadcast ke semua server secara paralel menggunakan threads
    print(f"[{datetime.now().strftime('%H:%M:%S')}] BROADCAST TRIGGER -> Layer {layer_index} Clip {clip_index}")
    threads = []
    for srv in servers:
        t = threading.Thread(target=send_request, args=(srv,))
        t.start()
        threads.append(t)
    
    # Tunggu sebentar (optional) atau biarkan fire & forget
    # Di sini kita tidak menunggu .join() agar tidak memblock scheduler chính.

    # Cari data jadwal untuk handling duration/repeat
    try:
        # Handling schedule removal/persistence
        data = []
        with open(SCHEDULE_FILE, 'r') as f:
            current_data = json.load(f)
            
        found_item = None
        new_data = []
        
        for item in current_data:
            is_match = False
            # Matching logic (using time, layer, column)
            if target_time and str(item.get('time')) == str(target_time) and int(item.get('layer')) == int(layer_index) and int(item.get('column')) == int(clip_index):
                is_match = True
            
            if is_match and not found_item:
                found_item = item
                has_chain = item.get('next_layer') and item.get('next_column')
                
                # Logic Persistence:
                if item.get('repeat', False):
                    # Repeating tasks never complete
                    item['completed'] = False
                    new_data.append(item)
                elif has_chain and not is_follow_up:
                    # Chained task: keep in upcoming during the first trigger
                    item['completed'] = False
                    new_data.append(item)
                else:
                    # Standalone task OR the follow-up of a chain has finished
                    item['completed'] = True
                    new_data.append(item)
            else:
                new_data.append(item)
                
        with open(SCHEDULE_FILE, 'w') as f:
            json.dump(new_data, f, indent=4)
            
        # Handling sub-sequent trigger (Duration Chaining)
        if found_item and not is_follow_up:
            next_l = found_item.get('next_layer')
            next_c = found_item.get('next_column')
            duration_sec = found_item.get('duration', 0)
            
            if next_l and next_c and duration_sec >= 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] QUEUED -> Next Clip in {duration_sec}s")
                threading.Timer(float(duration_sec), trigger_clip, args=[next_l, next_c, None, None, True]).start()

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR handling schedule post-trigger: {e}")
        
    # Jika tidak repeat, return CancelJob
    if found_item and not found_item.get('repeat', False):
        return schedule.CancelJob
    return None

def load_schedule_into_memory():
    """Load schedule from schedule.json back into the Python schedule instance."""
    schedule.clear()
    
    if not os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'w') as f:
            json.dump([], f)
            
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            data = json.load(f)
        for item in data:
            target_time = item.get('time')
            layer = item.get('layer')
            column = item.get('column')
            
            if target_time and layer and column:
                job = schedule.every().day.at(target_time).do(trigger_clip, layer_index=layer, clip_index=column, target_time=target_time)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error saat memuat JSON schedule: {e}")

def run_scheduler():
    """Daemon latar belakang (thread) eksekusi waktu."""
    while True:
        schedule.run_pending()
        time.sleep(1)

def get_local_ip():
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Try to connect to an external server (doesn't actually connect) to see which local IP is used
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

@app.route('/api/network-info', methods=['GET'])
def get_network_info():
    """Returns URL information for accessing the dashboard from other devices."""
    ip = get_local_ip()
    return jsonify({
        "local_ip": ip,
        "port": 5000,
        "full_url": f"http://{ip}:5000"
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """Returns aggregate connection status for all servers."""
    settings = load_settings()
    servers = settings.get("servers", [])
    
    enabled_servers = [s for s in servers if s.get("enabled", True)]
    total = len(enabled_servers)
    connected = 0
    
    for srv in enabled_servers:
        key = f"{srv['ip']}:{srv['port']}"
        if resolume_health.get(key) == "connected":
            connected += 1
            
    return jsonify({
        "status": "connected" if connected > 0 else "disconnected",
        "detailed_health": resolume_health,
        "servers_summary": f"{connected}/{total}",
        "paused": settings.get("paused", False)
    })

@app.route('/api/trigger-now', methods=['POST'])
def trigger_now():
    try:
        data = request.json
        layer = data.get('layer')
        column = data.get('column')
        if layer and column:
            # Manual trigger ignores paused state
            trigger_clip(layer, column, is_follow_up=True)
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "Invalid data"}), 400

@app.route('/api/pause', methods=['POST'])
def toggle_pause():
    try:
        settings = load_settings()
        is_paused = request.json.get('paused', False)
        settings['paused'] = is_paused
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        return jsonify({"success": True, "paused": is_paused})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html', version=APP_VERSION)

@app.route('/api/schedule', methods=['GET', 'POST'])
def manage_schedule():
    if request.method == 'GET':
        try:
            with open(SCHEDULE_FILE, 'r') as f:
                return jsonify(json.load(f))
        except:
            return jsonify([])
            
    elif request.method == 'POST':
        try:
            with open(SCHEDULE_FILE, 'w') as f:
                json.dump(request.json, f, indent=4)
            load_schedule_into_memory()
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if request.method == 'GET':
        return jsonify(load_settings())
    elif request.method == 'POST':
        try:
            req_data = request.json
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(req_data, f, indent=4)
            
            if 'autostart' in req_data:
                set_autostart(req_data['autostart'])
                
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/app-version', methods=['GET'])
def get_app_version():
    """Returns current app version."""
    return jsonify({"version": APP_VERSION.strip()})

@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Mengecek rilisan terbaru di GitHub secara diam-diam."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest_tag = data.get("tag_name", "")
            latest_version = latest_tag.replace("v", "").strip()
            current_version = APP_VERSION.strip()
            
            if latest_version and latest_version != current_version:
                return jsonify({
                    "update_available": True,
                    "latest_version": latest_version,
                    "current_version": current_version,
                    "url": data.get("html_url"),
                    "notes": data.get("body", "")
                })
        return jsonify({"update_available": False})
    except Exception as e:
        return jsonify({"update_available": False, "error": str(e)})

def start_flask():
    """Runs the Flask server to allow access from the local network."""
    # use_reloader=False is crucial to avoid conflicts with other threads
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    load_schedule_into_memory()
    
    # Jalankan scheduler di background
    threading.Thread(target=run_scheduler, daemon=True).start()
    
    # Jalankan heartbeat di background
    threading.Thread(target=heartbeat_worker, daemon=True).start()

    # Jalankan Flask di background agar bisa diakses dari Mobile (0.0.0.0)
    threading.Thread(target=start_flask, daemon=True).start()
    
    # Beri waktu sebentar untuk flask startup sebelum GUI muncul
    time.sleep(1)

    window = webview.create_window(
        title=f'Resolume Scheduler v{APP_VERSION}', 
        url='http://127.0.0.1:5000',
        width=540, 
        height=980, 
        background_color='#09090b',
        min_size=(440, 700)
    )
    
    webview.start()
