# Mystery Dungeon companion inputs

Torchic, Eevee and Treecko use native-resolution Mystery Dungeon game sprite
poses, with Red Rescue Team as the visual reference. The six unmodified input
sheets come from [PMDCollab/SpriteCollab](https://github.com/PMDCollab/SpriteCollab)
at revision `3e0866e340c1dc136e5a143a78d22b45d988224a`.
[sources.json](sources.json) records each exact URL, SHA-256 digest, cell size,
original timing and direction order. No download occurs at runtime.

The upstream credit logs attribute all imported Idle/Walk animations to
**CHUNSOFT**. Pokémon and the original game art belong to their respective
rights holders, including Nintendo, Game Freak and The Pokémon Company. These
are derived game sprites, not newly drawn character bases. SpriteCollab's
[use policy](https://github.com/PMDCollab/SpriteCollab/blob/3e0866e340c1dc136e5a143a78d22b45d988224a/README.md#submission-and-use-policy)
describes noncommercial reuse with attribution for contributed art; it does not
transfer ownership of original game sprites or place them under this project's
software license.

`companion_pokemon.py` crops each sequence with a shared bound, dims broad colour
areas for the LED matrix, preserves small eye highlights, and adds local props
and timelines: Torchic's seed and ember sneeze, Eevee's leaf pounce, and Treecko's
small hands, wrist roll and single-turn twig toss/catch. The original pixels are
never interpolated. Inputs are loaded once into a bounded pose cache and are
used only by the host Python app.
