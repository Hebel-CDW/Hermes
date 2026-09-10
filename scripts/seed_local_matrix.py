"""Build local SQLite matrix + JSON samples from pilot fixtures."""

from __future__ import annotations

from pathlib import Path

from scripts.ingest_fixtures import ingest


def main() -> None:
    report = ingest(
        Path("data/fixtures/pilot_population.json"),
        Path("data/hermes.db"),
    )
    print(f"wrote {report['skills_scored']} skill records to {report['db_path']}")


if __name__ == "__main__":
    main()
