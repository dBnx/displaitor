#!/usr/bin/env python3
"""Picture viewer; also available through tools/run.py pictures."""
if __package__:
    from .displaitor_tools.apps.pictures import main
else:
    from displaitor_tools.apps.pictures import main

if __name__ == '__main__':
    main()
