# Pokémon icon inputs

Native-resolution icon inputs from [PokéAPI/sprites](https://github.com/PokeAPI/sprites),
pinned at commit `97a7832d307311c0e1c6ea9035308bf80cc94f81`.
Exact URLs and SHA-256 digests are in [sources.json](sources.json).

The upstream [LICENCE.txt](https://github.com/PokeAPI/sprites/blob/97a7832d307311c0e1c6ea9035308bf80cc94f81/LICENCE.txt)
attributes the image contents to The Pokémon Company and separately describes
the repository's CC0 distribution. This attribution is retained for these inputs.

`tools/run.py preview play` crops the transparent margins without scaling the icons,
preserves source RGB intensity, separates Cubone's held bone, mirrors
Torchic to face its toy, and adds project-authored poses, props and animation
timelines. The pixel bases are source assets, not newly drawn character artwork.
No runtime download is required.
