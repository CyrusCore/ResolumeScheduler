import json
import time
import requests
import schedule
import threading
import sys
import os
import webview
import winreg as reg
from datetime import datetime
from flask import Flask, render_template, request, jsonify

def get_base_path():
    """Mendapatkan absolute path resource, perlu saat dijadikan EXE dengan PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_path = get_base_path()
app = Flask(__name__, 
            template_folder=os.path.join(base_path, 'templates'), 
            static_folder=os.path.join(base_path, 'static'))

# ==========================================
# KONFIGURASI VERSI & GITHUB REPO
# ==========================================
APP_VERSION = "1.5.1"
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
    """Membaca settings resolume dari file."""
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {"ip": "127.0.0.1", "port": "8080", "autostart": False}
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f)
        return default_settings
        
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            if "autostart" not in data:
                data["autostart"] = False
            return data
    except:
        return {"ip": "127.0.0.1", "port": "8080", "autostart": False}

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

def get_base_url():
    """Mengembalikan URL target dinamis berdasarkan file settings API."""
    settings = load_settings()
    ip = settings.get("ip", "127.0.0.1")
    port = settings.get("port", "8080")
    return f"http://{ip}:{port}/api/v1"

def trigger_clip(layer_index, clip_index, target_time):
    """Memicu klip spesifik di Resolume secara terprogram."""
    endpoint = f"{get_base_url()}/composition/layers/{layer_index}/clips/{clip_index}/connect"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] TRIGGER -> {endpoint}")
    try:
        requests.post(endpoint, timeout=4)
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR Triggering Resolume: {e}")
        
    # Auto-Delete dari schedule.json
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            data = json.load(f)
            
        new_data = []
        removed = False
        for item in data:
            if not removed and item.get('time') == target_time and int(item.get('layer')) == int(layer_index) and int(item.get('column')) == int(clip_index):
                removed = True
                continue
            new_data.append(item)
            
        with open(SCHEDULE_FILE, 'w') as f:
            json.dump(new_data, f, indent=4)
            
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR Auto-delete schedule: {e}")
        
    # Return CancelJob untuk menjamin triggernya 'run once'
    return schedule.CancelJob

def load_schedule_into_memory():
    """Memuat jadwal dari schedule.json kembali ke instance schedule Python."""
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
                schedule.every().day.at(target_time).do(trigger_clip, layer_index=layer, clip_index=column, target_time=target_time)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error saat memuat JSON schedule: {e}")

def run_scheduler():
    """Daemon latar belakang (thread) eksekusi waktu."""
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        target = f"{get_base_url()}/product"
        response = requests.get(target, timeout=0.8)
        if response.status_code == 200:
            return jsonify({"status": "connected", "url": target})
    except:
        pass
    return jsonify({"status": "disconnected"})

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

@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Mengecek rilisan terbaru di GitHub secara diam-diam."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest_tag = data.get("tag_name", "")
            # Sederhanakan format tag "v1.5.2" menjadi "1.5.2"
            latest_version = latest_tag.replace("v", "")
            
            if latest_version and latest_version != APP_VERSION:
                return jsonify({
                    "update_available": True,
                    "latest_version": latest_version,
                    "url": data.get("html_url"),
                    "notes": data.get("body", "Pembaruan minor/major baru telah dirilis.")
                })
        return jsonify({"update_available": False})
    except Exception as e:
        return jsonify({"update_available": False, "error": str(e)})

if __name__ == '__main__':
    load_schedule_into_memory()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    window = webview.create_window(
        title='Resolume Auto-Trigger', 
        url=app,
        width=520, 
        height=800, 
        background_color='#09090b'
    )
    
    webview.start()
