import os
from pathlib import Path


def load_env_file(env_path: Path | None = None) -> None:
    """
    Loads key=value pairs from a .env file into os.environ if not already set.
    Searches current and parent directories for .env if env_path is omitted.
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if env_path is None:
        current = Path(__file__).resolve().parent
        for _ in range(5):
            candidate = current / ".env"
            if candidate.is_file():
                env_path = candidate
                break
            current = current.parent

    if env_path and env_path.is_file():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass
