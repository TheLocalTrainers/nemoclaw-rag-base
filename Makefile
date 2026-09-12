.PHONY: smoke ingest query test config venv mongo-up mongo-down mongo-logs onboard onboard-help

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
