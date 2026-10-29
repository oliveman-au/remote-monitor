# Remote Monitor Agent
# Runs on employee computers
# Starts on boot, stops if killed until next restart
# Local network only
# Supports view + full remote control with adaptive quality + action panel
# Auto-updates from GitHub every 60 seconds

import asyncio
import json
import socket
import time
import uuid
import platform
import os
import sys
import urllib.request
import subprocess
from pathlib import Path

try:
    import websockets
    import mss
    from PIL import Image
    import io
    import pyautogui
except ImportError:
    print("Missing dependencies. Run: pip install websockets mss Pillow pyautogui")
    raise

# Disable pyautogui failsafe
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# Config
CONFIG_FILE = Path(__file__).parent / "config.json"
AGENT_FILE = Path(__file__).resolve()
VERSION_FILE = Path(__file__).parent / "version.txt"
DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766

# GitHub raw URLs (repo must be public)
GITHUB_USER = "oliveman-au"
GITHUB_REPO = "remote-monitor"
GITHUB_BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"

CURRENT_VERSION = "1.4"

# Quality ladder for control mode
QUALITY_LEVELS = [
    (1280, 720, 30, 70),
    (1280, 720, 60, 65),
    (1920, 1080, 30, 65),
    (1920, 1080, 60, 60),
    (2560, 1440, 30, 60),
    (2560, 1440, 60, 55),
    (3840, 2160, 30, 55),
    (3840, 2160, 60, 50),
]

class Agent:
    def __init__(self):
        self.id = self.get_or_create_id()
        self.hostname = platform.node()
        self.manager_uri = None
        self.websocket = None
        self.streaming = False
        self.controlling = False
        self.fps = 30
        self.running = True
        self.screen_size = pyautogui.size()
        self.quality_level = 0
        self.stable_count = 0
        self.unstable_count = 0

    def get_or_create_id(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                data = json.load(f)
                return data.get("id", str(uuid.uuid4()))
        else:
            agent_id = str(uuid.uuid4())
            with open(CONFIG_FILE, "w") as f:
                json.dump({"id": agent_id}, f)
            return agent_id

    def get_local_version(self):
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text().strip()
        return CURRENT_VERSION

    async def check_for_updates(self):
        while self.running:
            try:
                version_url = f"{RAW_BASE}/version.txt"
                with urllib.request.urlopen(version_url, timeout=10) as resp:
                    remote_version = resp.read().decode().strip()
                local_version = self.get_local_version()
                if remote_version != local_version:
                    print(f"Update detected: {local_version} → {remote_version}. Installing...")
                    agent_url = f"{RAW_BASE}/agent.py"
                    with urllib.request.urlopen(agent_url, timeout=15) as resp:
                        new_code = resp.read()
                    tmp = AGENT_FILE.with_suffix(".py.new")
                    tmp.write_bytes(new_code)
                    os.replace(tmp, AGENT_FILE)
                    VERSION_FILE.write_text(remote_version)
                    print("Update installed. Restarting...")
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception:
                pass
            await asyncio.sleep(60)

    async def discover_manager(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(5.0)
        message = b"REMOTE_MONITOR_DISCOVERY"
        try:
            sock.sendto(message, ("<broadcast>", DISCOVERY_PORT))
            data, addr = sock.recvfrom(1024)
            if data.startswith(b"REMOTE_MONITOR_MANAGER"):
                port = int(data.split(b":")[1])
                self.manager_uri = f"ws://{addr[0]}:{port}/agent"
                print(f"Discovered manager at {self.manager_uri}")
                return True
        except Exception as e:
            print(f"Discovery failed: {e}")
        finally:
            sock.close()
        return False

    async def capture_frame(self, width, height, quality):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return buf.getvalue()

    async def stream_screen(self):
        while self.streaming and self.websocket and self.running:
            try:
                if self.controlling:
                    w, h, target_fps, q = QUALITY_LEVELS[self.quality_level]
                else:
                    w, h, target_fps, q = 1280, 720, self.fps, 70

                start = time.perf_counter()
                frame = await self.capture_frame(w, h, q)
                await self.websocket.send(frame)
                elapsed = time.perf_counter() - start

                if self.controlling:
                    target_interval = 1.0 / target_fps
                    if elapsed < target_interval * 0.75:
                        self.stable_count += 1
                        self.unstable_count = 0
                        if self.stable_count >= 15 and self.quality_level < len(QUALITY_LEVELS) - 1:
                            self.quality_level += 1
                            self.stable_count = 0
                            print(f"Quality up to level {self.quality_level}")
                    elif elapsed > target_interval * 1.1:
                        self.unstable_count += 1
                        self.stable_count = 0
                        if self.unstable_count >= 5 and self.quality_level > 0:
                            self.quality_level -= 1
                            self.unstable_count = 0
                            print(f"Quality down to level {self.quality_level}")
                    else:
                        self.stable_count = max(0, self.stable_count - 1)

                sleep_time = max(0, (1.0 / target_fps) - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            except Exception as e:
                print(f"Stream error: {e}")
                break
        self.streaming = False

    def handle_control(self, data):
        cmd = data.get("cmd")
        try:
            if cmd == "mouse_move":
                x = int(data["x"] * self.screen_size.width)
                y = int(data["y"] * self.screen_size.height)
                pyautogui.moveTo(x, y, duration=0)
            elif cmd == "mouse_click":
                button = data.get("button", "left")
                pressed = data.get("pressed", True)
                if pressed:
                    pyautogui.mouseDown(button=button)
                else:
                    pyautogui.mouseUp(button=button)
            elif cmd == "mouse_scroll":
                amount = data.get("amount", 0)
                pyautogui.scroll(amount)
            elif cmd == "key":
                key = data.get("key")
                pressed = data.get("pressed", True)
                if pressed:
                    pyautogui.keyDown(key)
                else:
                    pyautogui.keyUp(key)
        except Exception as e:
            print(f"Control error: {e}")

    def run_action(self, action, extra=None):
        """Execute useful/fun actions on the remote machine"""
        try:
            if action == "volume_up":
                pyautogui.press("volumeup")
            elif action == "volume_down":
                pyautogui.press("volumedown")
            elif action == "volume_mute":
                pyautogui.press("volumemute")
            elif action == "lock":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            elif action == "sleep":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
            elif action == "open_notepad":
                subprocess.Popen(["notepad.exe"])
            elif action == "open_calculator":
                subprocess.Popen(["calc.exe"])
            elif action == "open_taskmgr":
                subprocess.Popen(["taskmgr.exe"])
            elif action == "open_explorer":
                subprocess.Popen(["explorer.exe"])
            elif action == "open_browser":
                subprocess.Popen(["start", "https://www.google.com"], shell=True)
            elif action == "open_youtube":
                subprocess.Popen(["start", "https://www.youtube.com"], shell=True)
            elif action == "minimize_all":
                pyautogui.hotkey("win", "d")
            elif action == "show_desktop":
                pyautogui.hotkey("win", "d")
            elif action == "screenshot":
                img = pyautogui.screenshot()
                path = Path.home() / "Desktop" / f"screenshot_{int(time.time())}.png"
                img.save(path)
                print(f"Screenshot saved to {path}")
            elif action == "message" and extra:
                subprocess.run(["msg", "*", extra], check=False)
            elif action == "brightness_up":
                # Best-effort for laptops
                subprocess.run(["powershell", "-Command", "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,80)"], check=False)
            elif action == "brightness_down":
                subprocess.run(["powershell", "-Command", "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,30)"], check=False)
            elif action == "open_cmd":
                subprocess.Popen(["cmd.exe"])
            elif action == "open_powershell":
                subprocess.Popen(["powershell.exe"])
            elif action == "play_beep":
                pyautogui.alert("Beep!", "Remote")
            elif action == "type_text" and extra:
                pyautogui.write(extra, interval=0.02)
            else:
                print(f"Unknown action: {action}")
        except Exception as e:
            print(f"Action error ({action}): {e}")

    async def handle_messages(self):
        async for message in self.websocket:
            try:
                if isinstance(message, bytes):
                    continue
                data = json.loads(message)
                cmd = data.get("cmd")
                if cmd == "start_stream":
                    self.fps = data.get("fps", 30)
                    if self.fps not in (30, 60):
                        self.fps = 30
                    self.streaming = True
                    asyncio.create_task(self.stream_screen())
                elif cmd == "stop_stream":
                    self.streaming = False
                elif cmd == "start_control":
                    self.controlling = True
                    self.quality_level = 0
                    self.stable_count = 0
                    self.unstable_count = 0
                    print("Control mode started")
                elif cmd == "stop_control":
                    self.controlling = False
                    self.quality_level = 0
                    print("Control mode stopped")
                elif cmd in ("mouse_move", "mouse_click", "mouse_scroll", "key"):
                    if self.controlling:
                        self.handle_control(data)
                elif cmd == "action":
                    if self.controlling:
                        self.run_action(data.get("action"), data.get("extra"))
                elif cmd == "ping":
                    await self.websocket.send(json.dumps({"type": "pong"}))
            except Exception as e:
                print(f"Message error: {e}")

    async def connect(self):
        asyncio.create_task(self.check_for_updates())
        while self.running:
            if not self.manager_uri:
                found = await self.discover_manager()
                if not found:
                    await asyncio.sleep(10)
                    continue
            try:
                async with websockets.connect(self.manager_uri) as ws:
                    self.websocket = ws
                    await ws.send(json.dumps({
                        "type": "register",
                        "id": self.id,
                        "hostname": self.hostname,
                        "os": platform.system()
                    }))
                    print(f"Connected as {self.hostname}")
                    await self.handle_messages()
            except Exception as e:
                print(f"Connection error: {e}")
                self.websocket = None
                self.streaming = False
                self.controlling = False
                await asyncio.sleep(5)

    def run(self):
        asyncio.run(self.connect())

if __name__ == "__main__":
    agent = Agent()
    agent.run()
