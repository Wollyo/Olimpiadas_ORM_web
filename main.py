"""Punto de entrada conveniente para iniciar la aplicación web."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    dashboard = Path(__file__).resolve().parent / "scripts" / "streamlit_dashboard.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(dashboard)],
        check=True,
    )

if __name__ == "__main__":
    main()
