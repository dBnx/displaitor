# Native USB Canvas hardware validation scope

Tests used the board's own USB data connection, not the debug probe UART.
Canvas protocol uploads, background streaming, named text/styles, atomic scene
transactions and reconnect recovery passed. PC statistics and companion senders
were exercised over the same native USB interface.

[Animated weather](WEATHER.md) completed sustained acknowledged updates and
negative-temperature/snow trials without transport errors. Physical weather
appearance was subsequently confirmed. Readback button controls were also
physically exercised; see [button validation](HARDWARE-CANVAS-BUTTONS.md).

Hardware evidence applies to the qualified runtime with local scroller content;
the neutral public sample is independently build/test verified. USB ACKs prove
protocol acceptance, not every physical pixel or optical contrast. No transport
logs, device-specific identifiers or private content are included here.
