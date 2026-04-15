# tests/debug_phase_timing.py
import time
from brain.stream_clock import StreamClock

c = StreamClock(planned_duration_minutes=30.0)
print(f'opening={c.opening_minutes} closing={c.closing_minutes}')
c.start()
start = time.time()

for i in range(25):
    time.sleep(5)
    t = c.tick()
    elapsed = time.time() - start
    print(f'{elapsed:5.1f}s | phase={t["phase"]:8s} | elapsed_min={t["elapsed_min"]}')
    if t['phase'] == 'main':
        print(f'  -> MAIN at {elapsed:.1f}s (expected ~90s)')
        break

print('done')
