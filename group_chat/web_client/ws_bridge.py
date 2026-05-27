"""
group_chat/web_client/ws_bridge.py
WebSocket ↔ TCP bridge.

Browsers connect to this bridge via WebSocket (default ws://localhost:8765).
The bridge connects to the group-chat TCP server on your behalf.

Usage:
    pip install websockets
    python ws_bridge.py                        # default tcp=127.0.0.1:6000, ws=8765
    python ws_bridge.py --tcp-host 10.0.0.5 --tcp-port 6000 --ws-port 8765
"""

import argparse
import asyncio
import socket
import sys

try:
    import websockets
    from websockets.server import serve, ServerConnection
except ImportError:
    print("Missing dependency: pip install websockets")
    sys.exit(1)

TCP_HOST = "127.0.0.1"
TCP_PORT = 6000
WS_PORT  = 8765
BUFFER   = 4096


async def handle_ws(websocket: ServerConnection, tcp_host: str, tcp_port: int) -> None:
    """One WebSocket client ↔ one TCP connection to the chat server."""
    loop = asyncio.get_event_loop()

    # Open a raw TCP connection to the chat server
    try:
        reader, writer = await asyncio.open_connection(tcp_host, tcp_port)
    except OSError as exc:
        await websocket.send(f"ERROR: Cannot reach chat server at {tcp_host}:{tcp_port} — {exc}")
        return

    print(f"[bridge] WS client {websocket.remote_address} connected → TCP {tcp_host}:{tcp_port}")

    async def tcp_to_ws() -> None:
        """Forward bytes from TCP server → WebSocket client."""
        try:
            while True:
                data = await reader.read(BUFFER)
                if not data:
                    break
                await websocket.send(data.decode("utf-8", errors="replace"))
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass
        finally:
            writer.close()

    async def ws_to_tcp() -> None:
        """Forward messages from WebSocket client → TCP server."""
        try:
            async for message in websocket:
                writer.write((message + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass
        finally:
            writer.close()

    t1 = asyncio.create_task(tcp_to_ws())
    t2 = asyncio.create_task(ws_to_tcp())
    done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    print(f"[bridge] WS client {websocket.remote_address} disconnected")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WebSocket ↔ TCP bridge for the group chat")
    p.add_argument("--tcp-host", default=TCP_HOST, help=f"Chat server host (default {TCP_HOST})")
    p.add_argument("--tcp-port", type=int, default=TCP_PORT, help=f"Chat server port (default {TCP_PORT})")
    p.add_argument("--ws-port",  type=int, default=WS_PORT,  help=f"WebSocket listen port (default {WS_PORT})")
    return p.parse_args()


async def run(tcp_host: str, tcp_port: int, ws_port: int) -> None:
    handler = lambda ws: handle_ws(ws, tcp_host, tcp_port)
    print("=" * 50)
    print("  Group Chat WebSocket Bridge")
    print(f"  TCP server : {tcp_host}:{tcp_port}")
    print(f"  WS listen  : ws://localhost:{ws_port}")
    print("  Open web_client/index.html in your browser")
    print("  Ctrl-C to stop")
    print("=" * 50)
    async with serve(handler, "0.0.0.0", ws_port):
        await asyncio.Future()  # run forever


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args.tcp_host, args.tcp_port, args.ws_port))
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
