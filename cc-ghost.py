#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "anthropic",
#     "python-dotenv",
# ]
# ///
"""Thin wrapper for `uv run cc-ghost.py` compatibility."""
from cc_ghost import main

if __name__ == "__main__":
    main()
