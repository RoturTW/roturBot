#!/usr/bin/env python3
"""
Main entry point for the roturbot Discord bot.
This script adds the parent directories to the Python path and runs the bot.
"""

import sys
import os

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
grandparent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, grandparent_dir)

if __name__ == "__main__":
    from roturbot.init import run
    run()
