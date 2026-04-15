# tests/test_text_parser.py
"""テキストパーサーのテスト（v4: フィラー完全埋め込み方式）"""
from voice.text_parser import parse_speech_text

def test_filler_embedded():
    """フィラーの括弧が外れて本文に溶ける"""
    text = '（ふふっ）あのさ、聞いてよ。'
    segs = parse_speech_text(text)
    assert len(segs) == 1, f'1セグメントのはずが{len(segs)}'
    assert segs[0].text == 'ふふっあのさ、聞いてよ。'
    print(f'フィラー埋め込み: "{segs[0].text}" OK')

def test_silence_splits():
    """間タグだけが分割点"""
    text = '（ふふっ）あのさ。【間】最近気になってて。'
    segs = parse_speech_text(text)
    assert len(segs) == 3
    assert segs[0].type == 'speech'
    assert segs[1].type == 'silence'
    assert segs[1].duration_ms == 800
    assert segs[2].type == 'speech'
    print(f'間分割: OK')
    for s in segs:
        print(f'  [{s.type:8s}] {s.text or f"{s.duration_ms}ms"}')

def test_multiple_fillers_one_chunk():
    """複数フィラーが1つのチャンクに埋め込まれる"""
    text = '（えっ！）まじで？（あはは）面白い。'
    segs = parse_speech_text(text)
    assert len(segs) == 1
    assert 'えっ！' in segs[0].text
    assert 'あはは' in segs[0].text
    print(f'複数フィラー1チャンク: "{segs[0].text}" OK')

def test_no_tags():
    """タグなし"""
    text = 'なんかね、最近気になって。'
    segs = parse_speech_text(text)
    assert len(segs) == 1
    assert segs[0].text == text
    print('タグなし: OK')

def test_realistic():
    """LLMの実際の出力"""
    text = (
        '（んー……）みんなに聞きたいんだけどさ。'
        '深夜に目が覚めた時、最初に何する？【間】'
        'わたしだったら……って、わたし寝ないんだけどね。（ふふっ）'
    )
    segs = parse_speech_text(text)
    print(f'リアル: {len(segs)}セグメント')
    for s in segs:
        print(f'  [{s.type:8s}] {s.text or f"{s.duration_ms}ms"}')
    assert len(segs) == 3  # speech + silence + speech
    assert 'んー……' in segs[0].text
    assert 'ふふっ' in segs[2].text
    print('OK')

if __name__ == '__main__':
    test_filler_embedded()
    test_silence_splits()
    test_multiple_fillers_one_chunk()
    test_no_tags()
    test_realistic()
    print('\nテキストパーサーテスト: 全て成功')
