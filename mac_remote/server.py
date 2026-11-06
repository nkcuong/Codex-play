#!/usr/bin/env python3
"""Mac Remote - control your Mac from your phone or another computer.

Runs a small HTTP server on the Mac. Open http://<mac-ip>:8765 from any device
on the same network, enter the token shown at startup, and press buttons.

Actions: lock, screensaver, unlock, reboot, check/install OS updates, open Safari, open stocks.

Only the Python standard library is used, so there is nothing to install.
"""

import argparse
import json
import os
import secrets
import shlex
import socket
import stat
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CONFIG_DIR = Path.home() / ".mac_remote"
CONFIG_FILE = CONFIG_DIR / "config.json"
KEYCHAIN_SERVICE = "mac_remote_unlock"
DEFAULT_PORT = 8765
STOCKS_URL = "https://www.investing.com/portfolio/?portfolioID=MDZjMm8%2FMms0am1mMmA5PQ%3D%3D"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    else:
        cfg = {}
    changed = False
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        changed = True
    if "port" not in cfg:
        cfg["port"] = DEFAULT_PORT
        changed = True
    if "safari_url" not in cfg:
        cfg["safari_url"] = ""
        changed = True
    if "stocks_url" not in cfg:
        cfg["stocks_url"] = STOCKS_URL
        changed = True
    if changed:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    return cfg


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------

class Runner:
    """Runs shell commands, records their output, supports a dry-run mode."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.lock = threading.Lock()
        self.log = []  # list of dicts, newest last

    def record(self, action, cmd, ok, output):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "action": action,
            "cmd": cmd if isinstance(cmd, str) else " ".join(shlex.quote(c) for c in cmd),
            "ok": ok,
            "output": (output or "").strip()[-2000:],
        }
        with self.lock:
            self.log.append(entry)
            del self.log[:-50]
        print(f"[{entry['time']}] {action}: {'ok' if ok else 'FAILED'} - {entry['cmd']}", flush=True)
        if entry["output"]:
            print("   " + entry["output"].replace("\n", "\n   "), flush=True)
        return entry

    def run(self, action, cmd, timeout=60, secret=None):
        """Run cmd (list). `secret` is a string to redact from logs."""
        shown = [c.replace(secret, "********") if secret and secret in c else c for c in cmd]
        if self.dry_run:
            return self.record(action, shown, True, "(dry run, not executed)")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            output = (p.stdout + p.stderr)
            if secret:
                output = output.replace(secret, "********")
            return self.record(action, shown, p.returncode == 0, output)
        except subprocess.TimeoutExpired:
            return self.record(action, shown, False, f"timed out after {timeout}s")
        except FileNotFoundError as e:
            return self.record(action, shown, False, str(e))

    def run_background(self, action, cmd, timeout=3600):
        """For long jobs like OS updates: start now, log when done."""
        entry = self.record(action, cmd, True, "started in background, see log for result")
        if self.dry_run:
            return entry
        threading.Thread(target=self.run, args=(action + " (result)", cmd, timeout), daemon=True).start()
        return entry


# ---------------------------------------------------------------------------
# macOS actions
# ---------------------------------------------------------------------------

def osascript(*lines):
    cmd = ["osascript"]
    for line in lines:
        cmd += ["-e", line]
    return cmd


def unlock_password():
    """Read the login password from the macOS Keychain (never stored in a file)."""
    p = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    return p.stdout.strip() if p.returncode == 0 else ""


class Actions:
    def __init__(self, runner, cfg):
        self.r = runner
        self.cfg = cfg

    def lock(self):
        # Ctrl+Cmd+Q is the system "Lock Screen" shortcut. Needs Accessibility
        # permission for the process running this server (Terminal / Python).
        return self.r.run("lock", osascript(
            'tell application "System Events" to keystroke "q" using {control down, command down}'))

    def screensaver(self):
        return self.r.run("screensaver", ["open", "-a", "ScreenSaverEngine"])

    def unlock(self):
        pw = "" if self.r.dry_run else unlock_password()
        if not pw and not self.r.dry_run:
            return self.r.record("unlock", "security find-generic-password", False,
                                 "No password in Keychain. Run: python3 server.py --set-unlock-password")
        pw = pw or "dryrun"
        esc = pw.replace("\\", "\\\\").replace('"', '\\"')  # AppleScript string escaping
        # 1) wake the display, 2) dismiss screensaver, 3) type password + return.
        self.r.run("unlock (wake)", ["caffeinate", "-u", "-t", "3"], timeout=10)
        time.sleep(1.5)
        return self.r.run("unlock", osascript(
            'tell application "System Events"',
            '  key code 53',  # Esc wakes the login field
            '  delay 1',
            f'  keystroke "{esc}"',
            '  keystroke return',
            'end tell',
        ), secret=pw)

    def reboot(self):
        # Prefer a clean restart via sudo (needs the sudoers rule from README);
        # fall back to asking System Events, which may show a confirmation dialog.
        e = self.r.run("reboot", ["sudo", "-n", "/sbin/shutdown", "-r", "now"])
        if not e["ok"]:
            e = self.r.run("reboot (fallback)", osascript('tell application "System Events" to restart'))
        return e

    def check_updates(self):
        return self.r.run("check updates", ["softwareupdate", "-l"], timeout=300)

    def install_updates(self):
        return self.r.run_background(
            "install updates",
            ["sudo", "-n", "/usr/sbin/softwareupdate", "-i", "-a", "--restart"],
        )

    def safari(self, url=""):
        url = url or self.cfg.get("safari_url") or ""
        cmd = ["open", "-a", "Safari"] + ([url] if url else [])
        return self.r.run("safari", cmd)

    def stocks(self):
        url = self.cfg.get("stocks_url") or STOCKS_URL
        return self.r.run("stocks", ["open", "-a", "Safari", url])


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Mac Remote</title>
<style>
  :root { color-scheme: light dark; --bg:#f4f4f7; --card:#fff; --fg:#111; --muted:#777; --accent:#0a84ff; --danger:#ff453a; --ok:#30d158; }
  @media (prefers-color-scheme: dark) { :root { --bg:#000; --card:#1c1c1e; --fg:#f2f2f7; --muted:#8e8e93; } }
  * { box-sizing:border-box }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--fg); padding:16px; padding-bottom:40px }
  h1 { font-size:22px; margin:8px 0 2px } .sub { color:var(--muted); font-size:13px; margin-bottom:16px }
  .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px }
  button { border:0; border-radius:16px; background:var(--card); color:var(--fg); padding:22px 10px; font-size:16px; font-weight:600; box-shadow:0 1px 3px rgba(0,0,0,.12); cursor:pointer; -webkit-tap-highlight-color:transparent }
  button:active { transform:scale(.97) } button .ic { display:block; font-size:30px; margin-bottom:8px }
  button.danger { color:var(--danger) } button.wide { grid-column:1/-1 }
  .row { display:flex; gap:8px; margin-top:12px } input { flex:1; border:1px solid #8884; border-radius:10px; padding:12px; font-size:16px; background:var(--card); color:var(--fg) }
  #status { margin-top:16px; padding:12px; border-radius:12px; background:var(--card); font-size:13px; white-space:pre-wrap; word-break:break-word; min-height:44px; color:var(--muted) }
  #status.ok { color:var(--ok) } #status.err { color:var(--danger) }
  #log { margin-top:12px; font-size:12px; color:var(--muted) } #log div { padding:6px 0; border-top:1px solid #8883 }
  .tok { display:flex; gap:8px; margin-bottom:14px }
</style>
</head>
<body>
<h1>Mac Remote</h1>
<div class="sub" id="host">connecting…</div>

<div class="tok"><input id="token" type="password" placeholder="Access token" autocomplete="off"><button style="padding:10px 14px" onclick="saveToken()">Save</button></div>

<div class="grid">
  <button onclick="act('lock')"><span class="ic">🔒</span>Lock screen</button>
  <button onclick="act('unlock')"><span class="ic">🔓</span>Unlock</button>
  <button onclick="act('screensaver')"><span class="ic">🌌</span>Screen saver</button>
  <button onclick="act('safari')"><span class="ic">🧭</span>Open Safari</button>
  <button onclick="act('stocks')"><span class="ic">📈</span>Open Stocks</button>
  <button onclick="act('check_updates')"><span class="ic">🔍</span>Check updates</button>
  <button class="danger wide" onclick="confirmAct('install_updates','Install all macOS updates and restart if needed?')"><span class="ic">⬇️</span>Update macOS</button>
  <button class="danger wide" onclick="confirmAct('reboot','Reboot the Mac now?')"><span class="ic">🔄</span>Reboot</button>
</div>

<div class="row"><input id="url" placeholder="https://… (optional URL for Safari)" inputmode="url"><button style="padding:10px 14px" onclick="act('safari', {url: document.getElementById('url').value})">Go</button></div>

<div id="status">Ready.</div>
<div id="log"></div>

<script>
const $ = id => document.getElementById(id);
$('token').value = localStorage.getItem('token') || '';
function saveToken(){ localStorage.setItem('token', $('token').value.trim()); status('Token saved.'); refresh(); }
function status(msg, cls){ const s=$('status'); s.textContent=msg; s.className=cls||''; }
function headers(){ return {'Content-Type':'application/json','X-Token': $('token').value.trim()}; }
function confirmAct(a, q){ if (confirm(q)) act(a); }
async function act(action, body){
  status('Running ' + action + '…');
  try {
    const r = await fetch('/api/' + action, {method:'POST', headers: headers(), body: JSON.stringify(body||{})});
    const j = await r.json();
    if (r.status === 401) { status('Wrong or missing token.', 'err'); return; }
    status((j.ok ? '✓ ' : '✗ ') + j.action + (j.output ? '\n' + j.output : ''), j.ok ? 'ok' : 'err');
    refresh();
  } catch (e) { status('Request failed: ' + e, 'err'); }
}
async function refresh(){
  try {
    const r = await fetch('/api/status', {headers: headers()});
    if (r.status === 401) { $('host').textContent = 'Enter your access token'; return; }
    const j = await r.json();
    $('host').textContent = j.host + (j.dry_run ? ' (dry run)' : '');
    $('log').innerHTML = j.log.slice().reverse().slice(0,10).map(e =>
      `<div><b>${e.time}</b> ${e.ok?'✓':'✗'} ${e.action}${e.output?' — '+e.output.split('\n')[0].slice(0,120):''}</div>`).join('');
  } catch (e) {}
}
refresh(); setInterval(refresh, 10000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

def make_handler(cfg, actions, runner):
    token = cfg["token"]
    hostname = socket.gethostname()

    class Handler(BaseHTTPRequestHandler):
        server_version = "MacRemote/1.0"

        def log_message(self, fmt, *args):  # quieter default logging
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authed(self):
            given = self.headers.get("X-Token") or parse_qs(urlparse(self.path).query).get("token", [""])[0]
            return secrets.compare_digest(given or "", token)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self._send(HTTPStatus.OK, INDEX_HTML, "text/html")
            if not self._authed():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "bad token"})
            if path == "/api/status":
                return self._send(HTTPStatus.OK, {"host": hostname, "dry_run": runner.dry_run, "log": runner.log})
            return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "bad token"})
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                body = {}
            name = path.removeprefix("/api/")
            routes = {
                "lock": actions.lock,
                "unlock": actions.unlock,
                "screensaver": actions.screensaver,
                "reboot": actions.reboot,
                "check_updates": actions.check_updates,
                "install_updates": actions.install_updates,
                "safari": lambda: actions.safari(str(body.get("url", ""))[:2000]),
                "stocks": actions.stocks,
            }
            fn = routes.get(name)
            if not fn:
                return self._send(HTTPStatus.NOT_FOUND, {"error": f"unknown action {name}"})
            return self._send(HTTPStatus.OK, fn())

    return Handler


def set_unlock_password():
    import getpass
    pw = getpass.getpass("Mac login password (stored in Keychain, used only for Unlock): ")
    subprocess.run(["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE],
                   capture_output=True)
    p = subprocess.run(["security", "add-generic-password", "-s", KEYCHAIN_SERVICE,
                        "-a", os.environ.get("USER", "user"), "-w", pw, "-U"], capture_output=True, text=True)
    print("Saved to Keychain." if p.returncode == 0 else f"Failed: {p.stderr}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, help=f"port to listen on (default {DEFAULT_PORT})")
    ap.add_argument("--bind", default="0.0.0.0", help="address to bind (default all interfaces)")
    ap.add_argument("--dry-run", action="store_true", help="print commands instead of running them")
    ap.add_argument("--set-unlock-password", action="store_true", help="store login password in Keychain for Unlock")
    ap.add_argument("--show-token", action="store_true", help="print the access token and exit")
    ap.add_argument("--reset-token", action="store_true", help="generate a new access token")
    args = ap.parse_args()

    if args.set_unlock_password:
        return set_unlock_password()

    cfg = load_config()
    if args.reset_token:
        cfg["token"] = secrets.token_urlsafe(24)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    if args.show_token or args.reset_token:
        print(cfg["token"])
        return

    port = args.port or cfg["port"]
    runner = Runner(dry_run=args.dry_run)
    actions = Actions(runner, cfg)
    httpd = ThreadingHTTPServer((args.bind, port), make_handler(cfg, actions, runner))
    print(f"Mac Remote listening on http://{lan_ip()}:{port}/")
    local = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True).stdout.strip() \
        if sys.platform == "darwin" else ""
    if local:
        print(f"Or use the fixed name:      http://{local}.local:{port}/")
    print(f"Access token: {cfg['token']}")
    if args.dry_run:
        print("DRY RUN: commands are logged, not executed.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9+ required")
    main()
