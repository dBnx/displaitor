# Canvas button hardware validation scope

Normal firmware was tested through the native USB Canvas interface. The test
covered inactive/active baselines, stable polling, future-cursor resynchronizing,
invalid payload rejection and readback inside a scene transaction. These checks
passed without consuming or changing drawing state.

A physical trial captured 46 consecutive button events without cursor loss.
Left/Right switched pets, A triggered the action, and Back returned to the local
menu. Re-entering Canvas did not accidentally trigger another pet action.
The host preserves Back priority and keeps normal redraws from reopening Canvas.

A reported moving floor was repaired in the host renderer: hopping moves only
actor geometry. Tests check fixed floor/background pixels across all poses.
Subsequent palette changes darken Ember/Sprout body areas while preserving their
small details. Their final optical contrast has not yet been separately confirmed.

The public API and bounded wire format are documented in
[Canvas buttons](CANVAS-BUTTONS.md). Local button-event logs, probe identifiers,
compiled firmware and private scroller input are excluded from this repository.
