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
APP_VERSION = "1.6.1"
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
        default_settings = {"ip": "127.0.0.1", "port": "8080", "autostart": False, "theme": "blue", "paused": False}
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f)
        return default_settings
        
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            if "autostart" not in data: data["autostart"] = False
            if "paused" not in data: data["paused"] = False
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

# Global health status
resolume_health = {"status": "disconnected", "last_check": 0}

def heartbeat_worker():
    """Thread untuk mengecek koneksi Resolume secara berkala."""
    global resolume_health
    while True:
        try:
            target = f"{get_base_url()}/product"
            response = requests.get(target, timeout=2)
            if response.status_code == 200:
                resolume_health = {"status": "connected", "last_check": time.time()}
            else:
                resolume_health = {"status": "disconnected", "last_check": time.time()}
        except:
            resolume_health = {"status": "disconnected", "last_check": time.time()}
        time.sleep(5)

def trigger_clip(layer_index, clip_index, target_time=None, item_id=None, is_follow_up=False):
    """Memicu klip spesifik di Resolume secara terprogram."""
    settings = load_settings()
    if settings.get("paused", False) and not is_follow_up:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] SKIP TRIGGER (Paused) -> Layer {layer_index} Clip {clip_index}")
        return
        
    endpoint = f"{get_base_url()}/composition/layers/{layer_index}/clips/{clip_index}/connect"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] TRIGGER -> {endpoint}")
    
    try:
        requests.post(endpoint, timeout=4)
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR Triggering Resolume: {e}")
        return # Jangan cancel job kalau gagal, mungkin mau coba lagi? Tapi kita skip aja dulu.

    # Cari data jadwal untuk handling duration/repeat
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            data = json.load(f)
            
        new_data = []
        found_item = None
        
        for item in data:
            # Match item (by time, layer, column as fallback or use a UUID if we had one)
            is_match = False
            if target_time and str(item.get('time')) == str(target_time) and int(item.get('layer')) == int(layer_index) and int(item.get('column')) == int(clip_index):
                is_match = True
            
            if is_match and not found_item:
                found_item = item
                # Jika repeat: true, simpan kembali
                if item.get('repeat', False):
                    new_data.append(item)
                # Jika tidak repeat, jangan masukkan ke new_data (auto-delete)
            else:
                new_data.append(item)
                
        # Simpan perubahan ke schedule.json
        with open(SCHEDULE_FILE, 'w') as f:
            json.dump(new_data, f, indent=4)
            
        # Handling sub-sequent trigger (Duration)
        if found_item and found_item.get('duration') and int(found_item['duration']) > 0:
            next_l = found_item.get('next_layer')
            next_c = found_item.get('next_column')
            duration_sec = int(found_item['duration']) * 60
            
            if next_l and next_c:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] QUEUED -> Next Clip in {found_item['duration']} min")
                threading.Timer(duration_sec, trigger_clip, args=[next_l, next_c, None, None, True]).start()

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR handling schedule post-trigger: {e}")
        
    # Jika tidak repeat, return CancelJob
    if found_item and not found_item.get('repeat', False):
        return schedule.CancelJob
    return None

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
                job = schedule.every().day.at(target_time).do(trigger_clip, layer_index=layer, clip_index=column, target_time=target_time)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error saat memuat JSON schedule: {e}")

def run_scheduler():
    """Daemon latar belakang (thread) eksekusi waktu."""
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route('/api/open-file-dialog', methods=['GET'])
def open_file_dialog():
    """Membuka dialog file native melalui pywebview."""
    if not webview.windows:
        return jsonify({"success": False, "error": "No window found"}), 500
    
    file_types = ('Video Files (*.mp4;*.mkv;*.mov;*.avi;*.m4v)', 'All files (*.*)')
    # Menggunakan window pertama yang aktif
    result = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
    
    if result:
        # result adalah tuple dari path yang dipilih
        path = result[0] if isinstance(result, (list, tuple)) else result
        return jsonify({"success": True, "path": path})
    return jsonify({"success": False, "path": None})

@app.route('/api/media-health', methods=['POST'])
def check_media_health():
    """Mengecek keberadaan dan status file di disk."""
    try:
        paths = request.json.get('paths', [])
        results = {}
        for path in paths:
            if not path: continue
            if not os.path.exists(path):
                results[path] = "missing"
            elif os.path.getsize(path) == 0:
                results[path] = "corrupt"
            else:
                results[path] = "ok"
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        "status": resolume_health["status"],
        "paused": load_settings().get("paused", False)
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
    """Mengembalikan versi aplikasi saat ini."""
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

if __name__ == '__main__':
    load_schedule_into_memory()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    heartbeat_thread.start()
    
    window = webview.create_window(
        title='Resolume Auto-Trigger', 
        url=app,
        width=520, 
        height=960, 
        background_color='#09090b'
    )
    
    webview.start()
