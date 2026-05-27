"""
group_chat/server/server.py
Multithreaded TCP group-chat server.

Usage:
    python server.py                  # defaults: host=0.0.0.0, port=6000
    python server.py --port 7777
    python server.py --host 127.0.0.1 --port 7777
"""

import argparse
import socket
import threading
import datetime
import sys

BUFFER_SIZE = 4096

clients: list[socket.socket] = []
client_names: dict[socket.socket, str] = {}
lock = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────────────

def timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{timestamp()}] {msg}", flush=True)


def send(sock: socket.socket, text: str) -> bool:
    """Send text to a single socket. Returns False on failure."""
    try:
        sock.sendall(text.encode("utf-8"))
        return True
    except OSError:
        return False


def broadcast(message: str, exclude: socket.socket | None = None) -> None:
    """Send *message* to every connected client except *exclude*."""
    with lock:
        dead: list[socket.socket] = []
        for client in clients:
            if client is exclude:
                continue
            if not send(client, message):
                dead.append(client)
        for client in dead:
            _remove_client_locked(client)


def _remove_client_locked(sock: socket.socket) -> None:
    """Must be called while holding *lock*."""
    if sock in clients:
        clients.remove(sock)
    client_names.pop(sock, None)
    try:
        sock.close()
    except OSError:
        pass


def remove_client(sock: socket.socket, reason: str = "disconnected") -> None:
    with lock:
        name = client_names.get(sock, "Unknown")
        _remove_client_locked(sock)
    log(f"{name} {reason}.")
    broadcast(f"[{timestamp()}] *** {name} has left the chat. ***\n")


# ── client handler ────────────────────────────────────────────────────────────

def handle_client(sock: socket.socket, address: tuple) -> None:
    # ── name negotiation ──────────────────────────────────────────────────
    send(sock, "Enter your name: ")
    try:
        raw = sock.recv(BUFFER_SIZE)
    except OSError:
        sock.close()
        return

    name = raw.decode("utf-8").strip() or f"Client-{address[1]}"

    with lock:
        # Ensure unique names
        existing = set(client_names.values())
        base, n = name, 2
        while name in existing:
            name = f"{base}_{n}"
            n += 1
        clients.append(sock)
        client_names[sock] = name

    log(f"{name} connected from {address[0]}:{address[1]}")
    broadcast(f"[{timestamp()}] *** {name} has joined the chat. ***\n", exclude=sock)
    send(sock, (
        f"[{timestamp()}] Welcome, {name}!  "
        "Type /help for commands, /quit to leave.\n"
    ))

    # ── message loop ──────────────────────────────────────────────────────
    try:
        while True:
            try:
                data = sock.recv(BUFFER_SIZE)
            except OSError:
                break

            if not data:
                break

            message = data.decode("utf-8").strip()
            if not message:
                continue

            # ── commands ──────────────────────────────────────────────────
            if message.startswith("/"):
                cmd = message.lower()

                if cmd in ("/quit", "/exit", "/q"):
                    send(sock, "Goodbye!\n")
                    break

                elif cmd in ("/list", "/who", "/users"):
                    with lock:
                        names = list(client_names.values())
                    user_list = ", ".join(sorted(names))
                    send(sock, f"[{timestamp()}] Online ({len(names)}): {user_list}\n")

                elif cmd == "/help":
                    send(sock, (
                        f"[{timestamp()}] Commands:\n"
                        "  /list  or /who   — list online users\n"
                        "  /quit  or /exit  — leave the chat\n"
                        "  /help            — show this message\n"
                    ))

                else:
                    send(sock, f"[{timestamp()}] Unknown command: {message}\n")

                continue

            # ── regular message ───────────────────────────────────────────
            full = f"[{timestamp()}] {name}: {message}\n"
            log(full.strip())
            broadcast(full)

    finally:
        remove_client(sock)


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Group-chat TCP server")
    p.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=6000, help="Port (default 6000)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    host, port = args.host, args.port

    print("=" * 50)
    print("  Group Chat Server")
    print(f"  Listening on {host}:{port}")
    print("  Ctrl-C to stop")
    print("=" * 50)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen()

        try:
            while True:
                client_sock, address = srv.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(client_sock, address),
                    daemon=True,
                )
                t.start()
        except KeyboardInterrupt:
            print("\nServer shutting down…")
            with lock:
                for client in list(clients):
                    send(client, "Server is shutting down. Goodbye!\n")
                    _remove_client_locked(client)
            sys.exit(0)


if __name__ == "__main__":
    main()
