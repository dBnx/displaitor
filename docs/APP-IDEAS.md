# App ideas

These are candidates, except Pixel Companion, which now has a runnable
[CPU/GPU-driven sender and six characters](PIXEL-COMPANION.md). Standalone apps are useful while
native USB is unavailable; Canvas ideas can first run against the simulator.
Use black behind text, sparse bright pixels and dim supporting details. Keep B
as Back and Select as mute. Every animation needs fixed storage and bounded work.

| Idea | Experience on 64×32 | Runs where |
| --- | --- | --- |
| **Hourglass** | A focus timer pours luminous grains between two chambers. A starts/pauses; Up/Down sets minutes. Sand follows elapsed time, so a slow frame cannot extend the timer. | Standalone firmware |
| **Orbit Rescue** | A tiny lander navigates gravity, fuel and landing pads. Left/Right adjusts thrust; A boosts. A few bright particles show motion against black. | Standalone firmware |
| **Pixel Aquarium** | A small school of fish follows simple local rules. Up/Down changes the current; A drops food. Fixed fish/food counts keep updates predictable. | Standalone firmware |
| **Pixel Companion** | An animated creature reacts to CPU/GPU activity: relaxed at idle, working hard under load. Compact text can show what the PC is doing. | PC helper over Canvas |
| **Build Beacon** | A launch-pad animation shows a running build, launches on success, and retains a small failure indicator until the next run. Use actual completion events rather than invented progress percentages. | PC helper over Canvas |
| **Music Skyline** | A dark city skyline responds to audio levels, with short-lived peak markers. The PC computes levels or frequency bins and sends the rendered background. | PC helper over Canvas |

**Hourglass** would be an independent, useful device app. Use a monotonic
timer, a fixed grain pool and an aggregate count for sand already settled.
It needs no wall-clock setting, network service or PC connection.

For the next Canvas experiment, **Build Beacon** is a small useful step: accept
start/success/failure events from a local build wrapper and retain the last result.
The existing eight text slots and streamed background are sufficient; it needs
no new firmware application or protocol commands. A stopped sender leaves a
snapshot, so a dim activity indicator should distinguish live updates.
