import anthropic
import json
import os
from dotenv import load_dotenv
from brain.reflex_layer import apply_reflex, merge_spike_to_state
from memory.emotion_carry import calc_emotion_residue, apply_residue_to_initial_state
from character.big_five import load_big_five

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
big_five = load_big_five()

async def process_v4(user_input: str, char_state: dict,
                      mode: str, user_history: list,
                      prev_session_data: dict = None,
                      silence_minutes: float = 0) -> dict:

    # Stage 1: 反射層
    spike = apply_reflex(user_input, silence_minutes)
    char_state = merge_spike_to_state(char_state, spike)

    # 感情残り香
    if prev_session_data:
        residue = calc_emotion_residue(
            prev_session_data.get('emotions', {}),
            prev_session_data.get('end_time')
        )
        char_state = apply_residue_to_initial_state(char_state, residue)

    # Stage 2: LLM①（感情評価）
    judge_prompt = f'''
感情状態を評価してください。
{big_five.to_prompt_text(mode)}
反射スパイク: surprise={spike.surprise}, warmth={spike.warmth}
現在の感情状態: {json.dumps(char_state, ensure_ascii=False)}
ユーザー入力: {user_input}
モード: {mode}
JSONのみ返す:
{{"suppressed_emotions": {{"joy": 0, "sadness": 0}},
"leak_true_self": false, "expression_pattern": "踏み込んで引く",
"relationship_distance": "普通"}}
'''
    resp1 = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=300,
        messages=[{'role': 'user', 'content': judge_prompt}]
    )
    raw = resp1.content[0].text.strip()
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        emotion_state = json.loads(raw[start:end])
    except json.JSONDecodeError:
        emotion_state = {
            "suppressed_emotions": {"joy": 0, "sadness": 0},
            "leak_true_self": False,
            "expression_pattern": "踏み込んで引く",
            "relationship_distance": "普通"
        }

    # Stage 3: LLM②（表現生成）
    mode_prompt = (
        '配信中は外向性高く。1〜3文。'
        if mode == 'broadcast' else
        '個人会話。短文。「かな」「かも」を使う。「わたし」が自然に出る。'
    )
    expr_prompt = f'''
{big_five.to_prompt_text(mode)}
{mode_prompt}
感情状態: {emotion_state}
ユーザー入力: {user_input}
1〜2文以内。感情を直接言わない。「大丈夫だよ」はNG。
'''
    resp2 = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=200,
        messages=[{'role': 'user', 'content': expr_prompt}]
    )
    expression = resp2.content[0].text

    return {
        'emotion_state': emotion_state,
        'expression': expression,
        'spike': spike,
        'updated_char_state': char_state
    }