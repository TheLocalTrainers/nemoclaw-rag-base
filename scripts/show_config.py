"""Print the effective configuration (TOML + env overrides) for debugging/handoff."""

from __future__ import annotations

import argparse
import dataclasses
import json

from rag.config import load_config
from rag.env import load_dotenv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--no-env", action="store_true", help="Skip loading .env")
    args = parser.parse_args(argv)

    dotenv_path = None if args.no_env else load_dotenv()
    config = load_config()

    data = dataclasses.asdict(config)
    data["source_path"] = str(config.source_path) if config.source_path else None
    data["dotenv_path"] = str(dotenv_path) if dotenv_path else None
    data["model"]["api_key_present"] = bool(config.model.api_key)

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True, default=str))
        return 0

    print(f"config file : {data['source_path'] or '(none — using code defaults)'}")
    print(f".env loaded : {data['dotenv_path'] or '(none)'}")
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        print(f"\n[{section}]")
        for key, value in sorted(values.items()):
            print(f"  {key} = {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
