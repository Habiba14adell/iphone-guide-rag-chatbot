"""Run local ingestion directly from the repository root."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iphone_guide_chatbot.ingestion.pipeline import main


if __name__ == "__main__":
    main()
