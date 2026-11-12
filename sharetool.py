import tkinter as tk
import json
import re
import time
import asyncio
import threading
import queue
import os
import sys
import ssl
import subprocess
import urllib.request
import urllib.parse
import platform
from tkinter import messagebox

# ==========================================
# KHẮC PHỤC TRIỆT ĐỂ LỖI SSL TRÊN MACOS & WINDOWS
# ==========================================
def get_ssl_context():
    """Tạo SSL context an toàn với certifi, tự động fallback nếu chạy trên máy thiếu chứng chỉ"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl._create_unverified_context()
        return ctx

SSL_CONTEXT = get_ssl_context()
ssl._create_default_https_context = lambda: SSL_CONTEXT

# Kích hoạt DPI Awareness cho Windows để chống mờ/méo giao diện
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ==========================================
# 0. QUẢN LÝ ĐƯỜNG DẪN ĐÓNG GÓI CHUẨN MAC & WIN
# ==========================================
def get_bundle_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if sys.platform == "darwin" and ".app/Contents/MacOS" in exe_dir:
            return os.path.abspath(os.path.join(exe_dir, "../../.."))
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))

BUNDLE_DIR = get_bundle_dir()
APP_DIR = get_app_data_dir()

# ==========================================
# CƠ CHẾ AUTO-UPDATE THÔNG MINH (HỖ TRỢ CẢ BẢN BUILD)
# ==========================================
BASE_URL = "https://raw.githubusercontent.com/hoanmihjob/Netfix_VeoVeo/main/"
FILES_TO_SYNC = [
    "sharetool.py",
    "templates.json",
    "startup.mp3",
    "alert.aiff"
]

def get_local_sync_path(file_name):
    """Luôn lưu và kiểm tra file cập nhật tại thư mục chứa ứng dụng (APP_DIR)"""
    return os.path.join(APP_DIR, file_name)

def check_update_available():
    """Kiểm tra xem có file nào khác biệt trên GitHub hay không (chỉ đọc, không ghi đè)"""
    try:
        for file_name in FILES_TO_SYNC:
            local_path = get_local_sync_path(file_name)
            # Nếu đang chạy bản đóng gói mà chưa từng tải file lẻ về APP_DIR thì lấy file trong BUNDLE_DIR để đối chiếu
            if not os.path.exists(local_path):
                bundled_candidate = os.path.join(BUNDLE_DIR, file_name)
                if os.path.exists(bundled_candidate):
                    local_path = bundled_candidate

            remote_url = f"{BASE_URL}{file_name}?t={int(time.time())}"
            try:
                req = urllib.request.Request(remote_url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
                with urllib.request.urlopen(req, timeout=4, context=SSL_CONTEXT) as resp:
                    remote_data = resp.read()
            except Exception:
                continue

            if not remote_data:
                continue

            if not os.path.exists(local_path):
                # Bỏ qua việc báo update nếu là sharetool.py nằm ẩn trong gói exe lần đầu chạy
                if file_name == "sharetool.py" and getattr(sys, 'frozen', False):
                    continue
                return True

            with open(local_path, "rb") as f:
                local_data = f.read()

            if file_name.endswith((".py", ".json")):
                norm_remote = remote_data.replace(b"\r\n", b"\n").strip()
                norm_local = local_data.replace(b"\r\n", b"\n").strip()
                if norm_remote != norm_local:
                    return True
            else:
                if remote_data != local_data:
                    return True
    except Exception:
        pass
    return False

def apply_full_update(app_instance=None):
    """Tải song song file mới, cập nhật UI real-time và khởi động lại ứng dụng mượt mà trên cả Mac & Win"""
    import concurrent.futures

    def _update_status(main_msg, sub_msg, mode="loading"):
        if app_instance and hasattr(app_instance, "root") and app_instance.root.winfo_exists():
            app_instance.root.after(0, lambda: app_instance.set_banner_status(main_msg, sub_msg, mode=mode))

    try:
        total_files = len(FILES_TO_SYNC)
        completed = [0]

        def _download_single(file_name):
            local_path = get_local_sync_path(file_name)
            remote_url = f"{BASE_URL}{file_name}?t={int(time.time())}"
            req = urllib.request.Request(remote_url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(req, timeout=12, context=SSL_CONTEXT) as resp:
                remote_data = resp.read()
            if remote_data:
                # Ghi ra file tạm trước để chống hỏng file
                tmp_path = local_path + ".tmp"
                with open(tmp_path, "wb") as f:
                    f.write(remote_data)
                os.replace(tmp_path, local_path)
            completed[0] += 1
            _update_status("Đang cập nhật...", f"Đã tải {completed[0]}/{total_files} file: {file_name}", mode="loading")
            return file_name

        _update_status("Đang tải dữ liệu mới...", "Đang kết nối tới máy chủ GitHub...", mode="loading")

        # Tải song song cả 4 file cùng lúc (tăng tốc 3x-4x)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(_download_single, FILES_TO_SYNC))

        _update_status("Tải xong bản cập nhật!", "Đang khởi động lại ứng dụng...", mode="success")
        time.sleep(0.4)

        def _restart_app():
            try:
                try:
                    TG_MANAGER.shutdown()
                except Exception:
                    pass
                if app_instance and hasattr(app_instance, "root") and app_instance.root.winfo_exists():
                    app_instance.root.destroy()
            except Exception:
                pass
            
            executable = sys.executable
            if getattr(sys, 'frozen', False):
                # Nếu là bản đóng gói (.app / .exe)
                subprocess.Popen([executable] + sys.argv[1:], cwd=APP_DIR)
            else:
                # Nếu chạy bằng python script
                target_script = os.path.join(APP_DIR, "sharetool.py")
                args = [executable, target_script]
                subprocess.Popen(args, cwd=APP_DIR)
            
            # Thoát tiến trình cũ
            os._exit(0)

        if app_instance and hasattr(app_instance, "root") and app_instance.root.winfo_exists():
            app_instance.root.after(100, _restart_app)
        else:
            _restart_app()

    except Exception as e:
        err_msg = f"Không thể cập nhật: {e}"
        _update_status("Cập nhật thất bại", str(e)[:45], mode="error")
        if app_instance and hasattr(app_instance, "root") and app_instance.root.winfo_exists():
            app_instance.root.after(0, lambda: messagebox.showerror("Lỗi Update", err_msg, parent=app_instance.root))
        else:
            messagebox.showerror("Lỗi Update", err_msg)

from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Kiểm tra thư viện Telethon
try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    TelegramClient = None
    SessionPasswordNeededError = Exception

# Nạp biến môi trường (.env)
env_external = os.path.join(APP_DIR, ".env")
env_bundled = os.path.join(BUNDLE_DIR, ".env")
if os.path.exists(env_external):
    load_dotenv(env_external)
elif os.path.exists(env_bundled):
    load_dotenv(env_bundled)

def get_session_path():
    return os.path.join(APP_DIR, "user_telegram")

# ==========================================
# CẤU HÌNH BOT TELEGRAM
# ==========================================
FEEDBACK_BOT_TOKEN = os.environ.get("FEEDBACK_BOT_TOKEN", "9036345671:AAEfxAK2-JuI3mBSQMJourgOfgMORlmXqCs")
FEEDBACK_CHAT_ID = os.environ.get("FEEDBACK_CHAT_ID", "8559042403")

# ==========================================
# QUẢN LÝ TIMER TẬP TRUNG
# ==========================================
class CountdownTimer:
    """Quản lý timer đếm ngược tái sử dụng cho các tác vụ UI"""
    def __init__(self, root):
        self.root = root
        self._after_id = None

    def cancel(self):
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def is_running(self):
        return self._after_id is not None

    def start(self, seconds, on_tick, on_done):
        self.cancel()
        self._step(seconds, on_tick, on_done)

    def _step(self, seconds_left, on_tick, on_done):
        if seconds_left > 0:
            if on_tick:
                on_tick(seconds_left)
            self._after_id = self.root.after(1000, lambda: self._step(seconds_left - 1, on_tick, on_done))
        else:
            self._after_id = None
            if on_done:
                on_done()

# ==========================================
# QUẢN LÝ KẾT NỐI TELEGRAM (PERSISTENT CLIENT)
# ==========================================
class TelegramManager:
    """Quản lý kết nối Telegram tập trung, duy trì kết nối persistent tránh overhead kết nối lại liên tục"""
    def __init__(self):
        self._loop = None
        self._thread = None
        self._client = None
        self._lock = threading.Lock()
        self._ready_event = threading.Event()
        self._start_thread()

    def _start_thread(self):
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="TelegramManagerLoop")
        self._thread.start()
        self._ready_event.wait(timeout=5)

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready_event.set()
        self._loop.run_forever()

    def run_coro(self, coro, timeout=35):
        if not self._loop or not self._loop.is_running():
            self._start_thread()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def get_client(self):
        if TelegramClient is None:
            return None
        api_id_val = os.environ.get("TG_API_ID", 0)
        api_hash_val = os.environ.get("TG_API_HASH", "")
        if not api_id_val or not api_hash_val:
            return None
        try:
            api_id = int(api_id_val)
        except ValueError:
            return None
        session = get_session_path()
        if self._client is None:
            self._client = TelegramClient(session, api_id, api_hash_val, timeout=12)
        if not self._client.is_connected():
            await self._client.connect()
        return self._client

    async def is_authorized(self):
        client = await self.get_client()
        if not client:
            return False
        return await client.is_user_authorized()

    async def disconnect(self):
        if self._client is not None:
            try:
                if self._client.is_connected():
                    await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def disconnect_sync(self):
        """Đóng kết nối đồng bộ để nhường file session cho Login Modal"""
        if self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self.disconnect(), self._loop)
                future.result(timeout=5)
            except Exception:
                pass

    def reset_client(self):
        self.disconnect_sync()

    def shutdown(self):
        self.disconnect_sync()
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

TG_MANAGER = TelegramManager()

TG_GETLINK_BOT_USERNAME = "@loginlinkjm_bot"  # Bot GetLoginLink
RE_NETFLIX_LINK = re.compile(r'(https?://(?:www\.)?netflix\.com/\S+)', flags=re.I)
RE_HTTP_LINK = re.compile(r'(https?://\S+)', flags=re.I)

# ==========================================
# BIÊN DỊCH TRƯỚC REGEX
# ==========================================
RE_EMAIL = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
RE_2FA = re.compile(r'[A-Z2-7]{16,}')
RE_SPLIT_TOKENS = re.compile(r'[\s\t,;]+')
RE_COOKIE_HEADER = re.compile(r'(?:cookies?\s*[:=]\s*)([^\r\n]+)', flags=re.I)
RE_NON_DIGIT = re.compile(r'[^0-9]')
RE_GETCODE_PREFIX = re.compile(r'^/getcode\s*', flags=re.I)
RE_WHITESPACE = re.compile(r'\s+')
RE_TG_CODE = re.compile(r'(?:Code\s*:\s*)?(\d{4,8})', flags=re.I)

# ==========================================
# 1. CẤU HÌNH TEMPLATE
# ==========================================
TEMPLATE_FILE = os.path.join(APP_DIR, "templates.json")

FORMAT_SCHEMAS = [
    {
        "id": "capcut",
        "title": "Format Capcut - Email + Pass",
        "default": "Email: {email}\nPassword: {password}\n\nPls remove the space after @ before logging in po."
    },
    {
        "id": "netflix",
        "title": "Format Netflix - Email + Username",
        "default": "Email: {email}\nPls remove the space after @ before logging in po.\n\nAccount to get code:\nUsername: {username}\nPassword: {password}"
    },
    {
        "id": "chatgpt",
        "title": "Format ChatGPT - Email + Pass + 2FA",
        "default": "Email: {email}\nPassword: {password}\n2FA Secret: {code_2fa}\nGet 2FA code at: https://2fa.live\n\nPls remove the space after @ before logging in po."
    }
]

DEFAULT_TEMPLATES = {cfg["id"]: cfg["default"] for cfg in FORMAT_SCHEMAS}
DEFAULT_TEMPLATES["netflix_default_pass"] = "1234567891011"

_TEMPLATES_CACHE = None

def load_custom_templates():
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return _TEMPLATES_CACHE
    
    target_tpl = TEMPLATE_FILE
    if not os.path.exists(target_tpl):
        bundled_tpl = os.path.join(BUNDLE_DIR, "templates.json")
        if os.path.exists(bundled_tpl):
            target_tpl = bundled_tpl

    if os.path.exists(target_tpl):
        try:
            with open(target_tpl, "r", encoding="utf-8") as f:
                data = json.load(f)
                _TEMPLATES_CACHE = {**DEFAULT_TEMPLATES, **data}
                return _TEMPLATES_CACHE
        except Exception:
            pass
    _TEMPLATES_CACHE = DEFAULT_TEMPLATES.copy()
    return _TEMPLATES_CACHE

def save_custom_templates(data):
    global _TEMPLATES_CACHE
    try:
        with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _TEMPLATES_CACHE = {**DEFAULT_TEMPLATES, **data}
    except Exception:
        pass


# ==========================================
# 2. CÁC HÀM XỬ LÝ DỮ LIỆU
# ==========================================
def find_matching_braces(s, start_idx):
    depth = 0
    for i in range(start_idx, len(s)):
        ch = s[i]
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return i
    return None

def extract_cookie_json(s):
    s = str(s or "")
    for match in re.finditer(r"\{", s):
        start_idx = match.start()
        end_idx = find_matching_braces(s, start_idx)
        if end_idx is None: continue
        candidate = s[start_idx:end_idx + 1].strip()
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and any(k in obj for k in ("cookies", "url", "uri", "origin")):
                return candidate
        except Exception:
            continue
    return None

def extract_header_cookies(s):
    s = str(s or "").strip()
    match = RE_COOKIE_HEADER.search(s)
    if match:
        cookie_part = match.group(1).strip()
    else:
        idx = s.find("NetflixId=")
        if idx != -1: cookie_part = s[idx:].strip()
        else: return None

    if cookie_part.startswith("{") or cookie_part.startswith("["): return None
    if " | " in cookie_part: cookie_part = cookie_part.split(" | ")[0].strip()
    elif "|" in cookie_part: cookie_part = cookie_part.split("|")[0].strip()

    cookie_list = []
    for pair in cookie_part.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair: continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v: continue
        cookie_list.append({
            "domain": ".netflix.com", "hostOnly": False, "httpOnly": k in ("SecureNetflixId", "NetflixId"),
            "name": k, "path": "/", "sameSite": "Lax" if k == "NetflixId" else ("Strict" if k == "SecureNetflixId" else "None"),
            "secure": True, "session": False, "value": v
        })
    if not cookie_list: return None
    return json.dumps({"url": "https://www.netflix.com", "cookies": cookie_list}, ensure_ascii=False)

def parse_input_source(raw_text):
    s = str(raw_text or "").strip()
    if not s: return None, None
    json_str = extract_cookie_json(s)
    if json_str:
        try:
            data = json.loads(json_str)
            cookies = data.get("cookies", []) if isinstance(data, dict) else data
            if isinstance(cookies, list) and len(cookies) > 0: return "JSON", cookies
        except Exception: pass
    header_str = extract_header_cookies(s)
    if header_str:
        try:
            data = json.loads(header_str)
            cookies = data.get("cookies", [])
            if isinstance(cookies, list) and len(cookies) > 0: return "Metadata", cookies
        except Exception: pass
    return None, None

def prepare_cookies_for_playwright(cookies_list):
    allowed_keys = {"name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
    prepared = []
    exp_future = float(time.time() + (365 * 24 * 60 * 60))
    mapping = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None", "unspecified": "None"}
    for raw_cookie in list(cookies_list or []):
        if not isinstance(raw_cookie, dict): continue
        cookie = dict(raw_cookie)
        if not cookie.get("domain"): cookie["domain"] = ".netflix.com"
        if not cookie.get("path"): cookie["path"] = "/"
        cookie.pop("url", None)
        if "expirationDate" in cookie and "expires" not in cookie: cookie["expires"] = cookie.pop("expirationDate")
        if "expires" in cookie: cookie["expires"] = exp_future
        for k_alt in ("same_site", "SameSite"):
            if k_alt in cookie and "sameSite" not in cookie: cookie["sameSite"] = cookie.pop(k_alt)
            else: cookie.pop(k_alt, None)
        if "sameSite" in cookie:
            s_val = str(cookie["sameSite"]).strip().lower()
            if s_val in mapping: cookie["sameSite"] = mapping[s_val]
            else: cookie.pop("sameSite", None)
        if "name" in cookie: cookie["name"] = str(cookie["name"])
        if "value" in cookie: cookie["value"] = str(cookie["value"])
        for key in list(cookie.keys()):
            if key not in allowed_keys: cookie.pop(key, None)
        prepared.append(cookie)
    return prepared

def format_bot_account_text(raw_text: str):
    text = str(raw_text or "").strip()
    if not text or "STATUS =" in text or "NetflixId=" in text: return None
    templates = load_custom_templates()
    email_match = RE_EMAIL.search(text)
    if not email_match: return None
    raw_email = email_match.group(1).strip()
    email_formatted = raw_email.replace("@", "@ ", 1)
    email_prefix = raw_email.split("@")[0]

    if "|" in text:
        lines = [line.strip() for line in text.splitlines() if "|" in line]
        target_line = lines[0] if lines else text
        pipe_parts = [p.strip() for p in target_line.split("|")]
        email_idx = -1
        for i, part in enumerate(pipe_parts):
            if raw_email in part:
                email_idx = i
                break
        if email_idx != -1:
            remaining_parts = pipe_parts[email_idx + 1:]
            if len(remaining_parts) >= 1:
                password = remaining_parts[0].split()[0] if remaining_parts[0] else ""
                is_chatgpt = False
                code_2fa = ""
                if len(remaining_parts) >= 2:
                    candidate_2fa = remaining_parts[1].split()[0] if remaining_parts[1] else ""
                    if RE_2FA.fullmatch(candidate_2fa):
                        is_chatgpt = True
                        code_2fa = candidate_2fa
                if is_chatgpt: return templates.get("chatgpt", "").format(email=email_formatted, password=password, code_2fa=code_2fa)
                else: return templates.get("capcut", "").format(email=email_formatted, password=password)

    tokens = RE_SPLIT_TOKENS.split(text)
    username_found = None
    for token in tokens:
        clean_token = token.strip()
        if clean_token == email_prefix:
            username_found = clean_token
            break
    if username_found:
        pass_val = templates.get("netflix_default_pass", "1234567891011")
        return templates.get("netflix", "").format(email=email_formatted, username=username_found, password=pass_val)
    return None

# ==========================================
# 3. THƯ VIỆN VẼ UI BO GÓC CHUYÊN NGHIỆP
# ==========================================
def get_rounded_rect_coords(x1, y1, x2, y2, radius=10):
    return [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]

def draw_rounded_rect(canvas, x1, y1, x2, y2, radius=10, **kwargs):
    points = get_rounded_rect_coords(x1, y1, x2, y2, radius)
    return canvas.create_polygon(points, smooth=True, **kwargs)

# ==========================================
# 4. MODAL LOGIN TELEGRAM
# ==========================================
class TelegramLoginModal:
    def __init__(self, parent_app):
        TG_MANAGER.disconnect_sync()
        self.app = parent_app
        self.top = tk.Toplevel(self.app.root)
        self.top.title("Đăng nhập Telegram")
        self.width, self.height = 420, 270
        self.top.geometry(f"{self.width}x{self.height}")
        self.top.configure(bg=self.app.BG_WINDOW)
        self.top.resizable(False, False)
        self.top.transient(self.app.root)
        self.top.grab_set()

        self.step = "PHONE"
        self.phone_val = ""
        self.phone_code_hash = None

        self.cv = tk.Canvas(self.top, width=self.width, height=self.height, bg=self.app.BG_WINDOW, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        draw_rounded_rect(self.cv, 20, 20, 400, 250, radius=14, fill=self.app.BG_CARD, outline=self.app.BORDER_CARD, width=1.5)
        self.cv.create_text(210, 48, text="Kết nối tài khoản Telegram", fill=self.app.TEXT_WHITE, font=("Arial", 18, "bold"), justify="center")
        self.desc_text = self.cv.create_text(210, 80, text="Nhập số điện thoại (VD: 0123456789):", fill=self.app.TEXT_MUTED, font=("Arial", 14), justify="center")
        self.input_rect = draw_rounded_rect(self.cv, 50, 100, 370, 145, radius=10, fill=self.app.BG_INPUT, outline=self.app.BORDER_INPUT, width=1.5)
        
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(self.top, textvariable=self.entry_var, bg=self.app.BG_INPUT, fg=self.app.TEXT_WHITE, insertbackground=self.app.TEXT_WHITE, font=("Arial", 15), bd=0, highlightthickness=0, justify="center")
        self.cv.create_window(210, 122, window=self.entry, width=300, height=28)
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self.on_submit())
        self.entry.bind("<FocusIn>", lambda e: self.cv.itemconfig(self.input_rect, outline=self.app.BORDER_ACTIVE))
        self.entry.bind("<FocusOut>", lambda e: self.cv.itemconfig(self.input_rect, outline=self.app.BORDER_INPUT))

        self.err_text = self.cv.create_text(210, 165, text="", fill="#EF4444", font=("Arial", 11), justify="center")
        
        btn_y, btn_h = 182, 44
        self.btn_rect = draw_rounded_rect(self.cv, 110, btn_y, 310, btn_y + btn_h, radius=10, fill="#FFFFFF", outline="")
        self.btn_txt = self.cv.create_text(210, btn_y + btn_h//2, text="Gửi mã", fill="#111827", font=("Arial", 16, "bold"))
        self.btn_hit = self.cv.create_rectangle(110, btn_y, 310, btn_y + btn_h, fill="", outline="")

        for itm in (self.btn_rect, self.btn_txt, self.btn_hit):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self.on_submit())
            self.cv.tag_bind(itm, "<Enter>", lambda e: self.cv.itemconfig(self.btn_rect, fill="#E5E7EB"))
            self.cv.tag_bind(itm, "<Leave>", lambda e: self.cv.itemconfig(self.btn_rect, fill="#FFFFFF"))

        self.top.update_idletasks()
        root_x = self.app.root.winfo_rootx()
        root_y = self.app.root.winfo_rooty()
        root_w = self.app.root.winfo_width()
        root_h = self.app.root.winfo_height()
        pos_x = root_x + (root_w - self.width) // 2
        pos_y = root_y + (root_h - self.height) // 2
        self.top.geometry(f"{self.width}x{self.height}+{pos_x}+{pos_y}")

    def set_ui_state(self, loading, err_text=""):
        self.cv.itemconfig(self.err_text, text=err_text)
        if loading:
            self.entry.config(state="disabled")
            self.cv.itemconfig(self.btn_txt, text="Đang xử lý...")
        else:
            self.entry.config(state="normal")
            if self.step == "PHONE": self.cv.itemconfig(self.btn_txt, text="Gửi mã xác nhận")
            elif self.step == "OTP": self.cv.itemconfig(self.btn_txt, text="Xác nhận mã OTP")
            else: self.cv.itemconfig(self.btn_txt, text="Xác nhận mật khẩu 2FA")
            self.entry.focus_set()

    def on_submit(self):
        val = self.entry_var.get().strip()
        if not val:
            self.cv.itemconfig(self.err_text, text="Vui lòng không để trống!")
            return
        if self.step == "PHONE":
            if val.startswith("0"): val = "+84" + val[1:]
            elif not val.startswith("+"): val = "+" + val
            self.phone_val = val
            self.set_ui_state(True)
            threading.Thread(target=self._send_code_worker, daemon=True).start()
        elif self.step == "OTP":
            self.set_ui_state(True)
            threading.Thread(target=self._verify_otp_worker, args=(val,), daemon=True).start()
        elif self.step == "2FA":
            self.set_ui_state(True)
            threading.Thread(target=self._verify_2fa_worker, args=(val,), daemon=True).start()

    def _send_code_worker(self):
        try:
            api_id = int(os.environ.get("TG_API_ID", 0))
            api_hash = os.environ.get("TG_API_HASH", "")
            session = get_session_path()
            async def _req():
                client = TelegramClient(session, api_id, api_hash)
                await client.connect()
                try:
                    sent = await client.send_code_request(self.phone_val)
                    return sent.phone_code_hash
                finally:
                    await client.disconnect()
            self.phone_code_hash = asyncio.run(_req())
            def _next():
                self.step = "OTP"
                self.entry_var.set("")
                self.cv.itemconfig(self.desc_text, text="Nhập mã OTP gồm 5 chữ số gửi về Telegram:")
                self.set_ui_state(False)
            self.top.after(0, _next)
        except Exception as e:
            self.top.after(0, lambda: self.set_ui_state(False, f"Lỗi SĐT: {str(e)[:45]}"))

    def _verify_otp_worker(self, otp_code):
        try:
            api_id = int(os.environ.get("TG_API_ID", 0))
            api_hash = os.environ.get("TG_API_HASH", "")
            session = get_session_path()
            async def _sign_in():
                client = TelegramClient(session, api_id, api_hash)
                await client.connect()
                try:
                    await client.sign_in(phone=self.phone_val, code=otp_code, phone_code_hash=self.phone_code_hash)
                    return "OK"
                except SessionPasswordNeededError:
                    return "NEED_2FA"
                finally:
                    await client.disconnect()
            res = asyncio.run(_sign_in())
            if res == "NEED_2FA":
                def _ask_2fa():
                    self.step = "2FA"
                    self.entry_var.set("")
                    self.entry.config(show="*")
                    self.cv.itemconfig(self.desc_text, text="Tài khoản có bảo mật 2 lớp. Nhập mật khẩu 2FA:")
                    self.set_ui_state(False)
                self.top.after(0, _ask_2fa)
            else:
                self.top.after(0, self._on_success)
        except Exception as e:
            self.top.after(0, lambda: self.set_ui_state(False, f"Sai mã OTP: {str(e)[:40]}"))

    def _verify_2fa_worker(self, password):
        try:
            api_id = int(os.environ.get("TG_API_ID", 0))
            api_hash = os.environ.get("TG_API_HASH", "")
            session = get_session_path()
            async def _sign_2fa():
                client = TelegramClient(session, api_id, api_hash)
                await client.connect()
                try:
                    await client.sign_in(password=password)
                finally:
                    await client.disconnect()
            asyncio.run(_sign_2fa())
            self.top.after(0, self._on_success)
        except Exception as e:
            self.top.after(0, lambda: self.set_ui_state(False, f"Sai mật khẩu 2FA: {str(e)[:38]}"))

    def _on_success(self):
        TG_MANAGER.reset_client()
        self.app.play_sound()
        self.app.check_telegram_connection()
        self.app.set_banner_status("Đăng nhập thành công!", "Tài khoản Telegram đã sẵn sàng", mode="success")
        self.top.destroy()

class UpdatePromptModal:
    def __init__(self, parent_app, has_update: bool):
        self.app = parent_app
        self.has_update = has_update
        self.top = tk.Toplevel(self.app.root)
        self.top.title("Cập nhật phần mềm")
        
        # Thiết lập kích thước chuẩn xác không bị tràn
        self.width = 440
        self.height = 370 if has_update else 230
        self.top.geometry(f"{self.width}x{self.height}")
        self.top.configure(bg=self.app.BG_WINDOW)
        self.top.resizable(False, False)
        self.top.transient(self.app.root)
        self.top.grab_set()

        self.cv = tk.Canvas(
            self.top, width=self.width, height=self.height, 
            bg=self.app.BG_WINDOW, highlightthickness=0, bd=0
        )
        self.cv.pack(fill="both", expand=True)

        # Viền card ngoài cùng
        draw_rounded_rect(
            self.cv, 16, 16, self.width - 16, self.height - 16, 
            radius=14, fill=self.app.BG_CARD, outline=self.app.BORDER_CARD, width=1.5
        )

        if not self.has_update:
            # ==========================================
            # 1. TRƯỜNG HỢP: ĐÃ LÀ BẢN MỚI NHẤT (CHƯA CÓ UPDATE)
            # ==========================================
            # Badge trạng thái tròn
            self.cv.create_oval(self.width//2 - 24, 34, self.width//2 + 24, 82, fill="#153524", outline="#245C3D", width=1.5)
            self.cv.create_text(self.width//2, 58, text="✓", fill="#22C55E", font=("Arial", 22, "bold"))

            self.cv.create_text(
                self.width//2, 106,
                text="Bạn đang dùng phiên bản mới nhất",
                fill=self.app.TEXT_WHITE, font=("Arial", 15, "bold"), justify="center"
            )
            self.cv.create_text(
                self.width//2, 134,
                text="Hiện chưa có cập nhật mới. Khi có tính năng mới,\nHoàn sẽ gửi thông báo đến bạn ngay nhé!",
                fill=self.app.TEXT_MUTED, font=("Arial", 11), justify="center"
            )

            # Nút OK căn giữa
            btn_w, btn_h, btn_y = 120, 36, 166
            bx1 = (self.width - btn_w) // 2
            bx2 = bx1 + btn_w
            btn_rect = draw_rounded_rect(self.cv, bx1, btn_y, bx2, btn_y + btn_h, radius=8, fill="#FFFFFF", outline="")
            btn_txt = self.cv.create_text(self.width//2, btn_y + btn_h//2, text="Đã hiểu", fill="#111827", font=("Arial", 13, "bold"))
            btn_hit = self.cv.create_rectangle(bx1, btn_y, bx2, btn_y + btn_h, fill="", outline="")

            for itm in (btn_rect, btn_txt, btn_hit):
                self.cv.tag_bind(itm, "<Button-1>", lambda e: self.top.destroy())
                self.cv.tag_bind(itm, "<Enter>", lambda e: self.cv.itemconfig(btn_rect, fill="#E5E7EB"))
                self.cv.tag_bind(itm, "<Leave>", lambda e: self.cv.itemconfig(btn_rect, fill="#FFFFFF"))

        else:
            # ==========================================
            # 2. TRƯỜNG HỢP: ĐÃ CÓ BẢN MỚI (CÓ CHẤM ĐỎ)
            # ==========================================
            # Tag phiên bản nhỏ chuyên nghiệp
            tag_w, tag_h = 70, 22
            tag_x1 = (self.width - tag_w) // 2
            draw_rounded_rect(self.cv, tag_x1, 28, tag_x1 + tag_w, 28 + tag_h, radius=6, fill="#1E293B", outline="#3B82F6", width=1.0)
            self.cv.create_text(self.width//2, 28 + tag_h//2, text="UPDATE", fill="#38BDF8", font=("Arial", 10, "bold"))

            # Tiêu đề
            self.cv.create_text(
                self.width//2, 66,
                text="Đã có phiên bản cập nhật mới!",
                fill=self.app.TEXT_WHITE, font=("Arial", 18, "bold"), justify="center"
            )

            # Box Changelog bo góc
            box_x1, box_y1, box_x2, box_y2 = 36, 88, self.width - 36, 245
            draw_rounded_rect(self.cv, box_x1, box_y1, box_x2, box_y2, radius=10, fill=self.app.BG_INPUT, outline=self.app.BORDER_INPUT, width=1.5)

            # Header bên trong box
            self.cv.create_text(box_x1 + 16, box_y1 + 18, text="Nội dung cập nhật:", fill="#94A3B8", font=("Arial", 12, "bold"), anchor="w")

            # Các dòng tính năng (Dùng ký hiệu dot thẩm mỹ)
            changelog_items = [
                "• Nâng cấp độ mượt khi Get CODE & Login Link",
                "• Tối ưu hệ thống bộ nhớ & chống văng ứng dụng",
                "• Tự động đồng bộ và sửa các lỗi hiển thị UI"
            ]
            line_y = box_y1 + 42
            for item in changelog_items:
                self.cv.create_text(box_x1 + 16, line_y, text=item, fill="#E2E8F0", font=("Arial", 12), anchor="w")
                line_y += 24

            # Câu hỏi xác nhận
            self.cv.create_text(
                self.width//2, 266,
                text="Ứng dụng sẽ tự động tải dữ liệu mới và khởi động lại.",
                fill=self.app.TEXT_MUTED, font=("Arial", 12), justify="center"
            )

            # Nút bấm: Để sau (Secondary) & Cập nhật ngay (Primary Xanh)
            btn_w, btn_h, btn_y = 150, 40, 295
            
            # 1. Nút "Để sau" (Bên trái)
            bx1_left = 48
            bx2_left = bx1_left + btn_w
            btn_no_rect = draw_rounded_rect(self.cv, bx1_left, btn_y, bx2_left, btn_y + btn_h, radius=8, fill=self.app.BG_CARD, outline=self.app.BORDER_CARD, width=1.5)
            btn_no_txt = self.cv.create_text((bx1_left + bx2_left)//2, btn_y + btn_h//2, text="Để sau", fill=self.app.TEXT_MUTED, font=("Arial", 12, "bold"))
            hit_no = self.cv.create_rectangle(bx1_left, btn_y, bx2_left, btn_y + btn_h, fill="", outline="")
            
            for itm in (btn_no_rect, btn_no_txt, hit_no):
                self.cv.tag_bind(itm, "<Button-1>", lambda e: self.top.destroy())
                self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(btn_no_rect, outline=self.app.BORDER_ACTIVE), self.cv.itemconfig(btn_no_txt, fill=self.app.TEXT_WHITE)))
                self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(btn_no_rect, outline=self.app.BORDER_CARD), self.cv.itemconfig(btn_no_txt, fill=self.app.TEXT_MUTED)))

            # 2. Nút "Cập nhật ngay" (Bên phải - Accent Brand Blue)
            bx1_right = self.width - 48 - btn_w
            bx2_right = bx1_right + btn_w
            btn_up_rect = draw_rounded_rect(self.cv, bx1_right, btn_y, bx2_right, btn_y + btn_h, radius=8, fill="#2563EB", outline="")
            btn_up_txt = self.cv.create_text((bx1_right + bx2_right)//2, btn_y + btn_h//2, text="Update now", fill="#FFFFFF", font=("Arial", 14, "bold"))
            hit_up = self.cv.create_rectangle(bx1_right, btn_y, bx2_right, btn_y + btn_h, fill="", outline="")
            
            for itm in (btn_up_rect, btn_up_txt, hit_up):
                self.cv.tag_bind(itm, "<Button-1>", lambda e: self._on_confirm_update())
                self.cv.tag_bind(itm, "<Enter>", lambda e: self.cv.itemconfig(btn_up_rect, fill="#1D4ED8"))
                self.cv.tag_bind(itm, "<Leave>", lambda e: self.cv.itemconfig(btn_up_rect, fill="#2563EB"))

        # Căn giữa màn hình ứng dụng chính
        self.top.update_idletasks()
        rx, ry = self.app.root.winfo_rootx(), self.app.root.winfo_rooty()
        rw, rh = self.app.root.winfo_width(), self.app.root.winfo_height()
        pos_x = rx + (rw - self.width) // 2
        pos_y = ry + (rh - self.height) // 2
        self.top.geometry(f"{self.width}x{self.height}+{pos_x}+{pos_y}")

    def _on_confirm_update(self):
        self.top.destroy()
        self.app.set_banner_status("Đang cập nhật...", "Chuẩn bị tải bản cập nhật mới...", mode="loading")
        self.app.root.update_idletasks()
        threading.Thread(target=apply_full_update, args=(self.app,), daemon=True).start()

# ==========================================
# 5. CLASS CHÍNH CỦA ỨNG DỤNG
# ==========================================
class ModernNetflixApp:
    BG_WINDOW = "#0D1016"
    BG_OUTER_PANEL = "#151922"
    BORDER_OUTER = "#232936"
    BG_CARD = "#11151E"
    BORDER_CARD = "#222734"
    BG_INPUT = "#181D27"
    BORDER_INPUT = "#2E3545"
    BORDER_ACTIVE = "#3B82F6"
    TEXT_WHITE = "#F3F4F6"
    TEXT_MUTED = "#6E788C"
    TEXT_GREEN = "#10B981"
    BTN_BG_INACTIVE = "#242B3A"
    BTN_TXT_INACTIVE = "#8A94A6"
    BTN_BG_ACTIVE = "#1D4ED8"
    BTN_BG_HOVER = "#2563EB"
    BADGE_WHITE = "#F9FAFB"
    BADGE_TEXT = "#111827"

    def __init__(self, root):
        self.sub_mode = "LINK"  # ĐẶT LINK LÀM MẶC ĐỊNH
        self.root = root
        self.root.title("Netflix Vèo Vèo")
        self.root.minsize(880, 457)
        self.root.geometry("880x457")
        self.root.withdraw()
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG_WINDOW)

        self.has_update = False
        threading.Thread(target=self._check_update_background, daemon=True).start()
        self.UI_SCALE = 1.0  
        self.is_muted = False

        load_custom_templates()

        self.cmd_queue = queue.Queue()
        self.ready_session = None
        
        self._cskh_timer = CountdownTimer(self.root)
        self._tv_timer = CountdownTimer(self.root)
        self._getcode_timer = CountdownTimer(self.root)
        
        self._feedback_win = None
        self._template_win = None

        self.show_chrome = False
        self.code_enabled = False
        self.tv_placeholder_active = True
        self.cskh_placeholder_active = True
        self.getcode_placeholder_active = True
        self.show_getcode = False
        
        self.tg_authorized = False
        self.tg_status_text = "Telegram: Đang kiểm tra..."
        self.tg_status_color = self.TEXT_MUTED

        self._build_canvas_ui()
        self.play_startup_sound()
        self.root.after(250, self.check_telegram_connection)
        threading.Thread(target=self._run_async_worker, daemon=True).start()
        
        self.timer_seconds = 10 * 60
        self._timer_after_id = None
        self._timer_after_id = self.root.after(1000, self._tick_spam_timer)

        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def S(self, val): return int(val * getattr(self, 'UI_SCALE', 1.0))
    def F(self, val): return int(val * getattr(self, 'UI_SCALE', 1.0))

    def _check_update_background(self):
        if check_update_available():
            self.has_update = True
            def _show_dot():
                if getattr(self, "menu_is_open", False):
                    self.cv.itemconfig(self.update_dot, state="normal")
            self.root.after(0, _show_dot)

    def _on_click_update(self, event=None):
        UpdatePromptModal(self, self.has_update)

    def _on_app_close(self):
        try: self.cmd_queue.put({"action": "quit"})
        except Exception: pass
        try: TG_MANAGER.shutdown()
        except Exception: pass
        self.root.after(200, self.root.destroy)

    def _clear_getcode_input(self):
        """Xoá nội dung ô nhập Get CODE / LINK và đặt lại placeholder mặc định"""
        try:
            self.getcode_entry.delete(0, "end")
            self.getcode_placeholder_active = True
            placeholder_text = "Nhập email ạ..." if self.sub_mode == "CODE" else "Nhập link/JSON ạ..."
            self.getcode_entry.insert(0, placeholder_text)
            self.getcode_entry.configure(fg=self.TEXT_MUTED)
            self.cv.itemconfig(self.otp_badge_txt, text="______", fill=self.BADGE_TEXT)
        except Exception:
            pass

    def _start_getcode_error_countdown(self, main_err, sub_err, seconds_left=5):
        """Đếm ngược xoá ô Get CODE/LINK khi dán dữ liệu sai hoặc API báo lỗi"""
        def _on_tick(sec):
            self.set_banner_status(main_err, f"{sub_err} (Xóa sau {sec}s)", mode="error")
        def _on_done():
            self._clear_getcode_input()
            self.set_banner_status("Sẵn sàng", "Hãy dán dữ liệu hợp lệ tiếp theo", mode="success")
        self._getcode_timer.start(seconds_left, _on_tick, _on_done)

    def _start_getcode_clear_countdown(self, main_msg, sub_msg, seconds_left=5):
        """Đếm ngược xoá ô Get CODE/LINK sau khi lấy link/code thành công"""
        def _on_tick(sec):
            self.set_banner_status(main_msg, f"{sub_msg} (Xoá sau {sec}s)", mode="success")
        def _on_done():
            self._clear_getcode_input()
            self.set_banner_status("Sẵn sàng", "Hãy dán dữ liệu tiếp theo", mode="success")
        self._getcode_timer.start(seconds_left, _on_tick, _on_done)

    def _toggle_sub_mode(self):
        """Nút chuyển đổi chế độ CODE và LINK"""
        if getattr(self, "_getcode_timer", None) is not None:
            self._getcode_timer.cancel()
            
        self.sub_mode = "LINK" if self.sub_mode == "CODE" else "CODE"
        title_new = "Get CODE" if self.sub_mode == "CODE" else "Get LINK"
        mode_btn_text = "LINK" if self.sub_mode == "LINK" else "CODE"
        
        self.cv.itemconfig(self.getcode_title_label, text=title_new)
        self.cv.itemconfig(self.btn_submode_text, text=mode_btn_text)
        if not getattr(self, "_getcode_running", False):
            self.cv.itemconfig(self.getcode_button_label, text="GET")

        self._clear_getcode_input()
        self.set_banner_status("Đã chuyển chế độ", f"Sẵn sàng lấy {self.sub_mode}", mode="success")

    def _build_canvas_ui(self):
        self.wrapper = tk.Frame(self.root, bg=self.BG_WINDOW)
        self.wrapper.pack(fill="both", expand=True)
        self.cv = tk.Canvas(self.wrapper, width=self.S(880), height=self.S(549), bg=self.BG_WINDOW, highlightthickness=0, bd=0)
        self.cv.place(relx=0.5, rely=0.5, anchor="center")

        self.outer_panel = draw_rounded_rect(self.cv, self.S(14), self.S(14), self.S(866), self.S(535), radius=self.S(24), fill=self.BG_OUTER_PANEL, outline=self.BORDER_OUTER, width=1.5)

        # 1. KHỐI TRÊN TRÁI: Chuẩn hoá (CSKH)
        draw_rounded_rect(self.cv, self.S(36), self.S(36), self.S(306), self.S(260), radius=self.S(14), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        self.cskh_title_text = self.cv.create_text(self.S(52), self.S(66), text="Format DATA", fill=self.TEXT_WHITE, font=("Arial", self.F(16), "bold"), anchor="w")

        # NÚT "Edit"
        btn_set_x, btn_set_w = 246, 44
        self.btn_set_rect = draw_rounded_rect(self.cv, self.S(btn_set_x), self.S(54), self.S(btn_set_x + btn_set_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.2)
        self.btn_set_text = self.cv.create_text(self.S(btn_set_x + btn_set_w // 2), self.S(66), text="Edit", fill=self.TEXT_MUTED, font=("Arial", self.F(12)), anchor="center")
        hit_set = self.cv.create_rectangle(self.S(btn_set_x), self.S(54), self.S(btn_set_x + btn_set_w), self.S(78), fill="", outline="")
        for itm in (self.btn_set_rect, self.btn_set_text, hit_set):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self._open_template_settings())
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_set_rect, outline=self.BORDER_ACTIVE), self.cv.itemconfig(self.btn_set_text, fill=self.TEXT_WHITE)))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_set_rect, outline=self.BORDER_CARD), self.cv.itemconfig(self.btn_set_text, fill=self.TEXT_MUTED)))

        self.cskh_input_box = draw_rounded_rect(self.cv, self.S(52), self.S(92), self.S(290), self.S(242), radius=self.S(10), fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)
        self.cskh_input_text = tk.Text(self.cv, bg=self.BG_INPUT, fg=self.TEXT_MUTED, insertbackground=self.BG_INPUT, font=("Arial", self.F(14)), bd=0, highlightthickness=0, wrap="word")
        self.cskh_input_text.bind("<Button-1>", lambda e: self.cskh_input_text.focus_set())
        self.cskh_input_text.bind("<FocusIn>", self._on_cskh_focus_in)
        self.cskh_input_text.bind("<FocusOut>", self._on_cskh_focus_out)
        self.cskh_input_text.bind("<KeyPress>", self._block_typing_only_paste)
        self.cskh_input_text.bind("<<Paste>>", self._on_cskh_paste)
        self.cskh_input_text.bind("<Command-v>", self._on_cskh_paste)
        self.cskh_input_text.bind("<Control-v>", self._on_cskh_paste)
        self.cv.create_window(self.S(64), self.S(104), window=self.cskh_input_text, width=self.S(214), height=self.S(126), anchor="nw")
        self.cv.tag_bind(self.cskh_input_box, "<Button-1>", lambda e: self.cskh_input_text.focus_set())

        # 2. KHỐI TRÊN PHẢI: Log CODE & Các Icon
        draw_rounded_rect(self.cv, self.S(322), self.S(36), self.S(844), self.S(260), radius=self.S(14), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        self.cv.create_text(self.S(338), self.S(66), text="Log CODE", fill=self.TEXT_WHITE, font=("Arial", self.F(16), "bold"), anchor="w")

        # === BỘ MENU TẮT MỞ KHI CLICK [+] / [-] ===
        btn_tg_x, btn_tg_w = 786, 42
        self.btn_tg_rect = draw_rounded_rect(self.cv, self.S(btn_tg_x), self.S(54), self.S(btn_tg_x + btn_tg_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.2)
        self.btn_tg_text = self.cv.create_text(self.S(btn_tg_x + btn_tg_w // 2), self.S(65), text="+", fill=self.TEXT_MUTED, font=("Arial", self.F(20)), anchor="center")
        hit_tg = self.cv.create_rectangle(self.S(btn_tg_x), self.S(54), self.S(btn_tg_x + btn_tg_w), self.S(78), fill="", outline="")
        
        # BỘ 4 NÚT (Ẩn mặc định)
        btn_snd_w = 56
        btn_snd_x = btn_tg_x - btn_snd_w - 10
        btn_sh_w = 56
        btn_sh_x = btn_snd_x - btn_sh_w - 10
        btn_zm_w = 56
        btn_zm_x = btn_sh_x - btn_zm_w - 10
        btn_fb_w = 78
        btn_fb_x = btn_zm_x - btn_fb_w - 10
        
        # Nút Sound/Mute
        snd_txt = "Mute" if self.is_muted else "Sound"
        snd_col = self.TEXT_MUTED if self.is_muted else "#38BDF8"
        self.btn_snd_rect = draw_rounded_rect(self.cv, self.S(btn_snd_x), self.S(54), self.S(btn_snd_x + btn_snd_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=self.BORDER_CARD if self.is_muted else "#38BDF8", width=1.2, tags=("menu_btns",))
        self.btn_snd_text = self.cv.create_text(self.S(btn_snd_x + btn_snd_w // 2), self.S(66), text=snd_txt, fill=snd_col, font=("Arial", self.F(12)), anchor="center", tags=("menu_btns",))
        hit_snd = self.cv.create_rectangle(self.S(btn_snd_x), self.S(54), self.S(btn_snd_x + btn_snd_w), self.S(78), fill="", outline="", tags=("menu_btns",))
        for itm in (self.btn_snd_rect, self.btn_snd_text, hit_snd):
            self.cv.tag_bind(itm, "<Button-1>", self._toggle_sound)
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_snd_rect, outline="#38BDF8"), self.cv.itemconfig(self.btn_snd_text, fill="#38BDF8" if self.is_muted else self.TEXT_WHITE)))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_snd_rect, outline=self.BORDER_CARD if self.is_muted else "#38BDF8"), self.cv.itemconfig(self.btn_snd_text, fill=self.TEXT_MUTED if self.is_muted else "#38BDF8")))

        # Nút Show
        sh_outline = "#38BDF8" if getattr(self, "show_chrome", False) else self.BORDER_CARD
        sh_color = "#38BDF8" if getattr(self, "show_chrome", False) else self.TEXT_MUTED
        self.btn_show_rect = draw_rounded_rect(self.cv, self.S(btn_sh_x), self.S(54), self.S(btn_sh_x + btn_sh_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=sh_outline, width=1.2, tags=("menu_btns",))
        self.btn_show_text = self.cv.create_text(self.S(btn_sh_x + btn_sh_w // 2), self.S(66), text="Show", fill=sh_color, font=("Arial", self.F(12)), anchor="center", tags=("menu_btns",))
        hit_sh = self.cv.create_rectangle(self.S(btn_sh_x), self.S(54), self.S(btn_sh_x + btn_sh_w), self.S(78), fill="", outline="", tags=("menu_btns",))
        for itm in (self.btn_show_rect, self.btn_show_text, hit_sh):
            self.cv.tag_bind(itm, "<Button-1>", self._toggle_chrome_checkbox)
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_show_rect, outline="#38BDF8"), self.cv.itemconfig(self.btn_show_text, fill="#38BDF8" if self.show_chrome else self.TEXT_WHITE)))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_show_rect, outline="#38BDF8" if self.show_chrome else self.BORDER_CARD), self.cv.itemconfig(self.btn_show_text, fill="#38BDF8" if self.show_chrome else self.TEXT_MUTED)))

        # Nút Update
        btn_up_w = 56
        btn_up_x = btn_sh_x - btn_up_w - 10
        self.btn_update_rect = draw_rounded_rect(self.cv, self.S(btn_up_x), self.S(54), self.S(btn_up_x + btn_up_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.2, tags=("menu_btns",))
        self.btn_update_text = self.cv.create_text(self.S(btn_up_x + btn_up_w // 2), self.S(66), text="Update", fill=self.TEXT_MUTED, font=("Arial", self.F(12)), anchor="center", tags=("menu_btns",))
        hit_update = self.cv.create_rectangle(self.S(btn_up_x), self.S(54), self.S(btn_up_x + btn_up_w), self.S(78), fill="", outline="", tags=("menu_btns",))

        dot_r = self.S(3.5)
        dot_x, dot_y = self.S(btn_up_x + btn_up_w - 3), self.S(58)
        self.update_dot = self.cv.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r, fill="#EF4444", outline="", state="hidden", tags=("menu_btns", "update_badge"))

        for itm in (self.btn_update_rect, self.btn_update_text, hit_update):
            self.cv.tag_bind(itm, "<Button-1>", self._on_click_update)
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_update_rect, outline="#38BDF8"), self.cv.itemconfig(self.btn_update_text, fill=self.TEXT_WHITE)))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_update_rect, outline=self.BORDER_CARD), self.cv.itemconfig(self.btn_update_text, fill=self.TEXT_MUTED)))

        # Nút Feedback
        self.btn_fb_rect = draw_rounded_rect(self.cv, self.S(btn_fb_x), self.S(54), self.S(btn_fb_x + btn_fb_w), self.S(78), radius=self.S(6), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.2, tags=("menu_btns",))
        self.btn_fb_text = self.cv.create_text(self.S(btn_fb_x + btn_fb_w // 2), self.S(66), text="Feedback", fill=self.TEXT_MUTED, font=("Arial", self.F(12)), anchor="center", tags=("menu_btns",))
        hit_fb = self.cv.create_rectangle(self.S(btn_fb_x), self.S(54), self.S(btn_fb_x + btn_fb_w), self.S(78), fill="", outline="", tags=("menu_btns",))
        for itm in (self.btn_fb_rect, self.btn_fb_text, hit_fb):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self.open_feedback_dialog())
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_fb_rect, outline=self.BORDER_ACTIVE), self.cv.itemconfig(self.btn_fb_text, fill=self.TEXT_WHITE)))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_fb_rect, outline=self.BORDER_CARD), self.cv.itemconfig(self.btn_fb_text, fill=self.TEXT_MUTED)))

        # 3. HÀM CLICK MENU TOGGLE
        self.cv.itemconfigure("menu_btns", state="hidden")
        self.menu_is_open = False

        def _toggle_menu(event=None):
            self.menu_is_open = not self.menu_is_open
            if self.menu_is_open:
                self.cv.itemconfigure("menu_btns", state="normal")
                if not getattr(self, "has_update", False):
                    self.cv.itemconfig(self.update_dot, state="hidden")
                self.cv.itemconfig(self.btn_tg_text, text="-", fill="#38BDF8")
                self.cv.itemconfig(self.btn_tg_rect, outline="#38BDF8")
            else:
                self.cv.itemconfigure("menu_btns", state="hidden")
                self.cv.itemconfig(self.btn_tg_text, text="+", fill=self.TEXT_MUTED)
                self.cv.itemconfig(self.btn_tg_rect, outline=self.BORDER_CARD)

        for itm in (self.btn_tg_rect, self.btn_tg_text, hit_tg):
            self.cv.tag_bind(itm, "<Button-1>", _toggle_menu)
            self.cv.tag_bind(itm, "<Enter>", lambda e: self.cv.itemconfig(self.btn_tg_text, fill="#38BDF8" if not self.menu_is_open else self.TEXT_WHITE))
            self.cv.tag_bind(itm, "<Leave>", lambda e: self.cv.itemconfig(self.btn_tg_text, fill="#38BDF8" if self.menu_is_open else self.TEXT_MUTED))

        self.tv_input_box = draw_rounded_rect(self.cv, self.S(338), self.S(92), self.S(576), self.S(242), radius=self.S(10), fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)
        self.tv_input_text = tk.Text(self.cv, bg=self.BG_INPUT, fg=self.TEXT_MUTED, insertbackground=self.BG_INPUT, font=("Arial", self.F(14)), bd=0, highlightthickness=0, wrap="word")
        self.tv_input_text.bind("<Button-1>", lambda e: self.tv_input_text.focus_set())
        self.tv_input_text.bind("<FocusIn>", self._on_tv_focus_in)
        self.tv_input_text.bind("<FocusOut>", self._on_tv_focus_out)
        self.tv_input_text.bind("<KeyPress>", self._block_typing_only_paste)
        self.tv_input_text.bind("<<Paste>>", self._on_tv_paste)
        self.tv_input_text.bind("<Command-v>", self._on_tv_paste)
        self.tv_input_text.bind("<Control-v>", self._on_tv_paste)
        self.cv.create_window(self.S(350), self.S(104), window=self.tv_input_text, width=self.S(214), height=self.S(126), anchor="nw")
        self.cv.tag_bind(self.tv_input_box, "<Button-1>", lambda e: self.tv_input_text.focus_set())

        self.code_box_rect = draw_rounded_rect(self.cv, self.S(592), self.S(92), self.S(828), self.S(158), radius=self.S(10), fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)
        self.code_var = tk.StringVar()
        self.code_entry = tk.Entry(self.cv, textvariable=self.code_var, bg=self.BG_INPUT, fg=self.TEXT_WHITE, disabledbackground=self.BG_INPUT, disabledforeground=self.TEXT_MUTED, insertbackground=self.TEXT_WHITE, font=("Arial", self.F(14)), bd=0, highlightthickness=0, state="disabled")
        self.code_var.set("Nhập code ạ...")
        self.code_entry.bind("<Return>", lambda e: self.submit_tv_code())
        self.code_entry.bind("<KeyPress>", self._handle_code_keypress)
        self.code_entry.bind("<<Paste>>", self._on_code_paste)
        self.code_entry.bind("<Command-v>", self._on_code_paste)
        self.code_entry.bind("<Control-v>", self._on_code_paste)
        self.code_var.trace_add("write", self._validate_code_input)
        self.cv.create_window(self.S(606), self.S(112), window=self.code_entry, width=self.S(208), height=self.S(28), anchor="nw")

        self.submit_btn_rect = draw_rounded_rect(self.cv, self.S(592), self.S(174), self.S(828), self.S(242), radius=self.S(10), fill=self.BTN_BG_INACTIVE, outline="")
        self.submit_btn_text = self.cv.create_text(self.S(710), self.S(208), text="Log in", fill=self.BTN_TXT_INACTIVE, font=("Arial", self.F(14), "bold"))
        submit_hit = self.cv.create_rectangle(self.S(592), self.S(174), self.S(828), self.S(242), fill="", outline="")
        for item in (self.submit_btn_rect, self.submit_btn_text, submit_hit):
            self.cv.tag_bind(item, "<Button-1>", lambda e: self.submit_tv_code())
            self.cv.tag_bind(item, "<Enter>", self._on_submit_hover_in)
            self.cv.tag_bind(item, "<Leave>", self._on_submit_hover_out)

        # 3. KHỐI GIỮA: Get CODE / Get LINK
        self.getcode_card = draw_rounded_rect(self.cv, self.S(36), self.S(278), self.S(844), self.S(420), radius=self.S(14), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        
        self.toggle_icon = self.cv.create_text(self.S(52), self.S(303), text="▶", fill=self.TEXT_WHITE, font=("Arial", self.F(13)), anchor="w")
        title_init = "Get CODE" if self.sub_mode == "CODE" else "Get LINK"
        self.getcode_title_label = self.cv.create_text(self.S(74), self.S(303), text=title_init, fill=self.TEXT_WHITE, font=("Arial", self.F(16), "bold"), anchor="w")

        for item in (self.toggle_icon, self.getcode_title_label):
            self.cv.tag_bind(item, "<Button-1>", self._toggle_getcode)
            self.cv.tag_bind(item, "<Enter>", lambda e: self.cv.itemconfig(self.getcode_title_label, fill="#38BDF8"))
            self.cv.tag_bind(item, "<Leave>", lambda e: self.cv.itemconfig(self.getcode_title_label, fill=self.TEXT_WHITE))

        self.telegram_status = self.cv.create_text(self.S(824), self.S(303), text=self.tg_status_text, fill=self.tg_status_color, font=("Arial", self.F(14), "bold"), anchor="e")
        self.cv.tag_bind(self.telegram_status, "<Button-1>", self._on_telegram_status_click)

        # --- NỘI DUNG BÊN TRONG CỦA THẺ GET CODE / GET LINK (3 Ô HÀNG DƯỚI) ---
        mode_btn_text = "LINK" if self.sub_mode == "LINK" else "CODE"
        self.btn_submode_rect = draw_rounded_rect(self.cv, self.S(52), self.S(344), self.S(172), self.S(404), radius=self.S(10), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5, tags=("getcode_content",))
        self.btn_submode_text = self.cv.create_text(self.S(112), self.S(374), text=mode_btn_text, fill=self.TEXT_WHITE, font=("Arial", self.F(14), "bold"), anchor="center", tags=("getcode_content",))
        hit_submode_btn = self.cv.create_rectangle(self.S(52), self.S(344), self.S(172), self.S(404), fill="", outline="", tags=("getcode_content",))
        for itm in (self.btn_submode_rect, self.btn_submode_text, hit_submode_btn):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self._toggle_sub_mode())
            self.cv.tag_bind(itm, "<Enter>", lambda e: (self.cv.itemconfig(self.btn_submode_rect, outline=self.BORDER_ACTIVE), self.cv.itemconfig(self.btn_submode_text, fill="#38BDF8")))
            self.cv.tag_bind(itm, "<Leave>", lambda e: (self.cv.itemconfig(self.btn_submode_rect, outline=self.BORDER_CARD), self.cv.itemconfig(self.btn_submode_text, fill=self.TEXT_WHITE)))

        self.getcode_input_rect = draw_rounded_rect(self.cv, self.S(184), self.S(344), self.S(684), self.S(404), radius=self.S(10), fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5, tags=("getcode_content",))
        self.getcode_email = tk.StringVar()
        self.getcode_entry = tk.Entry(self.cv, textvariable=self.getcode_email, bg=self.BG_INPUT, fg=self.TEXT_MUTED, insertbackground=self.TEXT_WHITE, font=("Arial", self.F(14)), bd=0, highlightthickness=0)
        
        placeholder_text = "Nhập email ạ..." if self.sub_mode == "CODE" else "Nhập link/JSON ạ..."
        self.getcode_entry.insert(0, placeholder_text)
        self.getcode_placeholder_active = True
        
        self.getcode_entry.bind("<FocusIn>", self._getcode_focus_in)
        self.getcode_entry.bind("<FocusOut>", self._getcode_focus_out)
        self.getcode_entry.bind("<KeyPress>", self._getcode_keypress)
        self.getcode_entry.bind("<<Paste>>", self._getcode_paste)
        self.getcode_entry.bind("<Command-v>", self._getcode_paste)
        self.getcode_entry.bind("<Control-v>", self._getcode_paste)
        self.getcode_entry_win = self.cv.create_window(self.S(198), self.S(374), window=self.getcode_entry, width=self.S(472), height=self.S(28), anchor="w", tags=("getcode_content",))
        self.cv.tag_bind(self.getcode_input_rect, "<Button-1>", lambda e: self.getcode_entry.focus_set())

        self.getcode_button_rect = draw_rounded_rect(self.cv, self.S(696), self.S(344), self.S(828), self.S(404), radius=self.S(10), fill=self.BTN_BG_INACTIVE, outline="", tags=("getcode_content",))
        self.getcode_button_label = self.cv.create_text(self.S(762), self.S(374), text="GET", fill=self.TEXT_WHITE, font=("Arial", self.F(14), "bold"), anchor="center", tags=("getcode_content",))
        hit_getcode_btn = self.cv.create_rectangle(self.S(696), self.S(344), self.S(828), self.S(404), fill="", outline="", tags=("getcode_content",))
        for itm in (self.getcode_button_rect, self.getcode_button_label, hit_getcode_btn):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self._getcode_submit())
            self.cv.tag_bind(itm, "<Enter>", lambda e: self.cv.itemconfig(self.getcode_button_rect, fill=self.BTN_BG_HOVER) if not getattr(self, "_getcode_running", False) else None)
            self.cv.tag_bind(itm, "<Leave>", lambda e: self.cv.itemconfig(self.getcode_button_rect, fill=self.BTN_BG_INACTIVE) if not getattr(self, "_getcode_running", False) else None)
            
        self.otp_badge_txt = self.cv.create_text(self.S(800), self.S(374), text="______", fill=self.BG_INPUT, font=("Arial", self.F(1), "bold"), anchor="center", state="hidden")

        # 4. FOOTER: STATUS BAR & SPAM TIMER
        self.status_bar_rect = draw_rounded_rect(self.cv, self.S(36), self.S(438), self.S(740), self.S(510), radius=self.S(12), fill="#153524", outline="#245C3D", width=1.5)
        self.status_icon_bg = self.cv.create_oval(self.S(52), self.S(456), self.S(88), self.S(492), fill="#22C55E", outline="")
        self.status_icon_txt = self.cv.create_text(self.S(70), self.S(474), text="✓", fill="#FFFFFF", font=("Arial", self.F(14), "bold"))
        
        self.status_left_txt = self.cv.create_text(self.S(104), self.S(474), text="Sẵn sàng", fill="#FFFFFF", font=("Arial", self.F(14), "bold"), anchor="w")
        self.status_right_txt = self.cv.create_text(self.S(726), self.S(474), text="Xin chào tới với Netflix Vèo Vèo!", fill="#E5E7EB", font=("Arial", self.F(14)), anchor="e")

        self.timer_box_rect = draw_rounded_rect(self.cv, self.S(750), self.S(438), self.S(844), self.S(510), radius=self.S(12), fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        self.timer_title_txt = self.cv.create_text(self.S(797), self.S(458), text="SPAM", fill=self.TEXT_MUTED, font=("Arial", self.F(14)))
        self.timer_box_txt = self.cv.create_text(self.S(797), self.S(482), text="10:00", fill=self.TEXT_WHITE, font=("Arial", self.F(14), "bold"))
        timer_hit = self.cv.create_rectangle(self.S(750), self.S(438), self.S(844), self.S(510), fill="", outline="")
        for itm in (self.timer_box_rect, self.timer_title_txt, self.timer_box_txt, timer_hit):
            self.cv.tag_bind(itm, "<Button-1>", lambda e: self._reset_spam_timer())

        self.cskh_input_text.delete("1.0", "end")
        self.cskh_input_text.insert("1.0", "Nhập thông tin ạ...")
        self.cskh_input_text.config(fg=self.TEXT_MUTED)
        self.cskh_placeholder_active = True

        self.tv_input_text.delete("1.0", "end")
        self.tv_input_text.insert("1.0", "Nhập link ạ...")
        self.tv_input_text.config(fg=self.TEXT_MUTED)
        self.tv_placeholder_active = True

        self._apply_getcode_state()
        
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.S(880)
        h = self.S(549) if self.show_getcode else self.S(457)
        self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        self.root.deiconify()
        self.root.lift()

    def _toggle_sound(self, event=None):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.cv.itemconfig(self.btn_snd_text, text="Mute", fill=self.TEXT_MUTED)
            self.cv.itemconfig(self.btn_snd_rect, outline=self.BORDER_CARD)
            self.set_banner_status("Đã tắt tiếng", "Chế độ yên lặng đã được bật", mode="loading")
        else:
            self.cv.itemconfig(self.btn_snd_text, text="Sound", fill="#38BDF8")
            self.cv.itemconfig(self.btn_snd_rect, outline="#38BDF8")
            self.set_banner_status("Đã bật tiếng", "Hệ thống âm thanh sẵn sàng", mode="success")
            self.play_sound()

    def _toggle_getcode(self, event=None):
        self.show_getcode = not self.show_getcode
        self._apply_getcode_state()

    def _apply_getcode_state(self):
        offset = self.S(92)
        w = self.S(880)
        if self.show_getcode:
            self.cv.itemconfig(self.toggle_icon, text="▼")
            self.cv.itemconfigure("getcode_content", state="normal")
            if hasattr(self, 'getcode_entry_win'):
                self.cv.itemconfigure(self.getcode_entry_win, state="normal")
            self.cv.coords(self.getcode_card, *get_rounded_rect_coords(self.S(36), self.S(278), self.S(844), self.S(420), self.S(14)))
            self.cv.coords(self.outer_panel, *get_rounded_rect_coords(self.S(14), self.S(14), self.S(866), self.S(535), self.S(24)))
            self.cv.coords(self.status_bar_rect, *get_rounded_rect_coords(self.S(36), self.S(438), self.S(740), self.S(510), self.S(12)))
            self.cv.coords(self.status_icon_bg, self.S(52), self.S(456), self.S(88), self.S(492))
            self.cv.coords(self.status_icon_txt, self.S(70), self.S(474))
            self.cv.coords(self.status_left_txt, self.S(104), self.S(474))
            self.cv.coords(self.status_right_txt, self.S(726), self.S(474))
            self.cv.coords(self.timer_box_rect, *get_rounded_rect_coords(self.S(750), self.S(438), self.S(844), self.S(510), self.S(12)))
            self.cv.coords(self.timer_title_txt, self.S(797), self.S(458))
            self.cv.coords(self.timer_box_txt, self.S(797), self.S(482))
            h = self.S(549)
        else:
            self.cv.itemconfig(self.toggle_icon, text="▶")
            self.cv.itemconfigure("getcode_content", state="hidden")
            if hasattr(self, 'getcode_entry_win'):
                self.cv.itemconfigure(self.getcode_entry_win, state="hidden")
            self.cv.coords(self.getcode_card, *get_rounded_rect_coords(self.S(36), self.S(278), self.S(844), self.S(328), self.S(14)))
            self.cv.coords(self.outer_panel, *get_rounded_rect_coords(self.S(14), self.S(14), self.S(866), self.S(443), self.S(24)))
            self.cv.coords(self.status_bar_rect, *get_rounded_rect_coords(self.S(36), self.S(438) - offset, self.S(740), self.S(510) - offset, self.S(12)))
            self.cv.coords(self.status_icon_bg, self.S(52), self.S(456) - offset, self.S(88), self.S(492) - offset)
            self.cv.coords(self.status_icon_txt, self.S(70), self.S(474) - offset)
            self.cv.coords(self.status_left_txt, self.S(104), self.S(474) - offset)
            self.cv.coords(self.status_right_txt, self.S(726), self.S(474) - offset)
            self.cv.coords(self.timer_box_rect, *get_rounded_rect_coords(self.S(750), self.S(438) - offset, self.S(844), self.S(510) - offset, self.S(12)))
            self.cv.coords(self.timer_title_txt, self.S(797), self.S(458) - offset)
            self.cv.coords(self.timer_box_txt, self.S(797), self.S(482) - offset)
            h = self.S(457)
        self.cv.config(height=h, width=w)
        self.root.minsize(w, h)
        self.root.geometry(f"{w}x{h}")

    # ==========================================
    # GÓP Ý
    # ==========================================
    def open_feedback_dialog(self):
        if getattr(self, "_feedback_win", None) is not None and self._feedback_win.winfo_exists():
            self._feedback_win.lift()
            self._feedback_win.focus_force()
            return

        top = tk.Toplevel(self.root)
        self._feedback_win = top
        top.title("Góp ý / Báo lỗi")
        width, height = 420, 360
        top.configure(bg=self.BG_WINDOW)
        top.resizable(False, False)
        top.withdraw()

        cv = tk.Canvas(top, width=width, height=height, bg=self.BG_WINDOW, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        draw_rounded_rect(cv, 20, 16, 400, 344, radius=14, fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        cv.create_text(210, 42, text="Góp ý & Báo lỗi", fill=self.TEXT_WHITE, font=("Arial", 18, "bold"), justify="center")

        cv.create_text(50, 68, text="Tên của bạn:", fill=self.TEXT_MUTED, font=("Arial", 12), anchor="w")
        input_name_rect = draw_rounded_rect(cv, 50, 84, 370, 124, radius=10, fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)
        name_var = tk.StringVar()
        entry_name = tk.Entry(top, textvariable=name_var, bg=self.BG_INPUT, fg=self.TEXT_WHITE, insertbackground=self.TEXT_WHITE, font=("Arial", 13), bd=0, highlightthickness=0)
        cv.create_window(62, 104, window=entry_name, width=296, height=26, anchor="w")
        entry_name.bind("<FocusIn>", lambda e: cv.itemconfig(input_name_rect, outline=self.BORDER_ACTIVE))
        entry_name.bind("<FocusOut>", lambda e: cv.itemconfig(input_name_rect, outline=self.BORDER_INPUT))

        cv.create_text(50, 140, text="Nội dung chi tiết:", fill=self.TEXT_MUTED, font=("Arial", 12), anchor="w")
        input_content_rect = draw_rounded_rect(cv, 50, 156, 370, 246, radius=10, fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)
        txt_content = tk.Text(top, bg=self.BG_INPUT, fg=self.TEXT_WHITE, insertbackground=self.TEXT_WHITE, font=("Arial", 12), bd=0, highlightthickness=0, wrap="word")
        cv.create_window(62, 164, window=txt_content, width=296, height=72, anchor="nw")
        txt_content.bind("<FocusIn>", lambda e: cv.itemconfig(input_content_rect, outline=self.BORDER_ACTIVE))
        txt_content.bind("<FocusOut>", lambda e: cv.itemconfig(input_content_rect, outline=self.BORDER_INPUT))

        err_text = cv.create_text(210, 260, text="", fill="#EF4444", font=("Arial", 11), justify="center")
        
        btn_y, btn_h = 280, 44
        btn_rect = draw_rounded_rect(cv, 110, btn_y, 310, btn_y + btn_h, radius=10, fill="#FFFFFF", outline="")
        btn_txt = cv.create_text(210, btn_y + btn_h // 2, text="Gửi góp ý", fill="#111827", font=("Arial", 15, "bold"))
        btn_hit = cv.create_rectangle(110, btn_y, 310, btn_y + btn_h, fill="", outline="")

        def on_submit():
            sender, content = name_var.get().strip(), txt_content.get("1.0", "end").strip()
            if not sender:
                cv.itemconfig(err_text, text="Vui lòng nhập tên của bạn!", fill="#EF4444")
                entry_name.focus_set()
                return
            if not content:
                cv.itemconfig(err_text, text="Vui lòng nhập nội dung góp ý!", fill="#EF4444")
                txt_content.focus_set()
                return
            cv.itemconfig(err_text, text="Đang gửi phản hồi...", fill="#38BDF8")
            cv.itemconfig(btn_txt, text="Đang gửi...")
            entry_name.config(state="disabled")
            txt_content.config(state="disabled")
            self._send_feedback_telegram(sender, content, top, cv, err_text, btn_txt, entry_name, txt_content)

        for itm in (btn_rect, btn_txt, btn_hit):
            cv.tag_bind(itm, "<Button-1>", lambda e: on_submit())
            cv.tag_bind(itm, "<Enter>", lambda e: cv.itemconfig(btn_rect, fill="#E5E7EB"))
            cv.tag_bind(itm, "<Leave>", lambda e: cv.itemconfig(btn_rect, fill="#FFFFFF"))

        top.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        pos_x = root_x + (root_w - width) // 2
        pos_y = root_y + (root_h - height) // 2
        
        top.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        top.deiconify()
        top.lift()
        top.grab_set()
        top.after(80, lambda: (top.focus_force(), entry_name.focus_set()))

    def show_success_modal(self, sender):
        modal = tk.Toplevel(self.root)
        modal.title("Thành công")
        w, h = 340, 210
        modal.configure(bg=self.BG_WINDOW)
        modal.resizable(False, False)
        modal.withdraw()

        cv = tk.Canvas(modal, width=w, height=h, bg=self.BG_WINDOW, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)
        draw_rounded_rect(cv, 15, 15, w - 15, h - 15, radius=14, fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)

        cv.create_oval(w//2 - 24, 35, w//2 + 24, 83, fill="#153524", outline="#245C3D", width=1.5)
        cv.create_text(w//2, 59, text="✓", fill="#22C55E", font=("Arial", 22, "bold"))
        cv.create_text(w // 2, 115, text=f"Cảm ơn {sender}!", fill=self.TEXT_WHITE, font=("Arial", 14, "bold"), justify="center")
        cv.create_text(w // 2, 140, text="Góp ý của bạn đã được gửi thành công.", fill=self.TEXT_MUTED, font=("Arial", 11), justify="center")

        btn_y, btn_h, btn_w = 160, 34, 100
        bx1 = (w - btn_w) // 2
        bx2 = bx1 + btn_w
        btn_rect = draw_rounded_rect(cv, bx1, btn_y, bx2, btn_y + btn_h, radius=8, fill="#FFFFFF", outline="")
        btn_txt = cv.create_text(w // 2, btn_y + btn_h // 2, text="OK", fill="#111827", font=("Arial", 13, "bold"))
        btn_hit = cv.create_rectangle(bx1, btn_y, bx2, btn_y + btn_h, fill="", outline="")

        for itm in (btn_rect, btn_txt, btn_hit):
            cv.tag_bind(itm, "<Button-1>", lambda e: modal.destroy())
            cv.tag_bind(itm, "<Enter>", lambda e: cv.itemconfig(btn_rect, fill="#E5E7EB"))
            cv.tag_bind(itm, "<Leave>", lambda e: cv.itemconfig(btn_rect, fill="#FFFFFF"))

        modal.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        pos_x = root_x + (root_w - w) // 2
        pos_y = root_y + (root_h - h) // 2
        modal.geometry(f"{w}x{h}+{pos_x}+{pos_y}")
        modal.deiconify()
        modal.lift()
        modal.grab_set()

    def _send_feedback_telegram(self, sender, content, window, cv, err_text, btn_txt, entry_name, txt_content):
        def _send():
            os_info = f"{platform.system()} {platform.release()}"
            machine_name = platform.node()
            text_message = f"📬 <b>FEEDBACK MỚI TỪ NETFIX VÈO VÈO</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Người gửi:</b> {sender}\n💻 <b>Thiết bị:</b> {machine_name} ({os_info})\n💬 <b>Nội dung:</b>\n{content}\n━━━━━━━━━━━━━━━━━━"
            url = f"https://api.telegram.org/bot{FEEDBACK_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": FEEDBACK_CHAT_ID, "text": text_message, "parse_mode": "HTML"}
            try:
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=8, context=SSL_CONTEXT) as response:
                    if response.status == 200:
                        window.after(0, window.destroy)
                        window.after(0, lambda: self.show_success_modal(sender))
            except Exception:
                def _recover():
                    cv.itemconfig(err_text, text="Lỗi kết nối hoặc sai Chat ID!", fill="#EF4444")
                    cv.itemconfig(btn_txt, text="Gửi góp ý")
                    entry_name.config(state="normal")
                    txt_content.config(state="normal")
                window.after(0, _recover)
        threading.Thread(target=_send, daemon=True).start()

    def _reset_spam_timer(self):
        if self._timer_after_id is not None:
            try: self.root.after_cancel(self._timer_after_id)
            except Exception: pass
            self._timer_after_id = None
        self.timer_seconds = 10 * 60
        mins, secs = divmod(self.timer_seconds, 60)
        self.cv.itemconfig(self.timer_box_txt, text=f"{mins:02d}:{secs:02d}", fill=self.TEXT_WHITE, font=("Arial", self.F(14), "bold"))
        self.cv.itemconfig(self.timer_title_txt, text="SPAM", fill=self.TEXT_MUTED, font=("Arial", self.F(14)))
        self.cv.itemconfig(self.timer_box_rect, outline=self.BORDER_CARD)
        self.set_banner_status("Sẵn sàng", "Đã khởi động lại Thời gian Spam (10p)", mode="success")
        self._timer_after_id = self.root.after(1000, self._tick_spam_timer)

    def _tick_spam_timer(self):
        self._timer_after_id = None
        self.timer_seconds -= 1
        if self.timer_seconds > 0:
            mins, secs = divmod(self.timer_seconds, 60)
            self.cv.itemconfig(self.timer_box_txt, text=f"{mins:02d}:{secs:02d}")
            self._timer_after_id = self.root.after(1000, self._tick_spam_timer)
        else:
            self.play_sound()
            self.set_banner_status("SPAM", "Hoàn nhắc bạn Spam nha :))", mode="loading")
            self.cv.itemconfig(self.timer_box_txt, text="↻", fill="#38BDF8", font=("Arial", self.F(20), "bold"))
            self.cv.itemconfig(self.timer_title_txt, text="Click Reset", fill="#38BDF8")
            self.cv.itemconfig(self.timer_box_rect, outline="#38BDF8")

    def _open_template_settings(self):
        if getattr(self, "_template_win", None) is not None and self._template_win.winfo_exists():
            self._template_win.lift()
            self._template_win.focus_force()
            return

        templates = load_custom_templates()
        tab_schemas = [
            {"id": "capcut", "tab_title": "Capcut", "right_tag": "EMAIL + PASS", "default": templates.get("capcut", DEFAULT_TEMPLATES["capcut"])},
            {"id": "netflix", "tab_title": "Netflix", "right_tag": "EMAIL + USERNAME", "default": templates.get("netflix", DEFAULT_TEMPLATES["netflix"])},
            {"id": "chatgpt", "tab_title": "ChatGPT", "right_tag": "EMAIL + PASS + CODE", "default": templates.get("chatgpt", DEFAULT_TEMPLATES["chatgpt"])}
        ]

        top = tk.Toplevel(self.root)
        self._template_win = top
        top.title("Format DATA")
        win_w, win_h = 460, 420
        top.geometry(f"{win_w}x{win_h}")
        top.resizable(False, False)
        top.configure(bg=self.BG_WINDOW)
        top.withdraw()

        pcv = tk.Canvas(top, width=win_w, height=win_h, bg=self.BG_WINDOW, highlightthickness=0, bd=0)
        pcv.pack(fill="both", expand=True)

        current_tab = ["capcut"]
        tab_rects, tab_texts = {}, {}
        text_widgets = {}
        tag_labels = {}

        btn_w, btn_h, gap = 120, 32, 10
        start_x = 35
        for idx, item in enumerate(tab_schemas):
            fid = item["id"]
            bx1 = start_x + idx * (btn_w + gap)
            bx2 = bx1 + btn_w
            rect = draw_rounded_rect(pcv, bx1, 20, bx2, 20 + btn_h, radius=8, fill=self.BTN_BG_INACTIVE, outline="")
            txt = pcv.create_text((bx1 + bx2) // 2, 20 + btn_h // 2, text=item["tab_title"], fill=self.TEXT_MUTED, font=("Arial", 12, "bold"))
            hit = pcv.create_rectangle(bx1, 20, bx2, 20 + btn_h, fill="", outline="")
            tab_rects[fid] = rect
            tab_texts[fid] = txt

            def _make_click(tab_id=fid):
                return lambda e: switch_tab(tab_id)

            for itm in (rect, txt, hit):
                pcv.tag_bind(itm, "<Button-1>", _make_click(fid))

        card_top, card_bottom = 66, 340
        draw_rounded_rect(pcv, 24, card_top, 436, card_bottom, radius=12, fill=self.BG_CARD, outline=self.BORDER_CARD, width=1.5)
        
        info_tag_txt = pcv.create_text(418, card_top + 18, text="", fill="#6E788C", font=("Arial", 10, "bold"), anchor="e")
        input_box_rect = draw_rounded_rect(pcv, 38, card_top + 34, 422, card_bottom - 16, radius=10, fill=self.BG_INPUT, outline=self.BORDER_INPUT, width=1.5)

        for item in tab_schemas:
            fid = item["id"]
            txt = tk.Text(pcv, bg=self.BG_INPUT, fg=self.TEXT_WHITE, insertbackground=self.TEXT_WHITE, font=("Arial", 12), bd=0, highlightthickness=0, wrap="word")
            txt.insert("1.0", item["default"])
            txt.bind("<FocusIn>", lambda e, r=input_box_rect: pcv.itemconfig(r, outline=self.BORDER_ACTIVE))
            txt.bind("<FocusOut>", lambda e, r=input_box_rect: pcv.itemconfig(r, outline=self.BORDER_INPUT))
            text_widgets[fid] = txt
            tag_labels[fid] = item["right_tag"]

        current_win_item = [None]

        def switch_tab(target_id):
            current_tab[0] = target_id
            for fid in tab_rects:
                if fid == target_id:
                    pcv.itemconfig(tab_rects[fid], fill=self.BTN_BG_ACTIVE)
                    pcv.itemconfig(tab_texts[fid], fill="#FFFFFF")
                else:
                    pcv.itemconfig(tab_rects[fid], fill=self.BTN_BG_INACTIVE)
                    pcv.itemconfig(tab_texts[fid], fill=self.TEXT_MUTED)

            pcv.itemconfig(info_tag_txt, text=tag_labels[target_id])

            if current_win_item[0] is not None:
                pcv.delete(current_win_item[0])
            
            active_text_widget = text_widgets[target_id]
            current_win_item[0] = pcv.create_window(46, card_top + 42, window=active_text_widget, width=366, height=card_bottom - card_top - 66, anchor="nw")
            active_text_widget.focus_set()

        def _on_apply():
            new_data = {fid: text_widgets[fid].get("1.0", "end").strip() for fid in text_widgets}
            save_custom_templates(new_data)
            self.set_banner_status("Đã lưu định dạng", "Cấu hình Format DATA mới đã có hiệu lực", mode="success")
            top.destroy()

        btn_y, btn_w, btn_h = 356, 160, 42
        btn_x1 = (win_w - btn_w) // 2
        btn_x2 = btn_x1 + btn_w
        btn_rect = draw_rounded_rect(pcv, btn_x1, btn_y, btn_x2, btn_y + btn_h, radius=10, fill="#FFFFFF", outline="")
        btn_txt = pcv.create_text(win_w // 2, btn_y + btn_h // 2, text="Apply", fill="#111827", font=("Arial", 14, "bold"))
        btn_hit = pcv.create_rectangle(btn_x1, btn_y, btn_x2, btn_y + btn_h, fill="", outline="")
        for itm in (btn_rect, btn_txt, btn_hit):
            pcv.tag_bind(itm, "<Button-1>", lambda e: _on_apply())
            pcv.tag_bind(itm, "<Enter>", lambda e: pcv.itemconfig(btn_rect, fill="#E5E7EB"))
            pcv.tag_bind(itm, "<Leave>", lambda e: pcv.itemconfig(btn_rect, fill="#FFFFFF"))

        switch_tab("capcut")

        top.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        pos_x = root_x + (root_w - win_w) // 2
        pos_y = root_y + (root_h - win_h) // 2
        
        top.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        top.deiconify()
        top.lift()
        top.grab_set()

    def _on_telegram_status_click(self, event=None):
        if not self.tg_authorized: TelegramLoginModal(self)
        else: self.check_telegram_connection()

    def _getcode_focus_in(self, event=None):
        self.cv.itemconfig(self.getcode_input_rect, outline=self.BORDER_ACTIVE)
        if self.getcode_placeholder_active:
            self.getcode_entry.delete(0, "end")
            self.getcode_entry.configure(fg=self.TEXT_WHITE)
            self.getcode_placeholder_active = False

    def _getcode_focus_out(self, event=None):
        self.cv.itemconfig(self.getcode_input_rect, outline=self.BORDER_INPUT)
        if not self.getcode_email.get().strip():
            self.getcode_placeholder_active = True
            self.getcode_entry.delete(0, "end")
            placeholder_text = "Nhập email ạ..." if self.sub_mode == "CODE" else "Nhập link/JSON ạ..."
            self.getcode_entry.insert(0, placeholder_text)
            self.getcode_entry.configure(fg=self.TEXT_MUTED)

    def _getcode_keypress(self, event):
        if event.keysym in ("Return", "KP_Enter"):
            self._getcode_submit()
            return "break"
        if event.keysym.lower() == "v" and (event.state & 0xC):
            self._getcode_paste()
            return "break"
        if event.keysym in ("Left", "Right", "Home", "End", "Tab", "ISO_Left_Tab"): return None
        return "break"

    def _getcode_paste(self, event=None):
        try: raw_pasted = self.root.clipboard_get()
        except tk.TclError: raw_pasted = ""
        
        if self.sub_mode == "CODE":
            email_match = RE_EMAIL.search(raw_pasted)
            if email_match: clean_val = email_match.group(1).strip()
            else: clean_val = RE_WHITESPACE.sub("", RE_GETCODE_PREFIX.sub("", raw_pasted.strip()))
        else:
            clean_val = raw_pasted.strip()
            
        self.getcode_entry.delete(0, "end")
        self.getcode_entry.insert(0, clean_val)
        self.getcode_entry.configure(fg=self.TEXT_WHITE)
        self.getcode_placeholder_active = False
        if clean_val: self.root.after(80, self._getcode_submit)
        return "break"

    def _getcode_submit(self, event=None):
        if getattr(self, "_getcode_running", False): return "break"
        if not self.tg_authorized:
            self.set_banner_status("Chưa kết nối Telegram", "Hãy đăng nhập Telegram ở cửa sổ vừa bật", mode="error")
            TelegramLoginModal(self)
            return "break"
            
        raw_val = self.getcode_email.get().strip()
        if self.getcode_placeholder_active or raw_val in ("Nhập email ạ...", "Nhập link/JSON ạ..."):
            self._start_getcode_error_countdown("Dữ liệu trống", "Vui lòng dán dữ liệu vào ô nhập", 5)
            return "break"

        if self.sub_mode == "CODE":
            email_match = RE_EMAIL.search(raw_val)
            email = email_match.group(1).strip() if email_match else ""
            self.getcode_entry.delete(0, "end")
            self.getcode_entry.insert(0, email)
            if not email:
                self.cv.itemconfig(self.otp_badge_txt, text="ERR", fill="#EF4444")
                self._start_getcode_error_countdown("Email không hợp lệ", "Vui lòng kiểm tra lại email", 5)
                return "break"
                
            self._getcode_running = True
            self.cv.itemconfig(self.getcode_button_label, text="...", fill="#FFFFFF")
            self.cv.itemconfig(self.getcode_button_rect, fill="#D97706")
            self.set_banner_status("Đang gửi lệnh Telegram", f"/getcode {email}", mode="loading")
            threading.Thread(target=self._fetch_code_from_bot_thread, args=(email,), daemon=True).start()
            return "break"

        else:
            is_link = raw_val.startswith("http://") or raw_val.startswith("https://")
            is_json = raw_val.startswith("{") or raw_val.startswith("[")
            
            if not is_link and not is_json:
                self.cv.itemconfig(self.otp_badge_txt, text="ERR", fill="#EF4444")
                if "@" in raw_val:
                    self._start_getcode_error_countdown("Sai chế độ!", "Đang dán Email. Hãy đổi sang nút 'CODE'", 5)
                else:
                    self._start_getcode_error_countdown("Dữ liệu không hợp lệ", "Chỉ nhận link URL hoặc JSON!", 5)
                return "break"

            if "netflixid=" in raw_val.lower() and not is_json:
                self.cv.itemconfig(self.otp_badge_txt, text="ERR", fill="#EF4444")
                self._start_getcode_error_countdown("Cảnh báo Metadata", "Vui lòng copy link JSON", 5)
                return "break"

            self._getcode_running = True
            self.cv.itemconfig(self.getcode_button_label, text="...", fill="#FFFFFF")
            self.cv.itemconfig(self.getcode_button_rect, fill="#D97706")
            self.set_banner_status("Đang kết nối bot GetLoginLink", "Gửi lệnh tạo link đăng nhập...", mode="loading")
            threading.Thread(target=self._fetch_link_from_bot_thread, args=(raw_val,), daemon=True).start()
            return "break"

    def _fetch_code_from_bot_thread(self, email: str):
        try:
            bot_target = os.environ.get("TG_BOT_USERNAME", "").strip()
            if not bot_target:
                self.root.after(0, lambda: self._finish_getcode(None, "Thiếu TG_BOT_USERNAME trong cấu hình"))
                return
            if bot_target.lstrip("-").isdigit(): bot_target = int(bot_target)

            async def _communicate():
                client = await TG_MANAGER.get_client()
                if not client or not await client.is_user_authorized():
                    self.tg_authorized = False
                    self.tg_status_text = "Telegram: Click để đăng nhập"
                    self.tg_status_color = "#F59E0B"
                    self.root.after(0, lambda: self.cv.itemconfig(self.telegram_status, text=self.tg_status_text, fill=self.tg_status_color))
                    return None, "Phiên Telegram hết hạn, hãy bấm đăng nhập lại"
                try:
                    self.root.after(0, lambda: self.set_banner_status("Đang tìm Bot Telegram", f"{bot_target}", mode="loading"))
                    entity = await asyncio.wait_for(client.get_entity(bot_target), timeout=8.0)
                    self.root.after(0, lambda: self.set_banner_status("Đang gửi lệnh", f"/getcode {email}", mode="loading"))
                    sent_msg = await asyncio.wait_for(client.send_message(entity, f"/getcode {email}"), timeout=8.0)
                    last_id = sent_msg.id
                    start_wait = time.time()
                    last_shown_sec = -1
                    while time.time() - start_wait < 20:
                        remain = int(20 - (time.time() - start_wait))
                        if remain != last_shown_sec:
                            last_shown_sec = remain
                            self.root.after(0, lambda r=remain: self.set_banner_status("Đang đợi bot trả lời...", f"Còn lại {r}s", mode="loading"))
                        await asyncio.sleep(0.4)
                        messages = await client.get_messages(entity, limit=2)
                        for msg in messages:
                            if msg.id > last_id and not msg.out and msg.message:
                                reply_text = msg.message.strip()
                                if "no new emails found" in reply_text.lower(): return None, "Bot báo: Không tìm thấy email mới"
                                match = RE_TG_CODE.search(reply_text)
                                if match: return match.group(1), reply_text
                                return reply_text, reply_text
                    return None, "Bot Telegram không phản hồi sau 20s"
                except asyncio.TimeoutError:
                    return None, f"Hết thời gian chờ khi kết nối tới {bot_target}"
                except Exception as ex:
                    await TG_MANAGER.disconnect()
                    raise ex

            code_result, full_reply = TG_MANAGER.run_coro(_communicate())
            self.root.after(0, lambda: self._finish_getcode(code_result, full_reply))
        except Exception as e:
            self.root.after(0, lambda: self._finish_getcode(None, f"Lỗi: {e}"))

    def _fetch_link_from_bot_thread(self, payload_text: str):
        try:
            bot_target = TG_GETLINK_BOT_USERNAME

            async def _communicate():
                client = await TG_MANAGER.get_client()
                if not client or not await client.is_user_authorized():
                    self.tg_authorized = False
                    self.tg_status_text = "Telegram: Click để đăng nhập"
                    self.tg_status_color = "#F59E0B"
                    self.root.after(0, lambda: self.cv.itemconfig(self.telegram_status, text=self.tg_status_text, fill=self.tg_status_color))
                    return None, "Phiên Telegram hết hạn, hãy bấm đăng nhập lại"
                
                try:
                    self.root.after(0, lambda: self.set_banner_status("Đang tìm GetLoginLink Bot", f"{bot_target}", mode="loading"))
                    entity = await asyncio.wait_for(client.get_entity(bot_target), timeout=8.0)

                    self.root.after(0, lambda: self.set_banner_status("Đang gửi lệnh", "🔗 Get Login Link", mode="loading"))
                    sent_cmd = await asyncio.wait_for(client.send_message(entity, "🔗 Get Login Link"), timeout=8.0)
                    last_id = sent_cmd.id
                    
                    start_ready = time.time()
                    while time.time() - start_ready < 6:
                        await asyncio.sleep(0.3)
                        msgs = await client.get_messages(entity, limit=2)
                        for m in msgs:
                            if m.id > last_id and not m.out:
                                last_id = m.id
                                break
                        if last_id != sent_cmd.id:
                            break

                    self.root.after(0, lambda: self.set_banner_status("Đang gửi dữ liệu", "Chờ bot tạo Login Link mới...", mode="loading"))
                    sent_payload = await asyncio.wait_for(client.send_message(entity, payload_text), timeout=8.0)
                    last_id = sent_payload.id

                    start_wait = time.time()
                    last_shown_sec = -1
                    while time.time() - start_wait < 25:
                        remain = int(25 - (time.time() - start_wait))
                        if remain != last_shown_sec:
                            last_shown_sec = remain
                            self.root.after(0, lambda r=remain: self.set_banner_status("Đang đợi bot tạo link...", f"Còn lại {r}s", mode="loading"))
                        await asyncio.sleep(0.4)
                        messages = await client.get_messages(entity, limit=3)
                        for msg in messages:
                            if msg.id > last_id and not msg.out and msg.message:
                                reply_text = msg.message.strip()
                                match = RE_NETFLIX_LINK.search(reply_text)
                                if match:
                                    return match.group(1), reply_text
                                match_http = RE_HTTP_LINK.search(reply_text)
                                if match_http and "t.me" not in match_http.group(1):
                                    return match_http.group(1), reply_text
                                if any(w in reply_text.lower() for w in ("invalid", "error", "lỗi", "không hợp lệ", "expire")):
                                    return None, f"Bot báo: {reply_text[:45]}"
                    return None, "Bot GetLoginLink không phản hồi sau 25s"
                except asyncio.TimeoutError:
                    return None, f"Hết thời gian chờ kết nối tới {bot_target}"
                except Exception as ex:
                    await TG_MANAGER.disconnect()
                    raise ex

            link_result, full_reply = TG_MANAGER.run_coro(_communicate())
            self.root.after(0, lambda: self._finish_getlink(link_result, full_reply))
        except Exception as e:
            self.root.after(0, lambda: self._finish_getlink(None, f"Lỗi: {e}"))

    def _finish_getcode(self, code_result, detail_text):
        self._getcode_running = False
        self.cv.itemconfig(self.getcode_button_label, text="GET", fill=self.TEXT_WHITE)
        self.cv.itemconfig(self.getcode_button_rect, fill=self.BTN_BG_INACTIVE)
        if code_result:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(code_result))
            self.root.update_idletasks()
            self.play_sound()
            self._start_getcode_clear_countdown(f"Mã OTP: {code_result}", "Đã Copy mã vào Clipboard!", 5)
        else:
            self.cv.itemconfig(self.otp_badge_txt, text="ERR", fill="#EF4444")
            self._start_getcode_error_countdown("Lấy code thất bại", detail_text[:40], 5)

    def _finish_getlink(self, link_result, detail_text):
        self._getcode_running = False
        self.cv.itemconfig(self.getcode_button_label, text="GET", fill=self.TEXT_WHITE)
        self.cv.itemconfig(self.getcode_button_rect, fill=self.BTN_BG_INACTIVE)
        if link_result:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(link_result))
            self.root.update_idletasks()
            self.play_sound()
            self._start_getcode_clear_countdown("Đã lấy Login Link!", f"{str(link_result)[:45]}... (Đã copy)", 5)
        else:
            self.cv.itemconfig(self.otp_badge_txt, text="ERR", fill="#EF4444")
            self._start_getcode_error_countdown("Lấy link thất bại", detail_text[:40], 5)

    def check_telegram_connection(self):
        self.tg_status_text = "Telegram: Đang kiểm tra..."
        self.tg_status_color = self.TEXT_MUTED
        self.cv.itemconfig(self.telegram_status, text=self.tg_status_text, fill=self.tg_status_color)
        threading.Thread(target=self._telegram_check_thread, daemon=True).start()

    def _telegram_check_thread(self):
        if TelegramClient is None:
            self._telegram_status_update("Telegram: Thiếu thư viện", False)
            return
        try:
            authorized = TG_MANAGER.run_coro(TG_MANAGER.is_authorized(), timeout=10)
            if authorized: self._telegram_status_update("Telegram: Đã kết nối ✓", True)
            else: self._telegram_status_update("Telegram: Click để đăng nhập", False)
        except Exception:
            self._telegram_status_update("Telegram: Click để đăng nhập", False)

    def _telegram_status_update(self, message, connected):
        self.tg_authorized = connected
        self.tg_status_text = message
        self.tg_status_color = self.TEXT_GREEN if connected else "#F59E0B"
        self.root.after(0, lambda: self.cv.itemconfig(self.telegram_status, text=self.tg_status_text, fill=self.tg_status_color))

    def _block_typing_only_paste(self, event):
        if event.keysym.lower() == "v" and (event.state & 0xC): return None
        return "break"

    def _handle_code_keypress(self, event):
        if event.keysym in ("Return", "KP_Enter"):
            self.submit_tv_code()
            return "break"
        if (event.state & 0xC) and event.keysym.lower() in ("a", "c", "v", "x", "z"): return None
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab", "Shift_L", "Shift_R"): return None
        if event.char and event.char.isdigit():
            try: has_selection = self.code_entry.selection_present()
            except Exception: has_selection = False
            if has_selection or len(self.code_var.get()) < 8: return None
            return "break"
        return "break"

    def _toggle_chrome_checkbox(self, event=None):
        self.show_chrome = not self.show_chrome
        if self.show_chrome:
            self.cv.itemconfig(self.btn_show_rect, outline="#38BDF8")
            self.cv.itemconfig(self.btn_show_text, fill="#38BDF8")
            self.set_banner_status("Hiện Chrome", "Trình duyệt sẽ hiển thị quá trình log CODE", mode="success")
        else:
            self.cv.itemconfig(self.btn_show_rect, outline=self.BORDER_CARD)
            self.cv.itemconfig(self.btn_show_text, fill=self.TEXT_MUTED)
            self.set_banner_status("Ẩn Chrome", "Trình duyệt sẽ chạy ngầm", mode="success")

    def _on_tv_focus_in(self, event=None):
        self.cv.itemconfig(self.tv_input_box, outline=self.BORDER_ACTIVE)
        if self.tv_placeholder_active:
            self.tv_input_text.delete("1.0", "end")
            self.tv_input_text.config(fg=self.TEXT_WHITE)
            self.tv_placeholder_active = False

    def _on_tv_focus_out(self, event=None):
        self.cv.itemconfig(self.tv_input_box, outline=self.BORDER_INPUT)
        content = self.tv_input_text.get("1.0", "end").strip()
        if not content:
            self.tv_placeholder_active = True
            self.tv_input_text.config(fg=self.TEXT_MUTED)
            self.tv_input_text.insert("1.0", "Nhập link ạ...")

    def _on_cskh_focus_in(self, event=None):
        self.cv.itemconfig(self.cskh_input_box, outline=self.BORDER_ACTIVE)
        if self.cskh_placeholder_active:
            self.cskh_input_text.delete("1.0", "end")
            self.cskh_input_text.config(fg=self.TEXT_WHITE)
            self.cskh_placeholder_active = False

    def _on_cskh_focus_out(self, event=None):
        self.cv.itemconfig(self.cskh_input_box, outline=self.BORDER_INPUT)
        content = self.cskh_input_text.get("1.0", "end").strip()
        if not content:
            self.cskh_placeholder_active = True
            self.cskh_input_text.config(fg=self.TEXT_MUTED)
            self.cskh_input_text.insert("1.0", "Nhập thông tin ạ...")

    def _set_code_input_state(self, enabled: bool):
        self.code_enabled = enabled
        if enabled:
            self.cv.itemconfig(self.code_box_rect, outline=self.BORDER_ACTIVE)
            self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_ACTIVE)
            self.cv.itemconfig(self.submit_btn_text, fill="#FFFFFF")
            self.code_entry.config(state="normal", fg=self.TEXT_WHITE)
            self.code_var.set("")
            self.code_entry.focus_set()
        else:
            self.cv.itemconfig(self.code_box_rect, outline=self.BORDER_INPUT)
            self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_INACTIVE)
            self.cv.itemconfig(self.submit_btn_text, fill=self.BTN_TXT_INACTIVE)
            self.code_var.set("Nhập code ạ...")
            self.code_entry.config(state="disabled")

    def _on_submit_hover_in(self, event=None):
        if self.code_enabled: self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_HOVER)

    def _on_submit_hover_out(self, event=None):
        if self.code_enabled: self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_ACTIVE)

    def set_banner_status(self, main_text: str, sub_text: str = "", mode: str = "success"):
        themes = {
            "success": ("#153524", "#245C3D", "#22C55E", "✓"),
            "loading": ("#332711", "#664D1E", "#F59E0B", "..."),
            "error":   ("#38151A", "#63222A", "#FF2E38", "✕"),
        }
        bg, border, icon_bg, icon_char = themes.get(mode, themes["success"])
        self.cv.itemconfig(self.status_bar_rect, fill=bg, outline=border)
        self.cv.itemconfig(self.status_icon_bg, fill=icon_bg)
        self.cv.itemconfig(self.status_icon_txt, text=icon_char)
        self.cv.itemconfig(self.status_left_txt, text=main_text)
        self.cv.itemconfig(self.status_right_txt, text=sub_text)

    def play_sound(self):
        if getattr(self, "is_muted", False): return
        try:
            ext_sound = os.path.join(APP_DIR, "alert.aiff")
            bundled_sound = os.path.join(BUNDLE_DIR, "alert.aiff")
            if sys.platform == "darwin":
                if os.path.exists(ext_sound): sound_file = ext_sound
                elif os.path.exists(bundled_sound): sound_file = bundled_sound
                else: sound_file = "/System/Library/Sounds/Glass.aiff"
                subprocess.Popen(["afplay", sound_file])
            elif sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else: self.root.bell()
        except Exception: pass
    
    def play_startup_sound(self):
        if getattr(self, "is_muted", False): return
        try:
            mp3_path = os.path.join(APP_DIR, "startup.mp3")
            if not os.path.exists(mp3_path):
                mp3_path = os.path.join(BUNDLE_DIR, "startup.mp3")
            if os.path.exists(mp3_path):
                if sys.platform == "darwin":
                    subprocess.Popen(["afplay", mp3_path])
                elif sys.platform == "win32":
                    # Dùng WMPlayer.OCX để phát chuẩn định dạng .mp3 ngầm trên Windows
                    ps_cmd = f'$p = New-Object -ComObject WMPlayer.OCX; $p.url = "{mp3_path}"; $p.controls.play(); Start-Sleep -Seconds 5'
                    subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd], creationflags=0x08000000)
        except Exception: pass

    def _on_code_paste(self, event=None):
        if not self.code_enabled: return "break"
        try: raw_pasted = self.root.clipboard_get()
        except tk.TclError: raw_pasted = ""
        clean_code = RE_NON_DIGIT.sub('', raw_pasted)[:8]
        if clean_code:
            self.code_var.set(clean_code)
            self.set_banner_status("Đã dán text", f"Mã: {clean_code}", mode="success")
            if len(clean_code) == 8: self.root.after(100, self.submit_tv_code)
        else: self.set_banner_status("Lỗi dán dữ liệu", "Không tìm thấy mã TV trong chuỗi vừa dán", mode="error")
        return "break"

    def _validate_code_input(self, *args):
        if not self.code_enabled: return
        val = self.code_var.get()
        clean_val = RE_NON_DIGIT.sub('', val)[:8]
        if val != clean_val: self.code_var.set(clean_val)

    def _on_tv_paste(self, event=None):
        try: pasted_text = self.root.clipboard_get()
        except tk.TclError: pasted_text = ""
        self.tv_input_text.delete("1.0", "end")
        self.tv_input_text.insert("1.0", pasted_text)
        self.tv_input_text.config(fg=self.TEXT_WHITE)
        self.tv_placeholder_active = False
        self.root.after(50, self._process_tv_link)
        return "break"

    def _process_tv_link(self):
        if getattr(self, "_tv_timer", None) is not None:
            self._tv_timer.cancel()
        raw = self.tv_input_text.get("1.0", "end").strip()
        if not raw or raw in ("Nhập link ạ...", "Nhập link ạ....", "Nhập link..."): return
        source_type, cookies_list = parse_input_source(raw)
        if not source_type or not cookies_list:
            self._set_code_input_state(False)
            self._start_tv_error_countdown("Die link/cookies")
            return
        self._set_code_input_state(False)
        self.set_banner_status(f"Đang kiểm tra {source_type}", "Đang đăng nhập vào trang TV8 ngầm", mode="loading")
        self.cmd_queue.put({"action": "warmup", "cookies": cookies_list, "type": source_type, "headless": not self.show_chrome})

    def submit_tv_code(self):
        if not self.code_enabled: return
        code = self.code_var.get().strip()
        if len(code) != 8 or not code.isdigit():
            self.set_banner_status("Mã chưa đủ 8 số", "Vui lòng nhập đúng 8 chữ số trên TV", mode="error")
            return
        self.code_entry.config(state="disabled")
        self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_INACTIVE)
        self.set_banner_status(f"Đang gửi mã {code}", "Đang kích hoạt thiết bị trên Netflix", mode="loading")
        self.cmd_queue.put({"action": "submit", "code": code})

    def _clear_tv_input(self):
        self.tv_input_text.delete("1.0", "end")
        self.tv_placeholder_active = True
        self.tv_input_text.config(fg=self.TEXT_MUTED)
        self.tv_input_text.insert("1.0", "Nhập link ạ...")
        self._set_code_input_state(False)
        self.root.focus_set()
        self.set_banner_status("Sẵn sàng", "Hãy dán JSON hoặc Metadata tiếp theo", mode="success")

    def _start_tv_clear_countdown(self, seconds_left=5):
        def _on_tick(sec):
            self.set_banner_status("Submit Code DONE", f"Tự động xoá dữ liệu sau {sec}s", mode="success")
        self._tv_timer.start(seconds_left, _on_tick, self._clear_tv_input)

    def _start_tv_error_countdown(self, main_err="Lỗi Log CODE", sub_err="", seconds_left=5):
        def _on_tick(sec):
            self.set_banner_status(main_err, f"{sub_err} Tự động xoá dữ liệu sau {sec}s ạ!", mode="error")
        self._tv_timer.start(seconds_left, _on_tick, self._clear_tv_input)

    def _on_cskh_paste(self, event=None):
        if getattr(self, "_cskh_processing", False): return "break"
        self._cskh_processing = True
        try: pasted_text = self.root.clipboard_get()
        except tk.TclError: pasted_text = ""
        self.cskh_input_text.delete("1.0", "end")
        self.cskh_input_text.insert("1.0", pasted_text)
        self.cskh_input_text.config(fg=self.TEXT_WHITE)
        self.cskh_placeholder_active = False
        self.root.after(30, self._process_cskh_text)
        return "break"

    def _process_cskh_text(self):
        try:
            raw = self.cskh_input_text.get("1.0", "end").strip()
            if not raw or raw in ("Nhập thông tin...", "Nhập thông tin đi ạ...", "Nhập thông tin ạ..."): return
            formatted = format_bot_account_text(raw)
            if formatted:
                self.cskh_input_text.delete("1.0", "end")
                self.cskh_input_text.insert("1.0", formatted)
                self.root.clipboard_clear()
                self.root.clipboard_append(formatted)
                self.root.update_idletasks()
                self.play_sound()
                self._start_cskh_clear_countdown(5)
            else:
                self._start_cskh_error_countdown(5)
        finally:
            self.root.after(200, lambda: setattr(self, "_cskh_processing", False))

    def _clear_cskh_input(self):
        self.cv.itemconfig(self.cskh_title_text, text="Format DATA", fill=self.TEXT_WHITE)
        self.cskh_input_text.delete("1.0", "end")
        self.cskh_placeholder_active = True
        self.cskh_input_text.config(fg=self.TEXT_MUTED)
        self.cskh_input_text.insert("1.0", "Nhập thông tin ạ...")
        self.root.focus_set()

    def _start_cskh_clear_countdown(self, seconds_left=5):
        def _on_tick(sec):
            self.cv.itemconfig(self.cskh_title_text, text=f"Chuẩn hoá ({sec}s)", fill="#38BDF8")
            self.set_banner_status("Đã chuẩn hoá & Tự động Copy", f"Tự xoá sau {sec}s ạ", mode="success")
        def _on_done():
            self._clear_cskh_input()
            self.set_banner_status("Đã xoá ô Format DATA", "Sẵn sàng nhận dữ liệu tiếp theo", mode="success")
        self._cskh_timer.start(seconds_left, _on_tick, _on_done)

    def _start_cskh_error_countdown(self, seconds_left=5):
        self.cv.itemconfig(self.cskh_title_text, text="Format DATA", fill=self.TEXT_WHITE)
        def _on_tick(sec):
            self.set_banner_status("Sai định dạng CSKH", f"Tự động xoá dữ liệu sau {sec}s ạ!", mode="error")
        def _on_done():
            self._clear_cskh_input()
            self.set_banner_status("Sẵn sàng", "Hãy dán thông tin CSKH, link TV8 hoặc email", mode="success")
        self._cskh_timer.start(seconds_left, _on_tick, _on_done)

    async def _launch_smart_browser(self, p, headless):
        args = ["--window-size=520,440", "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions", "--no-sandbox", "--disable-background-networking", "--disable-sync", "--disable-translate", "--mute-audio"]
        for ch in ("chrome", "msedge"):
            try: return await p.chromium.launch(channel=ch, headless=headless, args=args)
            except Exception: pass
        return await p.chromium.launch(headless=headless, args=args)

    def _run_async_worker(self):
        asyncio.run(self._worker_loop())

    async def _create_standby_session(self, browser):
        try:
            context = await browser.new_context(viewport={"width": 500, "height": 400}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            await context.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font") else route.continue_())
            pages = context.pages
            page = pages[0] if pages else await context.new_page()
            return {"context": context, "page": page}
        except Exception:
            return None

    async def _worker_loop(self):
        async with async_playwright() as p:
            current_headless = True
            browser = None
            try: browser = await self._launch_smart_browser(p, current_headless)
            except Exception: self.root.after(0, lambda: self.set_banner_status("Thiếu trình duyệt", "Vui lòng cài đặt Google Chrome để dùng Log CODE", mode="error"))
            standby_session = None
            if browser: standby_session = await self._create_standby_session(browser)

            while True:
                try: cmd = self.cmd_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.08)
                    continue

                action = cmd.get("action")
                if action == "warmup":
                    req_headless = cmd.get("headless", True)
                    if browser is None or req_headless != current_headless:
                        await self._close_ready_session()
                        if standby_session:
                            try: await standby_session["context"].close()
                            except Exception: pass
                            standby_session = None
                        if browser:
                            try: await browser.close()
                            except Exception: pass
                        current_headless = req_headless
                        try:
                            browser = await self._launch_smart_browser(p, current_headless)
                            standby_session = await self._create_standby_session(browser)
                        except Exception:
                            self.root.after(0, lambda: self.set_banner_status("Thiếu Google Chrome", "Máy chưa cài đặt Google Chrome!", mode="error"))
                            continue

                    active_session = standby_session
                    standby_session = None
                    if not active_session: active_session = await self._create_standby_session(browser)
                    await self._handle_warmup(browser, active_session, cmd["cookies"], cmd.get("type", "JSON"))
                    if browser and not standby_session: standby_session = await self._create_standby_session(browser)

                elif action == "submit":
                    await self._handle_submit(cmd["code"])
                    if browser and not standby_session: standby_session = await self._create_standby_session(browser)

                elif action == "quit":
                    await self._close_ready_session()
                    if standby_session:
                        try: await standby_session["context"].close()
                        except Exception: pass
                    if browser:
                        try: await browser.close()
                        except Exception: pass
                    break

    async def _close_ready_session(self):
        if self.ready_session:
            try: await self.ready_session["context"].close()
            except Exception: pass
            self.ready_session = None

    async def _unlock_profile_gate_if_needed(self, page):
        profiles = page.locator('.list-profiles li.profile, ul.choose-profile li, [data-uia="action-select-profile"]')
        count = await profiles.count()
        if count == 0: return "NO_GATE"
        for i in range(count):
            prof = profiles.nth(i)
            txt = (await prof.inner_text() or "").lower()
            if "add" in txt or "thêm" in txt: continue
            has_lock = await prof.locator('[data-uia*="lock"], .profile-lock, [class*="lock"], svg[class*="lock"]').count() > 0
            if has_lock: continue
            await prof.click(force=True, timeout=3000)
            await page.wait_for_timeout(1000)
            pin_box = await page.locator('input[type="tel"], input[data-uia*="pin"], .pin-input-container').count()
            if pin_box > 0: continue
            return "UNLOCKED"
        return "ALL_LOCKED"

    async def _handle_warmup(self, browser, session, cookies_list, source_type):
        await self._close_ready_session()
        context = session["context"] if session else None
        page = session["page"] if session else None
        try:
            prepared_cookies = prepare_cookies_for_playwright(cookies_list)
            if not prepared_cookies:
                self.root.after(0, lambda: self._start_tv_error_countdown("Die link/cookies", "Tài khoản lỗi hoặc đã logout", 5))
                if context: await context.close()
                return
            await context.add_cookies(prepared_cookies)
            await page.goto("https://www.netflix.com/tv8", timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(600)
            current_url = page.url.lower()
            if any(k in current_url for k in ["/login", "/clearcookies", "/logout"]):
                self.root.after(0, lambda: self._start_tv_error_countdown("Die link/cookies", "Tài khoản lỗi hoặc đã logout", 5))
                await context.close()
                return
            input_count = await page.locator('input[type="text"], input[type="tel"], input[type="number"], input:not([type="hidden"])').count()
            if input_count == 0:
                gate_status = await self._unlock_profile_gate_if_needed(page)
                if gate_status == "ALL_LOCKED":
                    self.root.after(0, lambda: self.set_banner_status("All locked", "Tất cả Profile đều dính mã PIN", mode="error"))
                    await context.close()
                    return
                elif gate_status == "UNLOCKED":
                    if "tv8" not in page.url.lower(): await page.goto("https://www.netflix.com/tv8", timeout=20000, wait_until="domcontentloaded")
            if "/login" in page.url.lower() or await page.locator('a[href*="/login"], button:has-text("Sign In")').count() > 0:
                self.root.after(0, lambda: self._start_tv_error_countdown("Die link/cookies", "Tài khoản lỗi hoặc đã logout", 5))
                await context.close()
                return
            await page.wait_for_selector('input:not([type="hidden"])', state="visible", timeout=12000)
            self.ready_session = {"context": context, "page": page}
            def unlock_ui():
                self._set_code_input_state(True)
                self.set_banner_status(f"{source_type} hợp lệ", "Nhập mã TV để tiếp tục", mode="success")
            self.root.after(0, unlock_ui)
        except Exception:
            self.root.after(0, lambda: self._start_tv_error_countdown("Die link/cookies", "Tài khoản lỗi hoặc đã logout", 5))
            if context: await context.close()

    async def _handle_submit(self, code):
        if not self.ready_session:
            self.root.after(0, lambda: self._start_tv_error_countdown("Die link/cookies", "Tài khoản lỗi hoặc đã logout", 5))
            return
        page = self.ready_session["page"]
        try:
            inputs = page.locator('input:not([type="hidden"])')
            first_input = inputs.first
            await first_input.click(force=True)
            select_all_key = "Meta+A" if sys.platform == "darwin" else "Control+A"
            await page.keyboard.press(select_all_key)
            await page.keyboard.press("Backspace")
            for _ in range(8): await page.keyboard.press("Backspace")

            await first_input.click(force=True)
            await page.keyboard.type(code, delay=20)
            await page.wait_for_timeout(120)
            submit_selectors = ['button[type="submit"]', 'button[data-uia*="submit"]', 'button[data-uia*="continue"]', 'button.tv8-button', 'button:has-text("Continue")', 'button:has-text("Tiếp tục")', 'button:has-text("Tiếp")', 'button:has-text("Activate")']
            clicked = False
            for sel in submit_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True)
                    clicked = True
                    break
            if not clicked: await page.keyboard.press("Enter")
                
            outcome = "UNKNOWN"
            for _ in range(35):
                await asyncio.sleep(0.25)
                current_url = page.url.lower()
                if "tv8" not in current_url and "/login" not in current_url:
                    outcome = "DONE"
                    break
                dom_status = await page.evaluate('''() => {
                    if (document.querySelector('[data-uia*="success"], .success-icon, .checkmark')) return 'DONE';
                    const bodyText = (document.body.innerText || '').toLowerCase();
                    const successWords = ['all set', 'connected', 'success', 'enjoy netflix on your tv', 'thành công', 'đã kết nối', 'hoàn tất', 'listo', 'conectado', 'autenticación'];
                    for (const w of successWords) { if (bodyText.includes(w)) return 'DONE'; }
                    const errorSelectors = ['[data-uia*="error"]', '[data-uia*="message"]', '.ui-message-error', '.error-message', '.error', 'div[role="alert"]'];
                    for (const sel of errorSelectors) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const style = window.getComputedStyle(el);
                            if (style && style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0) {
                                const txt = (el.innerText || el.textContent || '').trim();
                                if (txt.length > 2) return 'ERROR';
                            }
                        }
                    }
                    const errWords = ['invalid code', 'incorrect code', 'code has expired', 'try again', 'something went wrong', 'not valid', 'mã không hợp lệ', 'thử lại', 'código no válido', 'código incorrecto'];
                    for (const ew of errWords) { if (bodyText.includes(ew)) return 'ERROR'; }
                    const visibleInputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(el => el.offsetHeight > 0);
                    if (visibleInputs.length === 0) return 'DONE';
                    return 'WAIT';
                }''')
                if dom_status == "DONE":
                    outcome = "DONE"
                    break
                elif dom_status == "ERROR":
                    outcome = "ERROR"
                    break
            if outcome == "DONE":
                self.play_sound()
                await self._close_ready_session()
                self.root.after(0, lambda: self._start_tv_clear_countdown(5))
            else:
                self.root.after(0, lambda: self._start_tv_error_countdown("Code Error", "Mã sai hoặc hết hạn", 5))
        except Exception as e:
            if "execution context was destroyed" in str(e).lower() or "target closed" in str(e).lower():
                self.play_sound()
                await self._close_ready_session()
                self.root.after(0, lambda: self._start_tv_clear_countdown(5))
            else:
                self.root.after(0, lambda: self.set_banner_status("Code Error", "Vui lòng kiểm tra lại mã TV", mode="error"))
                self.root.after(0, self._reopen_code_input)

    def _reopen_code_input(self):
        self.code_enabled = True
        self.code_entry.config(state="normal", fg=self.TEXT_WHITE)
        self.cv.itemconfig(self.submit_btn_rect, fill=self.BTN_BG_ACTIVE)
        self.cv.itemconfig(self.submit_btn_text, fill="#FFFFFF")
        self.code_entry.selection_range(0, "end")
        self.code_entry.focus_set()

if __name__ == "__main__":
    # Nạp động file sharetool.py mới nhất nếu đang chạy bản đóng gói (.app/.exe) và đã bấm Update
    updated_script = os.path.join(APP_DIR, "sharetool.py")
    if getattr(sys, 'frozen', False) and os.path.exists(updated_script) and not os.environ.get("NETFLIX_DYNAMIC_LOADED"):
        try:
            os.environ["NETFLIX_DYNAMIC_LOADED"] = "1"
            with open(updated_script, "r", encoding="utf-8") as f:
                code_str = f.read()
            exec(compile(code_str, updated_script, 'exec'), globals())
            sys.exit(0)
        except Exception:
            pass

    root = tk.Tk()
    try: root.tk.call('tk', 'scaling', 1.3333)
    except Exception: pass
    app = ModernNetflixApp(root)
    root.mainloop()
