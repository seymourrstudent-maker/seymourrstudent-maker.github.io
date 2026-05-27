# Group Chat

A multithreaded TCP group-chat application in Python, with an optional browser-based UI.

```
group_chat/
├── server/
│   └── server.py        # TCP chat server (stdlib only)
├── client/
│   └── client.py        # Terminal client with ANSI color (stdlib only)
├── web_client/
│   ├── ws_bridge.py     # WebSocket ↔ TCP bridge  (requires: websockets)
│   └── index.html       # Browser UI (open directly — no build step)
├── requirements.txt
└── .gitignore
```

---

## Quick start (terminal)

**Terminal 1 — start the server**
```bash
cd server
python server.py
# or pick a custom port:
python server.py --port 7777
```

**Terminal 2, 3, … — connect clients**
```bash
cd client
python client.py
# or pass everything up front:
python client.py --host 127.0.0.1 --port 6000 --name Alice
```

---

## Running on separate machines

1. Start the server on machine A.
2. Find machine A's IP (`ipconfig` on Windows, `ifconfig` / `ip addr` on macOS/Linux).
3. On every other machine run `python client.py --host <machine-A-IP>`.
4. Make sure your firewall allows the chosen port (default **6000**).

---

## Chat commands

| Command | Alias | Effect |
|---------|-------|--------|
| `/list` | `/who`, `/users` | List online users |
| `/help` | — | Show help |
| `/quit` | `/exit`, `/q` | Leave the chat |

---

## Browser UI (optional)

The web client gives you a polished in-browser interface.

**Step 1** — install the bridge dependency
```bash
pip install websockets
# or: pip install -r requirements.txt
```

**Step 2** — start the server (if not already running)
```bash
cd server && python server.py
```

**Step 3** — start the WebSocket bridge
```bash
cd web_client
python ws_bridge.py
# custom addresses:
python ws_bridge.py --tcp-host 127.0.0.1 --tcp-port 6000 --ws-port 8765
```

**Step 4** — open `web_client/index.html` in any browser.  
Fill in the bridge host/port, enter your name, and click **Connect**.

> **Note:** Because the page is opened as a local file (`file://`), browsers allow
> `ws://localhost` connections without HTTPS. If you host the file on a web server
> you will need to switch to a secure WebSocket (`wss://`) or serve over HTTP from
> the same machine.

---

## Architecture

```
Browser ──ws──► ws_bridge.py ──TCP──► server.py ◄──TCP── client.py
                                           │
                                      (broadcasts to
                                       all connected
                                        sockets)
```

The server is intentionally kept simple: one thread per client, a shared list
protected by a `threading.Lock`, and a `broadcast()` helper that cleans up dead
sockets automatically.

---

## Python version

Python 3.10+ (uses the `X | Y` union type hint for `socket.socket | None`).  
Drop back to `Optional[socket.socket]` from `typing` if you need 3.9 or earlier.
