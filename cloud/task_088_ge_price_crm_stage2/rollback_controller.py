#!/usr/bin/env python3
"""Restore only the exact approved Stage 2 installation backup."""
import os
import controller

if __name__ == "__main__":
    controller.rollback(os.environ)
