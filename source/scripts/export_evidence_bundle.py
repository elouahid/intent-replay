"""Export one existing execution report; no replay or provider request."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intent_replay.evidence_handoff import main

if __name__ == '__main__':
    raise SystemExit(main())
