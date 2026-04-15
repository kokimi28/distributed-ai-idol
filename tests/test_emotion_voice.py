# tests/test_emotion_voice.py  感情→音声パラメータ変換テスト
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from character.emotion_to_voice import convert_emotion_to_voice


def test_emotion_voice_mapping():
    # joy=80の時：低stability・高style（興奮系）
    settings_joy = convert_emotion_to_voice({'joy': 80}, 'broadcast')
    print(f'joy=80（配信）: {settings_joy}')
    assert settings_joy['stability'] < 0.5, \
        f'joy高=興奮→stability低くなるはず（実際: {settings_joy["stability"]}）'

    # sadness=75の時：高stability（静か系）
    settings_sad = convert_emotion_to_voice({'sadness': 75}, 'private')
    print(f'sadness=75（個人）: {settings_sad}')
    assert settings_sad['stability'] > 0.6, \
        f'sadness=静か→stability高くなるはず（実際: {settings_sad["stability"]}）'

    # PRIVATEモード：similarity_boost高め（キャラ声重視）
    settings_private = convert_emotion_to_voice({'joy': 40}, 'private')
    print(f'PRIVATEモード: {settings_private}')
    assert settings_private['similarity_boost'] >= 0.80, \
        f'PRIVATEはsimilarity_boost高め（素の声に近い）（実際: {settings_private["similarity_boost"]}）'

    print('感情→音声変換テスト: 成功')


test_emotion_voice_mapping()
