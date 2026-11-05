"""Start the fixed original-event QA transport using the official MCP SDK."""
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from intent_replay.qa_room_mcp import main


if __name__ == "__main__":
    raise SystemExit(main())
