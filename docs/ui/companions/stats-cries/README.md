# Stats and cries preview

Offline export of the live companion: Up/Down select CPU, RAM, GPU, used VRAM
and ALL. Left/Right retain pet selection; A runs the existing trick and a short
original GBA-inspired cry for Torchic, Eevee or Treecko.

- [All fifteen pet/page combinations](stats-gallery.png)
- [Animated page cycle](stats-cycle.gif)
- [All three tricks, silent GIF](pet-actions.gif)
- [Video with each cry separately](pet-cries.mp4)
- WAV auditions: [Torchic](cry_torchic.wav), [Eevee](cry_eevee.wav), [Treecko](cry_treecko.wav)

Readings are samples: CPU 7%, RAM 64%, GPU 35%, used VRAM 3.2 GiB. DEMO labels
remain visible in the rendered HUD (in the header for ALL, otherwise the footer).
The real application defaults to actual telemetry with full pet names.

The text boxes come from the real Rust Canvas renderer over temporary loopback
TCP connections. Sprite pixels are the same RGB565 frames sent by the host app,
enlarged without smoothing. The video uses decoded copies of the exact QOA
firmware assets. GIF timing uses the format's 10 ms resolution and merges
identical adjacent frames. These are software previews, not panel recordings.

Regenerate with `tools/preview_companion_stats.py`; see
[the companion guide](../../../PIXEL-COMPANION.md#preview-and-demo-modes) and
[the sound sources](../../../../assets/audio/CRIES.md).
