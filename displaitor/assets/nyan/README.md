# Nyan Cat palette

The twelve 64×32 QOI frames store logical RGB colours. The legacy imported
palette had dark midtones: body `#505050`, icing `#ff49ff`, pastry `#f69d50`
and sky `#030822`. Those values became too dark under the panel's gamma 2.8.

The restored palette uses grey `#999999`, pastel pink `#ff99ff`, pastry
`#ffcc99`, cheeks `#ff9999` and sky `#003366`, with clean rainbow bands.
Outlines, stars, all pixel positions and all twelve poses are preserved.
This is a semantic palette replacement, not an inverse gamma transform.

Gamma remains 2.8 at the firmware display boundary, applied once. Never store
panel drive values in these frames. Desktop previews show logical colours:
[animation](../../../docs/ui/nyan/animation.gif).

`tools/tests/test_nyan_assets.py` checks the palette and every pixel's semantic
role against the animation geometry captured before recolouring.
