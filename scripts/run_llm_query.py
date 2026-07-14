from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print(
            'Usage: python scripts/run_llm_query.py "Your question here"',
            file=sys.stderr,
        )
        return 1

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from src.shared.dotenv import load_dotenv_from_repo

    load_dotenv_from_repo(repo_root / ".env")

    from datetime import datetime, timezone

    from src.llm.audit import write_audit_log
    from src.llm.pipeline import format_query_output, run_llm_query
    from src.shared.config import get_llm_audit_dir

    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print("Question must not be empty.", file=sys.stderr)
        return 1

    try:
        query_result = run_llm_query(question)
        print(format_query_output(query_result))
        return 0
    except Exception as exc:
        audit_path = write_audit_log(
            {
                "question": question,
                "status": "error",
                "error": str(exc),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            get_llm_audit_dir(),
        )
        print(f"Error: {exc}", file=sys.stderr)
        print(f"Audit log: {audit_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
