# Network Access — reaching the CareClaw web console over the LAN

The PI Review Console (`web/server.py`, served with uvicorn) can be reached from
other devices on the same network. Both the frontend and its JSON API are served
from the **same origin**, and the frontend calls the backend with relative paths
(`fetch("/api/...")`), so once the server is reached by IP everything works with
no code change and no CORS.

## Start it for the LAN

```bash
make web                 # binds 0.0.0.0:8010 (all interfaces)
```

`make web` prints the local and LAN URLs, e.g.:

```
PI Review Console (binding 0.0.0.0:8010)
  local:   http://127.0.0.1:8010
  network: http://10.50.22.99:8010
```

Open the `network:` URL from any device on the same network. To just print the
URLs without starting a server: `make where` (or `.venv/bin/python scripts/whereami.py`).

The local vLLM (`http://localhost:8000`) and MongoDB stay on this machine — only
the web console is exposed.

## ⚠️ Security — read before exposing

Binding `0.0.0.0` makes the console reachable by **anyone on the network**, and:

- **There is NO authentication.** Any device that can reach the port can view
  and modify the demo clinical data (it reads/writes the `careclaw` MongoDB
  database: cases, patients, events — including signing and dismissing cases).
- This is intended for **trusted-network / demo use only** (e.g. a hackathon LAN
  or a single controlled room). Do **not** expose it to untrusted networks or
  the public internet.

### How to restrict access

- **Bind localhost only** (no LAN exposure):

  ```bash
  make web WEB_HOST=127.0.0.1
  ```

  (or set `WEB_HOST=127.0.0.1` in the environment when running
  `python -m web.server`).

- **Firewall the port.** The host firewall may already block the port from other
  machines. Check and, if you deliberately want LAN access, allow it (run these
  yourself — they need sudo):

  ```bash
  sudo ufw status              # is the firewall active / is 8010 blocked?
  sudo ufw allow 8010/tcp      # allow LAN access to the console port
  sudo ufw delete allow 8010/tcp   # revoke it again afterwards
  ```

  If `ufw` is inactive the port is likely already open on the LAN; if it is
  active and you have not allowed 8010, other machines will be blocked even
  though uvicorn is bound to `0.0.0.0`.
