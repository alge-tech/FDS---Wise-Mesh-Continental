"""Command line: `python -m app.cli seed | seed-if-empty | reset | openapi [path]`."""

import json
import sys

from sqlalchemy.orm import Session

import app.models  # noqa: F401  registers every table


def _seed(only_if_empty: bool) -> None:
    from app.core.db import session_factory
    from app.modules.demo.seed import is_seeded, seed

    with session_factory()() as session, session.begin():
        if only_if_empty and is_seeded(session):
            print("seed: database already seeded")
            return
        seed(session)
    print("seed: done")


def _reset() -> None:
    from sqlalchemy import create_engine

    from app.core.config import get_settings
    from app.modules.demo.seed import truncate_all

    owner = create_engine(get_settings().migration_database_url)
    with Session(owner) as s, s.begin():
        truncate_all(s)
    owner.dispose()
    _seed(only_if_empty=False)


def _openapi(path: str | None) -> None:
    from app.main import create_app

    schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if path:
        with open(path, "w") as f:
            f.write(schema)
    else:
        sys.stdout.write(schema)


def main(argv: list[str]) -> None:
    command = argv[1] if len(argv) > 1 else ""
    if command == "seed":
        _seed(only_if_empty=False)
    elif command == "seed-if-empty":
        _seed(only_if_empty=True)
    elif command == "reset":
        _reset()
    elif command == "openapi":
        _openapi(argv[2] if len(argv) > 2 else None)
    else:
        sys.exit("usage: python -m app.cli seed | seed-if-empty | reset | openapi [path]")


if __name__ == "__main__":
    main(sys.argv)
