#!/usr/bin/env python3
"""Standalone cozy scenes; also available through tools/run.py cozy."""
if __package__:
    from .displaitor_tools.apps.cozy import main
else:
    from displaitor_tools.apps.cozy import main

if __name__ == '__main__':
    main()
