"""
group_chat/client/client.py
Terminal group-chat client with ANSI color support.

Usage:
    python client.py                       # interactive prompts
    python client.py --host 127.0.0.1 --port 6000 --name Alice
"""

import argparse
import socket
import sys
import threading

BUFFER_SIZE = 4096


# ── ANSI color helpers ────────────────────────────────────────────────────────

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = _supports_color()


class C:
    """ANSI color codes (no-op strings when color is unsupported)."""
    RESET   = "\033[0m"   if USE_COLOR else ""
    BOLD    = "\033[1m"   if USE_COLOR else ""
    DIM     = "\033[2m"   if USE_COLOR else ""
    GREEN   = "\033[32m"  if USE_COLOR else ""
    CYAN    = "\033[36m"  if USE_COLOR else ""
    YELLOW  = "\033[33m"  if USE_COLOR else ""
    MAGENTA = "\033[35m"  if USE_COLOR else ""
    RED     = "\033[31m"  if USE_COLOR else ""
    WHITE   = "\033[97m"  if USE_COLOR else ""


def colorize(text: str) -> str:
    """Apply colors to server messages."""
    lower = text.lower()
    if "has joined" in lower:
        return f"{C.GREEN}{text}{C.RESET}"
    if "has left" in lower or "disconnected" in lower:
        return f"{C.YELLOW}{text}{C.RESET}"
    if "server is shutting down" in lower:
        return f"{C.RED}{C.BOLD}{text}{C.RESET}"
    if lower.startswith("[") and "welcome" in lower:
        return f"{C.CYAN}{text}{C.RESET}"
    # Highlight "[HH:MM:SS] Name:" prefix
    if text.startswith("["):
        try:
            bracket_end = text.index("]") + 1
            rest = text[bracket_end:].lstrip()
            colon = rest.index(":") if ":" in rest else -1
            if colon > 0:
                ts   = text[:bracket_end]
                name = rest[:colon]
                msg  = rest[colon:]
                return (
                    f"{C.DIM}{ts}{C.RESET} "
                    f"{C.MAGENTA}{C.BOLD}{name}{C.RESET}"
                    f"{C.WHITE}{msg}{C.RESET}"
                )
        except ValueError:
            pass
    return text


# ── receive thread ────────────────────────────────────────────────────────────

_stop_event = threading.Event()


def receive_loop(sock: socket.socket) -> None:
    while not _stop_event.is_set():
        try:
            data = sock.recv(BUFFER_SIZE)
        except OSError:
            break

        if not data:
            print(f"\n{C.RED}Disconnected from server.{C.RESET}")
            _stop_event.set()
            break

        text = data.decode("utf-8")
        # Print without an extra newline (server already adds \n)
        sys.stdout.write(colorize(text))
        sys.stdout.flush()


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Group-chat terminal client")
    p.add_argument("--host", default="", help="Server IP (prompted if omitted)")
    p.add_argument("--port", type=int, default=0, help="Server port (prompted if omitted)")
    p.add_argument("--name", default="", help="Your display name (prompted if omitted)")
    return p.parse_args()


def prompt(label: str, default: str) -> str:
    display = f"{label} [{default}]: " if default else f"{label}: "
    val = input(display).strip()
    return val or default


def main() -> None:
    args = parse_args()

    print(f"{C.CYAN}{C.BOLD}")
    print("  ╔══════════════════════════════╗")
    print("  ║      Group Chat Client       ║")
    print("  ╚══════════════════════════════╝")
    print(f"{C.RESET}")

    host = args.host or prompt("Server IP", "127.0.0.1")
    port = args.port or int(prompt("Server port", "6000") or "6000")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"{C.RED}Could not connect to {host}:{port}. Is the server running?{C.RESET}")
        sys.exit(1)
    except OSError as exc:
        print(f"{C.RED}Connection error: {exc}{C.RESET}")
        sys.exit(1)

    # Start receive thread
    t = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    t.start()

    # Send loop — the server will prompt for the name first
    try:
        while not _stop_event.is_set():
            try:
                line = input()
            except EOFError:
                break

            if _stop_event.is_set():
                break

            try:
                sock.sendall((line + "\n").encode("utf-8"))
            except OSError:
                print(f"{C.RED}Send failed — connection lost.{C.RESET}")
                break

            if line.strip().lower() in ("/quit", "/exit", "/q", "exit"):
                break

    except KeyboardInterrupt:
        try:
            sock.sendall("/quit\n".encode("utf-8"))
        except OSError:
            pass

    _stop_event.set()
    sock.close()
    print(f"{C.DIM}Client closed.{C.RESET}")


if __name__ == "__main__":
    main()
