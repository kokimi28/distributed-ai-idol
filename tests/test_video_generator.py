# tests/test_video_generator.py
"""VideoGenerator ユニットテスト"""
from video.video_generator import (
    build_video_prompt, _cache_key, VideoGenerator,
    STYLE_PREFIX, TOPIC_VISUAL_MAP
)


def test_prompt_building():
    """話題キーワードからプロンプトが構築される"""
    print('=== プロンプト構築テスト ===')

    # マッピングに存在する話題
    p = build_video_prompt('宇宙の話', ['星', '銀河'])
    assert STYLE_PREFIX in p
    assert 'galaxy' in p or 'stars' in p
    print(f'[OK] 宇宙: {p[len(STYLE_PREFIX):]}')

    p2 = build_video_prompt('猫の動画見た', ['猫', 'かわいい'])
    assert 'cat' in p2
    print(f'[OK] 猫: {p2[len(STYLE_PREFIX):]}')

    # キーワードでヒット
    p3 = build_video_prompt('最近の天気', ['雨', '傘'])
    assert 'rain' in p3
    print(f'[OK] 雨(keyword): {p3[len(STYLE_PREFIX):]}')

    # マッピングにない話題 → デフォルト
    p4 = build_video_prompt('税金の話', [])
    assert STYLE_PREFIX in p4
    print(f'[OK] default: {p4[len(STYLE_PREFIX):]}')

    # 全マッピングをテスト
    for key in TOPIC_VISUAL_MAP:
        p = build_video_prompt(key)
        assert STYLE_PREFIX in p
    print(f'[OK] {len(TOPIC_VISUAL_MAP)}件のマッピング全通過')


def test_cache_key():
    """同一プロンプトは同一キャッシュキー"""
    print('\n=== キャッシュキーテスト ===')
    k1 = _cache_key('test prompt 1')
    k2 = _cache_key('test prompt 1')
    k3 = _cache_key('test prompt 2')
    assert k1 == k2, 'same prompt should produce same key'
    assert k1 != k3, 'different prompt should produce different key'
    assert k1.endswith('.mp4')
    print(f'[OK] key1={k1}, key3={k3}')


def test_video_generator_init():
    """VideoGeneratorの初期化"""
    print('\n=== VideoGenerator初期化テスト ===')
    # APIキーなし → disabled
    vg = VideoGenerator(api_key='')
    assert not vg.is_enabled
    print('[OK] APIキーなし: disabled')

    # APIキーあり → enabled
    vg2 = VideoGenerator(api_key='test_key_123')
    assert vg2.is_enabled
    print('[OK] APIキーあり: enabled')

    # キャッシュカウント
    count = vg2.get_cached_count()
    print(f'[OK] キャッシュ数: {count}')


def test_provider_config():
    """プロバイダ設定"""
    print('\n=== プロバイダ設定テスト ===')
    from video.video_generator import KlingProvider
    for name in ['piapi', 'aimlapi', 'kling_official']:
        p = KlingProvider(provider=name, api_key='test')
        assert p.base_url
        assert p.create_ep
        print(f'[OK] {name}: {p.base_url}')


if __name__ == '__main__':
    test_prompt_building()
    test_cache_key()
    test_video_generator_init()
    test_provider_config()
    print('\n=== 全テスト成功 ===')
