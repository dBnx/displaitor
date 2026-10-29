#!/usr/bin/env python3
"""Compatibility entry point; use tools/run.py canvas for the unified CLI."""
if __package__:
    from .displaitor_tools.canvas import (
        ButtonEvent, ButtonState, Client, Layout, color565, image_frame, main,
    )
else:
    from displaitor_tools.canvas import (
        ButtonEvent, ButtonState, Client, Layout, color565, image_frame, main,
    )

if __name__ == '__main__':
    main()
