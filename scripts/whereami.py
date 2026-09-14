#!/usr/bin/env python3
"""Print the URLs the CareClaw web console is reachable at on this machine.

Usage:  python scripts/whereami.py [PORT]   (default port 8010)

Shows the localhost URL plus any LAN IPs, so you know where to point a browser
on another device. This only prints URLs — it does not start a server.
"""

from __future__ import annotations

import socket
import subprocess
import sys


def lan_ips() -> list[str]:
    ips: list[str] = []
    try:
        out = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=3
        ).stdout.split()
        ips = [ip for ip in out if ip and not ip.startswith("127.")]
    except Exception:
        ips = []
    if not ips:
        # Fallback: the source IP the kernel would use to reach the internet.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("1.1.1.1", 80))
            ips = [s.getsockname()[0]]
            s.close()
        except Exception:
            ips = []
    return ips


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8010"
    print(f"CareClaw PI Review Console — reachable at (port {port}):")
    print(f"  local:   http://127.0.0.1:{port}")
    for ip in lan_ips():
        print(f"  network: http://{ip}:{port}")
    print(
        "\nNote: 0.0.0.0 binds all interfaces with NO authentication — trusted "
        "networks / demo only. See docs/NETWORK_ACCESS.md."
    )


if __name__ == "__main__":
    main()
