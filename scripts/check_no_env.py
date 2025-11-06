#!/usr/bin/env python3
"""Fail the build if any plain `.env` files are present in the tree."""
from pathlib import Path
import sys

found = [str(p) for p in Path('.') .rglob('.env')]
if found:
    print("Detected .env files:")
    for item in found:
        print(f" - {item}")
    sys.exit(1)
print("No .env files detected")
