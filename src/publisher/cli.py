from __future__ import annotations

from .pipeline import PUBLISH_PATH, prepare_data_artifacts
from .publish import run_publisher_loop


def main() -> None:
    if not PUBLISH_PATH.exists():
        prepare_data_artifacts()
    run_publisher_loop(PUBLISH_PATH)


if __name__ == "__main__":
    main()
