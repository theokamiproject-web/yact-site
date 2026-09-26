#!/usr/bin/env python3
"""インストールせずに使う場合の起動口: python podcast.py episode.wav"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from podcast_tool.cli import main  # noqa: E402

sys.exit(main())
