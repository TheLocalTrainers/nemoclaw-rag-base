.PHONY: smoke ingest query test config venv mongo-up mongo-down mongo-logs onboard onboard-help web where seed mongo-reset show-db

# Host/port for the FastAPI PI Review Console.
#   Default host 0.0.0.0 binds all interfaces so the app is reachable over the LAN.
#   Override to bind localhost only:  make web WEB_HOST=127.0.0.1
#   Override the port:                make web WEB_PORT=8010
WEB_HOST ?= 0.0.0.0
WEB_PORT ?= 8010

# Prefer the project venv so targets work without activating it first.
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

smoke: mongo-up
	$(PYTHON) -m scripts.smoke_test

ingest: mongo-up
	$(PYTHON) -m scripts.ingest

query: mongo-up
	@test -n "$(Q)" || (echo 'Usage: make query Q="your question"' && exit 1)
	$(PYTHON) -m scripts.query "$(Q)"

# Resolved config (nemoclaw-rag.toml + .env + env vars). Start here when debugging.
config:
	$(PYTHON) -m scripts.show_config

test: mongo-up
	$(PYTHON) -m unittest discover -s tests -v

mongo-up:
	@chmod +x scripts/start-mongo.sh
	@./scripts/start-mongo.sh

mongo-down:
	@if docker info >/dev/null 2>&1; then docker compose down; fi
	@pkill -f '.tools/mongodb/bin/mongod --dbpath' >/dev/null 2>&1 || true
	@echo "MongoDB stop attempted"

mongo-logs:
	@if [ -f .rag/mongod.log ]; then tail -n 100 .rag/mongod.log; else docker compose logs --tail=100 mongo; fi

venv:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e .

onboard:
	@chmod +x scripts/onboard.sh
	@./scripts/onboard.sh

onboard-help:
	@sed -n '1,140p' docs/onboarding.md

# Seed the demo into MongoDB (careclaw db): 1 PT-004 patient + 1 pending case + events.
seed: mongo-up
	$(PYTHON) -m scripts.seed_demo

# Read-only tour of the MongoDB setup (dbs, collections, counts, indexes, sample docs).
show-db: mongo-up
	$(PYTHON) -m scripts.show_db

# Clear ONLY the careclaw operational collections (patients/cases/events); leaves the RAG corpus.
mongo-reset: mongo-up
	$(PYTHON) -c "from store.careclaw_store import CareClawStore; s=CareClawStore(); s.reset_demo(); print('careclaw collections cleared')"

# Light-mode PI Review Console (FastAPI) — reads/writes MongoDB (careclaw db) as source of truth.
# Binds 0.0.0.0 by default so it is reachable over the LAN (see docs/NETWORK_ACCESS.md).
web:
	@echo "PI Review Console (binding $(WEB_HOST):$(WEB_PORT))"
	@echo "  local:   http://127.0.0.1:$(WEB_PORT)"
	@LAN_IPS="$$(hostname -I 2>/dev/null)"; \
	if [ -z "$$LAN_IPS" ]; then LAN_IPS="$$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p')"; fi; \
	if [ "$(WEB_HOST)" = "0.0.0.0" ] && [ -n "$$LAN_IPS" ]; then \
	  for ip in $$LAN_IPS; do echo "  network: http://$$ip:$(WEB_PORT)"; done; \
	fi; \
	echo "  (0.0.0.0 exposes this app with NO auth — trusted networks only; see docs/NETWORK_ACCESS.md)"
	$(PYTHON) -m uvicorn web.server:app --host $(WEB_HOST) --port $(WEB_PORT)

# Print the URLs this machine is reachable at for the web console (no server started).
where:
	@$(PYTHON) scripts/whereami.py $(WEB_PORT)
