# tests/test_config_store.py
"""config_storeとseed_dataの整合性テスト"""
import json
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_seed_data_valid_json():
    """seed_data.jsonが有効なJSONか"""
    from pathlib import Path
    path = Path(__file__).parent.parent / 'shared' / 'seed_data.json'
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f'seed_data.json: {len(data)}キー')
    for key in data:
        print(f'  {key}: {type(data[key]).__name__}')
    assert len(data) >= 8, f'キーが少なすぎる: {len(data)}'
    print('JSON検証: OK')

def test_config_store_sync():
    """config_storeのget_syncがseed_dataを読めるか"""
    from shared.config_store import config
    # seed_dataは自動ロードされる
    fillers = config.get_sync('fillers')
    assert fillers is not None, 'fillersが取得できない'
    assert 'opening' in fillers, 'fillers.openingがない'
    assert len(fillers['opening']) >= 2, 'openingフィラーが少なすぎ'
    print(f'fillers: {len(fillers)}カテゴリ OK')

    rules = config.get_sync('reflex_rules')
    assert rules is not None, 'reflex_rulesが取得できない'
    assert 'rules' in rules, 'reflex_rules.rulesがない'
    print(f'reflex_rules: {len(rules["rules"])}ルール OK')

    half_lives = config.get_sync('emotion_half_lives')
    assert half_lives is not None
    assert 'joy' in half_lives
    print(f'emotion_half_lives: {len(half_lives)}感情 OK')

    heat = config.get_sync('heat_rules')
    assert heat is not None
    assert 'comment_increase' in heat
    print(f'heat_rules: {len(heat)}ルール OK')

    phase = config.get_sync('phase_instructions')
    assert phase is not None
    assert 'INTRO' in phase
    print(f'phase_instructions: {len(phase)}フェーズ OK')

    voice = config.get_sync('voice_settings')
    assert voice is not None
    assert 'base' in voice
    assert 'emotion_influence' in voice
    print(f'voice_settings: OK')

    fallbacks = config.get_sync('topic_fallbacks')
    assert fallbacks is not None
    print(f'topic_fallbacks: OK')

    vtube = config.get_sync('vtube_params')
    assert vtube is not None
    assert 'param_map' in vtube
    print(f'vtube_params: OK')

    print('\nconfig_store同期テスト: 全て成功')

async def test_config_store_async():
    """config_storeのasync getが動くか"""
    from shared.config_store import config
    await config.initialize()

    fillers = await config.get('fillers')
    assert fillers is not None
    print(f'async get fillers: OK')

    await config.preload([
        'fillers', 'reflex_rules', 'emotion_half_lives',
        'heat_rules', 'phase_instructions', 'voice_settings',
        'topic_fallbacks', 'vtube_params',
    ])
    print('preload 8キー: OK')

    print('\nconfig_store非同期テスト: 全て成功')

def test_modules_use_config():
    """各モジュールがconfig_storeからデータを読めるか"""
    from brain.reflex_layer import apply_reflex
    spike = apply_reflex('え！まじで！')
    assert spike.surprise > 0
    print(f'reflex_layer via config: surprise={spike.surprise} OK')

    from memory.emotion_carry import calc_emotion_residue
    from datetime import datetime, timedelta
    res = calc_emotion_residue({'joy': 80}, datetime.now() - timedelta(minutes=30))
    assert res['joy'] > 0
    print(f'emotion_carry via config: joy residue={res["joy"]} OK')

    from character.emotion_to_voice import convert_emotion_to_voice
    params = convert_emotion_to_voice({'joy': 80}, 'broadcast')
    assert 'stability' in params
    print(f'emotion_to_voice via config: stability={params["stability"]:.3f} OK')

    print('\nモジュール統合テスト: 全て成功')

if __name__ == '__main__':
    test_seed_data_valid_json()
    print()
    test_config_store_sync()
    print()
    test_modules_use_config()
    print()
    asyncio.run(test_config_store_async())
    print('\n========== 全テスト完了 ==========')
