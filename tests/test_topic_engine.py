import sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from brain.topic_engine import TopicEngine

te = TopicEngine()
te.add_topic('猫の話', ['猫', 'ペット'])

print('=== No-comment simulation (15 turns) ===')
for i in range(15):
    r = te.tick()
    phase = r['phase'] or 'done'
    heat = r['heat']
    hint = r['prompt_hint'][:50].replace('\n', ' ')
    print(f't{i:2d}: {phase:8s} heat={heat:3d}  {hint}')
    if phase == 'done' or r['action'] == 'need_topics':
        print('  -> topic ended')
        break
