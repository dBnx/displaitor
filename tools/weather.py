#!/usr/bin/env python3
"""Compatibility entry point; new commands use tools/run.py weather."""
if __package__:
    from .displaitor_tools.apps.weather import Weather as Weather, main as main
else:
    from displaitor_tools.apps.weather import Weather as Weather, main as main

if __name__ == '__main__':
    main()
