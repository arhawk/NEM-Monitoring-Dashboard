from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "Task4_appStreamlit.py"
    repo_root = target.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    runpy.run_path(str(target), run_name="__main__")
