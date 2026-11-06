# Mac Remote

Control your Mac from your phone (or any browser on the same Wi‑Fi):
**Lock screen · Unlock · Screen saver · Open Safari · Check updates · Update macOS · Reboot**

Pure Python 3 standard library. Nothing to install.

## Quick start (on the Mac)

```bash
cd mac_remote
python3 server.py
```

It prints something like:

```
Mac Remote listening on http://192.168.1.23:8765/
Access token: Xk3...
```

Open that URL on your phone, paste the token, tap buttons. Add the page to your
home screen for an app-like feel.

## One-time macOS setup

| Feature | What to do |
|---|---|
| Lock screen, Unlock | System Settings → Privacy & Security → **Accessibility** → add **Terminal** (or whatever runs `python3`). Unlock also needs the password stored once: `python3 server.py --set-unlock-password` (it goes into the macOS Keychain, not a file). |
| Unlock | System Settings → Lock Screen → *Require password after screen saver begins* must be set, and the Mac must not be fully asleep with "Wake for network access" off. Enable System Settings → Battery/Energy → **Wake for network access**. |
| Reboot, Update macOS | Allow these two commands without a password: `sudo visudo -f /etc/sudoers.d/mac_remote` and paste `sudoers.example` with your username. Without this, Reboot falls back to an on-screen "Restart" request and Update will fail. |
| Open Safari | Works out of the box. Put a default URL in `~/.mac_remote/config.json` (`"safari_url"`) or type one in the page. |

## Run at login

```bash
./install.sh      # installs a launchd user agent, prints the URL and token
./uninstall.sh    # removes it
```

Logs go to `~/.mac_remote/server.log`.

## Security notes

* Every request must carry the token (`X-Token` header or `?token=`), kept in `~/.mac_remote/config.json` (mode 600). Run `python3 server.py --reset-token` to rotate it.
* The server listens on your local network only. Do **not** port‑forward it to the internet; use Tailscale or a VPN if you want remote access from outside.
* The unlock password lives in the Keychain under the service name `mac_remote_unlock` and is redacted from logs.

## API

`POST /api/<action>` with header `X-Token: <token>`.
Actions: `lock`, `unlock`, `screensaver`, `safari` (JSON body `{"url": "..."}` optional), `check_updates`, `install_updates`, `reboot`.
`GET /api/status` returns the host name and the last 50 log entries.

Example:

```bash
curl -X POST -H "X-Token: $TOKEN" http://192.168.1.23:8765/api/lock
```

## Test without a Mac

`python3 server.py --dry-run` logs the commands instead of executing them.
