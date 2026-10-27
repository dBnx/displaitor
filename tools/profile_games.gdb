# Manual SWD diagnostic. Requires matching --features profiling firmware/ELF.
# Start probe-rs gdb first; see docs/VALIDATION.md. Never opens UART.
set pagination off
set confirm off
set print elements 140
set print max-depth 5
set mem inaccessible-by-default off
target extended-remote 127.0.0.1:1337
python
import gdb, hashlib, json, os, signal, struct, threading
from pathlib import Path

inferior = gdb.selected_inferior()
def read32(address):
    return struct.unpack('<I', inferior.read_memory(address, 4).tobytes())[0]
def write32(address, value):
    # RAM only: do not use byte-oriented GDB transfers for RP2040 MMIO writes.
    assert 0x20000000 <= address < 0x20042000
    inferior.write_memory(address, struct.pack('<I', value))
def symbol(name):
    with gdb.with_parameter('language', 'c'):
        return int(gdb.parse_and_eval("&'" + name + "'"))
def run_for(seconds):
    timer = threading.Timer(seconds, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        gdb.execute('continue', to_string=True)
    finally:
        timer.cancel()

kind = gdb.lookup_type('displaitor::engine::Engine<3>')
engine = None
frame = gdb.newest_frame()
while frame is not None and engine is None:
    for name in ('engine', 'self'):
        try:
            value = frame.read_var(name)
            if value.is_optimized_out:
                continue
            typ = value.type.strip_typedefs()
            if typ.code in (gdb.TYPE_CODE_PTR, gdb.TYPE_CODE_REF):
                if str(typ.target()) == str(kind):
                    engine = value.cast(kind.pointer())
                    break
            elif str(typ) == str(kind):
                engine = value.address.cast(kind.pointer())
                break
        except (gdb.error, ValueError):
            pass
    frame = frame.older()
if engine is None:
    # Embassy keeps the suspended main future in static task storage; it is
    # absent from the stack while the thread executor sleeps.
    root = 'aitos::board::____embassy_main_task::____embassy_main_task_inner_function::{async_fn_env#0}'
    def offset(typ, field):
        return next(f.bitpos // 8 for f in typ.fields() if f.name == field)
    storage = gdb.lookup_type('embassy_executor::raw::TaskStorage<' + root + '>')
    future = symbol('aitos::board::__embassy_main::POOL') + offset(storage, 'future')
    state = inferior.read_memory(future + offset(gdb.lookup_type(root), '__state'), 1).tobytes()[0]
    assert state == 3, 'Main future is not suspended/initialized; no RAM changes made'
    engine = gdb.Value(future + offset(gdb.lookup_type(root + '::Suspend0'), 'engine')).cast(kind.pointer())
assert engine is not None, 'Engine not available in DWARF; no RAM changes made'

# Framebuffer placement changes when code moves to RAM. Obtain each storage
# address from the matching ELF instead of assuming the start of SRAM.
framebuffer_addresses = []
for name in ('aitos::board::FB0', 'aitos::board::FB1'):
    with gdb.with_parameter('language', 'c'):
        value = gdb.parse_and_eval("'" + name + "'")
    field = next(f for f in value.type.fields() if f.name == 'val')
    framebuffer_addresses.append(int(value.address) + field.bitpos // 8)

input_address = symbol('GAME_INPUT')
capture_address = symbol('GAME_CAPTURE')
timings_address = symbol('GAME_TIMINGS')
apps = sorted(gdb.lookup_type('displaitor::engine::AppId').fields(), key=lambda field: field.enumval)
names = ['Splash', 'Home', 'Watch', 'Play'] + [field.name.rsplit('::', 1)[-1] for field in apps]
results = dict(engine_address=hex(int(engine)), timer_dbgpause=hex(read32(0x4005402c)),
               source='instrumented firmware; RAM synthetic controls through normal debounce', captures=[])
output = Path(os.environ.get('GAME_PROFILE_OUTPUT', 'target/game-profile.json'))
output.parent.mkdir(parents=True, exist_ok=True)
def screen():
    return str(engine.dereference()['screen'])
def tap(mask):
    write32(input_address, mask)
    run_for(.10)
    write32(input_address, 0)
    run_for(.10)
def snapshot():
    state = engine.dereference()
    return dict(screen=str(state['screen']), game=str(state['game']),
                framebuffer_hashes=[hashlib.sha256(inferior.read_memory(address, 12292).tobytes()).hexdigest()
                                    for address in framebuffer_addresses])
def capture(label, seconds):
    before = snapshot()
    write32(capture_address, int(seconds * 1_000_000))
    # Idle game-over has no periodic UI wakeup. These Up/release boundaries
    # start/finish the capture without restarting the game or toggling audio.
    idle = 'over: true' in str(engine.dereference()['game'])
    if idle:
        write32(input_address, 8)
        run_for(.05)
    run_for(seconds + .25)
    if idle:
        write32(input_address, 0)
        run_for(.05)
    request, start, finish = struct.unpack('<3I', inferior.read_memory(capture_address, 12).tobytes())
    if request == 0 and finish == 0 and 'over: true' in str(engine.dereference()['game']):
        # A game may stop autonomously during an initially moving capture.
        original = read32(input_address)
        write32(input_address, original ^ 8)
        run_for(.05)
        write32(input_address, original)
        run_for(.05)
        request, start, finish = struct.unpack('<3I', inferior.read_memory(capture_address, 12).tobytes())
    assert request == 0 and finish != 0, 'Capture did not finish; do not report partial metrics'
    duration = (finish - start) & 0xffffffff
    word_count = len(names) * 12
    words = struct.unpack(f'<{word_count}I', inferior.read_memory(timings_address, word_count * 4).tobytes())
    screens = {}
    for index, name in enumerate(names):
        counters = words[index * 12:(index + 1) * 12]
        if not any(counters):
            continue
        stages = {}
        for stage, name_stage in enumerate(('update', 'render', 'swap', 'poll_interval')):
            count, total, maximum = counters[stage * 3:stage * 3 + 3]
            stages[name_stage] = dict(count=count, total_us=total, max_us=maximum,
                                     mean_us=total / count if count else None)
        stages['redraws_per_second'] = counters[3] * 1_000_000 / duration
        screens[name] = stages
    result = dict(label=label, duration_us=duration, before=before, after=snapshot(), screens=screens)
    results['captures'].append(result)
    output.write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(dict(label=label, duration_us=duration, screens=screens), indent=2))

try:
    write32(input_address, 0)
    run_for(.2)
    if 'Splash' in screen():
        tap(2)
    assert 'Names' in screen(), screen()
    tap(2) # Names -> Home
    tap(16)
    tap(16)
    tap(1) # Play
    tap(1) # Pong
    assert 'Pong' in screen(), screen()
    capture('Pong idle', 5)
    write32(input_address, 8)
    run_for(.2)
    capture('Pong held Up, rallies and scoring', 8)
    write32(input_address, 16)
    run_for(.2)
    capture('Pong held Down', 5)
    write32(input_address, 0)
    tap(2)
    tap(16)
    tap(1)
    assert 'Snake' in screen(), screen()
    capture('Snake moving right', .6)
    for label, mask in [('up', 8), ('left', 32), ('down', 16), ('right', 64)]:
        write32(input_address, mask)
        run_for(.05)
        capture('Snake steering ' + label, .6)
    write32(input_address, 0)
    run_for(4)
    assert 'over: true' in str(engine.dereference()['game']), str(engine.dereference()['game'])
    capture('Snake game over idle', 2)
    tap(1)
    assert 'over: false' in str(engine.dereference()['game']), str(engine.dereference()['game'])
    results['retry_passed'] = True
    capture('Snake after retry', .6)
    results['final'] = snapshot()
finally:
    write32(input_address, 0)
    results['synthetic_input_restored'] = read32(input_address) == 0
    results['gpio_controls'] = {str(pin): hex(read32(0x40014004 + 8 * pin))
                               for pin in (14, 15, 16, 17, 18, 23, 29)}
    output.write_text(json.dumps(results, indent=2) + '\n')
end
detach
