import sys, asyncio
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from dotenv import load_dotenv
load_dotenv()

async def test():
    from llm.claude_bridge import ClaudeBridge
    print('1. ClaudeBridge init...')
    bridge = ClaudeBridge(mode='broadcast')
    print(f'   model: {bridge.model}')
    
    print('2. Direct API call...')
    try:
        result = await bridge.generate(
            topic='テスト',
            phase='opening',
            heat=60,
            prompt_hint='挨拶する。2文以内。',
        )
        print(f'   OK: {result[:50]}')
    except Exception as e:
        print(f'   FAIL: {e}')

    print('3. AutonomousTalk test...')
    from brain.autonomous_talk import AutonomousTalk
    from brain.stream_clock import StreamClock
    from brain.topic_engine import TopicEngine
    
    clock = StreamClock()
    te = TopicEngine()
    talk = AutonomousTalk(
        clock=clock, topic_engine=te,
        generate_fn=bridge.generate,
        min_interval=0.5, max_interval=3.0,
    )
    talk.prepare_topics([
        {'topic': 'テスト話題', 'keywords': ['テスト'], 'priority': 60},
    ])
    clock.start()
    
    count = 0
    async for action in talk.run():
        print(f'   Action: {action.text[:50]}...')
        count += 1
        if count >= 2:
            break
    
    clock.stop()
    print(f'Done: {count} actions')

asyncio.run(test())
