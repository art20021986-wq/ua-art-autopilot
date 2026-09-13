#!/usr/bin/env python3
"""Exact installation-only backup entrypoint; no Stage 1 execution."""
import os
import controller

if __name__ == "__main__":
    controller.backup(os.environ)
