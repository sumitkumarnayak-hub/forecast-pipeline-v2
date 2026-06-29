#!/usr/bin/env python3
"""
CLI entry point for the Optimized Baseline Auto-Pilot.

Run from the repository root (recommended for task schedulers):

    python scripts/run_optimized_autopilot.py

See also: planning_suite.automation.optimized_autopilot
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from planning_suite.automation.optimized_autopilot import main

if __name__ == "__main__":
    raise SystemExit(main())
