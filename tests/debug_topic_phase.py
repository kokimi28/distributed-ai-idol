# tests/debug_topic_phase.py
import time
from brain.stream_clock import StreamClock
from brain.topic_engine import TopicEngine

# StreamClock test
c = StreamClock(planned_duration_minutes=30.0)
print(f'opening_minutes={c.opening_minutes}')
print(f'closing_minutes={c.closing_minutes}')
c.start()
print(f'after start: opening={c.opening_minutes}')
time.sleep(2)
t = c.tick()
print(f'2s: phase={t["phase"]} elapsed={t["elapsed_min"]}')

# TopicEngine test
print()
te = TopicEngine()
te.add_topic('test topic 1', ['kw1'], priority=80)
te.add_topic('test topic 2', ['kw2'], priority=60)
print(f'queue size: {len(te.topic_queue)}')
print(f'active before tick: {te.active_topic}')

r = te.tick()
print(f'tick1: action={r["action"]} topic={r.get("topic","?")}')
print(f'active after tick: {te.active_topic.topic if te.active_topic else None}')

s = te.get_state_summary()
print(f'summary: {s["active"]["topic"]}')

# simulate multiple ticks
for i in range(5):
    r = te.tick()
    phase = r.get('phase', '?')
    topic = r.get('topic', '?')
    at = te.active_topic.topic[:20] if te.active_topic else 'None'
    print(f'tick{i+2}: phase={phase} topic={topic[:20] if topic else "?"} active={at}')

print()
print('=== test done ===')
