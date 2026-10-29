# Games for the 64×32 panel

The controls suit games with immediate spatial feedback: a left d-pad and one
right action button. Reserve B for the existing local menu and Select for mute.
Use icons and animation during play, with scores on a separate end screen; small
text, inventories and simultaneous multi-button combinations waste this panel.
These are proposals, not implemented games.

| Priority | Game | D-pad | A | What gives it depth |
| --- | --- | --- | --- | --- |
| 1 | Brick garden | Left/right moves the paddle; Up/Down aims before launch | Serve; hold to charge a limited sticky catch | Angled rebounds, several brick types, short patterned stages, three lives, earned power-ups |
| 2 | Tiny warehouse (Sokoban) | Step on a roughly 12×6 tile board; walking pushes crates | Undo the last move | Hand-built puzzles, unlimited undo, clear goals, progressively introduced mechanics; no reaction-time pressure |
| 3 | Cavern flight | Fly in four directions through a scrolling cavern | Fire a short burst | Readable enemy patterns, destructible gates, rescue pickups, small boss encounters, shields and checkpoints |
| 4 | Pocket angler | Left/right chooses a spot; Up/Down controls line tension | Cast/hook; hold to reel | Fish silhouettes, a visible tension bar, changing fish behaviour and a tiny collection; a cozy companion to Watch |
| 5 | One-button platformer | Left/right walks, Down drops through ledges | Jump, with press duration controlling height | Moving platforms, switches, short checkpointed rooms; use a side view with large silhouettes |
| 6 | Bomb garden | Move between cells | Place a bomb | Timed blast patterns, destructible walls, simple enemies and escape planning; clear blast warnings on the small grid |

Start with **Brick garden** for immediate arcade appeal and **Tiny warehouse**
for a slower game that uses all four directions well. **Cavern flight** is the
strongest action follow-up once movement and collision feel responsive.

## Improve the current games

Pong currently uses a fixed diagonal ball trajectory, a half-speed AI paddle,
automatic serves and a score counter. Make rebound angle depend on impact
position and paddle motion; use A to serve/activate an earned brief paddle boost;
add a visible best-of-five match and a gradual, capped speed increase. Preserve
reachable AI returns rather than making the opponent perfectly track the ball.

Snake already prevents impossible reversals and has bounded storage. Make it a
short set of readable stages: a starting countdown, deliberate wall layouts,
more than one food behaviour, a speed curve and a clear win/death/restart state.
A can pause during play and restart after a loss. Do not add an extra action
that requires taking the thumb off steering at exactly the wrong moment.

## Implementation direction

Prototype new games in typed Python 3.12+ using `run_scene` and the existing
button reports. Keep fixed-step simulation separate from rendering; consume each
press once, cap catch-up after stalls and use held input for continuous movement.
Use a bounded board/entity list and a deterministic seed for repeatable levels.
Account for host USB round-trip time before claiming arcade responsiveness;
the firmware's direct input path remains preferable if measurements show delay.

Share the approved gamma 2.8 output path, avoid full-screen flashing, and keep
characters at least a few pixels wide. Add idle attract scenes and a concise
control hint before the first level. Save unlocks only if persistent storage is
explicitly introduced; do not imply scores survive a power cycle today.
