#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "campaigns"))
from render_compression_closeout import generate
generate(root, Path(__file__).resolve().parents[1].name)
