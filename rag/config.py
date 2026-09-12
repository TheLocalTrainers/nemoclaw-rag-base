"""Single entry point for configuration.

Reads `nemoclaw-rag.toml` (the committed source of truth), then applies
environment-variable overrides. CLI flags override both, because each CLI
passes the resolved config value as its argparse default.

Precedence: CLI flag > environment variable > nemoclaw-rag.toml > dataclass default.

This module deliberately does NOT load `.env`. CLI entrypoints call
`rag.env.load_dotenv()` first so that env loading happens exactly once, at a
place the caller controls (keeps library behaviour and tests deterministic).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "nemoclaw-rag.toml"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_toml_cache: dict[tuple[Path, int], dict] = {}


@dataclass(frozen=True)
class ProjectConfig:
    name: str = "nemoclaw-rag-base"
    smoke_token: str = "NEON-BEACON-42"
    smoke_question: str = "What is the project beacon code?"


@dataclass(frozen=True)
class MongoConfig:
    uri: str = "mongodb://127.0.0.1:27017"
    database: str = "nemoclaw_rag"
    collection: str = "chunks"
    smoke_database: str = "nemoclaw_rag_smoke"
    smoke_collection: str = "chunks"
    server_selection_timeout_ms: int = 5000
    port: int = 27017
    docker_image: str = "mongo:7"
    local_version: str = "7.0.39"


@dataclass(frozen=True)
class CareClawConfig:
    """Operational store for patient records, intake cases, and the event log.

    Shares the Mongo instance with the RAG corpus (see MongoConfig.uri) but uses
    a dedicated database so the corpus `chunks` collection is never touched.
    """

    database: str = "careclaw"
    patients_collection: str = "patients"
    cases_collection: str = "cases"
    events_collection: str = "events"
    care_team_collection: str = "care_team"


@dataclass(frozen=True)
class CorpusConfig:
    dir: str = "corpus"
    extensions: tuple[str, ...] = (".md", ".txt")


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 900
    overlap: int = 120


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int = 3
    regex_fallback: bool = True
    min_token_length: int = 2


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    temperature: float = 0.0
    timeout_seconds: int = 60
    api_key_env: str = "OPENAI_API_KEY"

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()


@dataclass(frozen=True)
class AgentConfig:
    harness: str = "hermes"
    sandbox_name: str = "nemoclaw-rag-base"
    nemoclaw_provider: str = "openai-api"


@dataclass(frozen=True)
class Config:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    mongodb: MongoConfig = field(default_factory=MongoConfig)
    careclaw: CareClawConfig = field(default_factory=CareClawConfig)
    corpus: CorpusConfig = field(default_factory=CorpusConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    source_path: Path | None = None


def find_config_file(explicit: Path | str | None = None) -> Path | None:
    """Locate nemoclaw-rag.toml: explicit path, then env, then cwd, then repo root."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_path = os.getenv("NEMOCLAW_RAG_CONFIG", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path.cwd() / CONFIG_FILENAME)
    candidates.append(_REPO_ROOT / CONFIG_FILENAME)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_toml(path: Path) -> dict:
    key = (path.resolve(), path.stat().st_mtime_ns)
    cached = _toml_cache.get(key)
    if cached is None:
        with path.open("rb") as handle:
            cached = tomllib.load(handle)
        _toml_cache[key] = cached
    return cached


def _pick_str(table: dict, key: str, env: str, fallback: str) -> str:
    from_env = os.getenv(env, "").strip()
    if from_env:
        return from_env
    value = table.get(key, fallback)
    return str(value)


def _pick_int(table: dict, key: str, env: str, fallback: int) -> int:
    from_env = os.getenv(env, "").strip()
    if from_env:
        try:
            return int(from_env)
        except ValueError as exc:
            raise ValueError(f"{env} must be an integer, got {from_env!r}") from exc
    value = table.get(key, fallback)
    return int(value)


def _pick_float(table: dict, key: str, env: str, fallback: float) -> float:
    from_env = os.getenv(env, "").strip()
    if from_env:
        try:
            return float(from_env)
        except ValueError as exc:
            raise ValueError(f"{env} must be a number, got {from_env!r}") from exc
    value = table.get(key, fallback)
    return float(value)


def _pick_bool(table: dict, key: str, env: str, fallback: bool) -> bool:
    from_env = os.getenv(env, "").strip().lower()
    if from_env:
        if from_env in {"1", "true", "yes", "on"}:
            return True
        if from_env in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{env} must be a boolean-like value, got {from_env!r}")
    return bool(table.get(key, fallback))


def load_config(*, path: Path | str | None = None) -> Config:
    """Build a Config from nemoclaw-rag.toml plus environment overrides."""
    config_path = find_config_file(path)
    data: dict = _read_toml(config_path) if config_path is not None else {}

    project_tbl = data.get("project", {})
    mongo_tbl = data.get("mongodb", {})
    careclaw_tbl = data.get("careclaw", {})
    corpus_tbl = data.get("corpus", {})
    chunk_tbl = data.get("chunking", {})
    retrieval_tbl = data.get("retrieval", {})
    model_tbl = data.get("model", {})
    agent_tbl = data.get("agent", {})

    defaults = Config()

    extensions_raw = corpus_tbl.get("extensions", list(defaults.corpus.extensions))
    extensions = tuple(str(ext).lower() for ext in extensions_raw)

    return Config(
        project=ProjectConfig(
            name=str(project_tbl.get("name", defaults.project.name)),
            smoke_token=str(project_tbl.get("smoke_token", defaults.project.smoke_token)),
            smoke_question=str(
                project_tbl.get("smoke_question", defaults.project.smoke_question)
            ),
        ),
        mongodb=MongoConfig(
            uri=_pick_str(mongo_tbl, "uri", "MONGODB_URI", defaults.mongodb.uri),
            database=_pick_str(mongo_tbl, "database", "MONGODB_DB", defaults.mongodb.database),
            collection=_pick_str(
                mongo_tbl, "collection", "MONGODB_COLLECTION", defaults.mongodb.collection
            ),
            smoke_database=_pick_str(
                mongo_tbl, "smoke_database", "MONGODB_SMOKE_DB", defaults.mongodb.smoke_database
            ),
            smoke_collection=_pick_str(
                mongo_tbl,
                "smoke_collection",
                "MONGODB_SMOKE_COLLECTION",
                defaults.mongodb.smoke_collection,
            ),
            server_selection_timeout_ms=_pick_int(
                mongo_tbl,
                "server_selection_timeout_ms",
                "MONGODB_TIMEOUT_MS",
                defaults.mongodb.server_selection_timeout_ms,
            ),
            port=_pick_int(mongo_tbl, "port", "MONGODB_PORT", defaults.mongodb.port),
            docker_image=_pick_str(
                mongo_tbl, "docker_image", "MONGODB_IMAGE", defaults.mongodb.docker_image
            ),
            local_version=_pick_str(
                mongo_tbl,
                "local_version",
                "MONGODB_LOCAL_VERSION",
                defaults.mongodb.local_version,
            ),
        ),
        careclaw=CareClawConfig(
            database=_pick_str(
                careclaw_tbl, "database", "CARECLAW_DB", defaults.careclaw.database
            ),
            patients_collection=_pick_str(
                careclaw_tbl,
                "patients_collection",
                "CARECLAW_PATIENTS",
                defaults.careclaw.patients_collection,
            ),
            cases_collection=_pick_str(
                careclaw_tbl, "cases_collection", "CARECLAW_CASES", defaults.careclaw.cases_collection
            ),
            events_collection=_pick_str(
                careclaw_tbl,
                "events_collection",
                "CARECLAW_EVENTS",
                defaults.careclaw.events_collection,
            ),
            care_team_collection=_pick_str(
                careclaw_tbl,
                "care_team_collection",
                "CARECLAW_CARE_TEAM",
                defaults.careclaw.care_team_collection,
            ),
        ),
        corpus=CorpusConfig(
            dir=_pick_str(corpus_tbl, "dir", "RAG_CORPUS_DIR", defaults.corpus.dir),
            extensions=extensions or defaults.corpus.extensions,
        ),
        chunking=ChunkingConfig(
            max_chars=_pick_int(
                chunk_tbl, "max_chars", "RAG_CHUNK_MAX_CHARS", defaults.chunking.max_chars
            ),
            overlap=_pick_int(
                chunk_tbl, "overlap", "RAG_CHUNK_OVERLAP", defaults.chunking.overlap
            ),
        ),
        retrieval=RetrievalConfig(
            top_k=_pick_int(retrieval_tbl, "top_k", "RAG_TOP_K", defaults.retrieval.top_k),
            regex_fallback=_pick_bool(
                retrieval_tbl,
                "regex_fallback",
                "RAG_REGEX_FALLBACK",
                defaults.retrieval.regex_fallback,
            ),
            min_token_length=_pick_int(
                retrieval_tbl,
                "min_token_length",
                "RAG_MIN_TOKEN_LENGTH",
                defaults.retrieval.min_token_length,
            ),
        ),
        model=ModelConfig(
            base_url=_pick_str(
                model_tbl, "base_url", "OPENAI_BASE_URL", defaults.model.base_url
            ).rstrip("/"),
            model=_pick_str(model_tbl, "model", "OPENAI_MODEL", defaults.model.model),
            temperature=_pick_float(
                model_tbl, "temperature", "OPENAI_TEMPERATURE", defaults.model.temperature
            ),
            timeout_seconds=_pick_int(
                model_tbl, "timeout_seconds", "OPENAI_TIMEOUT_SECONDS", defaults.model.timeout_seconds
            ),
            api_key_env=str(model_tbl.get("api_key_env", defaults.model.api_key_env)),
        ),
        agent=AgentConfig(
            harness=_pick_str(agent_tbl, "harness", "NEMOCLAW_AGENT", defaults.agent.harness),
            sandbox_name=_pick_str(
                agent_tbl, "sandbox_name", "NEMOCLAW_SANDBOX_NAME", defaults.agent.sandbox_name
            ),
            nemoclaw_provider=_pick_str(
                agent_tbl,
                "nemoclaw_provider",
                "NEMOCLAW_PROVIDER",
                defaults.agent.nemoclaw_provider,
            ),
        ),
        source_path=config_path,
    )
