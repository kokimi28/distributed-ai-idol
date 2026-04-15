import asyncio
from llm.claude_client_v4 import process_v4

async def test_v4():
    char_state = {
        'joy': 40, 'sadness': 0, 'anger': 0, 'surprise': 0,
        'embarrass': 0, 'fear': 0, 'affection': 50,
        'fatigue': 20, 'tension': 60, 'loneliness': 15
    }

    print('=== テスト1: 驚きワードへの反射 ===')
    result = await process_v4(
        user_input='えっ！まじで？！',
        char_state=char_state.copy(),
        mode='private',
        user_history=[]
    )
    print(f'反射スパイク: surprise={result["spike"].surprise}')
    print(f'LLM①評価: {result["emotion_state"]}')
    print(f'LLM②表現: {result["expression"]}')
    assert result['spike'].surprise > 0
    print('テスト1: 成功')

    print()
    print('=== テスト2: 感情残り香あり ===')
    from datetime import datetime, timedelta
    prev_data = {
        'emotions': {'joy': 80, 'sadness': 10},
        'end_time': datetime.now() - timedelta(minutes=20)
    }
    result2 = await process_v4(
        user_input='ねえ、今日どうだった？',
        char_state=char_state.copy(),
        mode='private',
        user_history=[],
        prev_session_data=prev_data
    )
    print(f'残り香適用後joy: {result2["updated_char_state"]["joy"]}')
    print(f'LLM②表現: {result2["expression"]}')
    print('テスト2: 成功')
    print()
    print('v4統合テスト: 完了')

asyncio.run(test_v4())