from character.big_five import load_big_five

def test_big_five():
    profile = load_big_five()
    print(f'Big Fiveプロファイル:')
    print(f'  O={profile.openness}, C={profile.conscientiousness}')
    print(f'  E(配信)={profile.extraversion_public}')
    print(f'  E(個人)={profile.extraversion_private}')
    print(f'  A={profile.agreeableness}, N={profile.neuroticism}')

    assert profile.extraversion_public > profile.extraversion_private, \
        '配信時の外向性が個人時より低い（設計と逆）'

    print()
    print('--- 配信モードプロンプト ---')
    print(profile.to_prompt_text('broadcast'))
    print('--- 個人モードプロンプト ---')
    print(profile.to_prompt_text('private'))
    print('Big Fiveテスト: 成功')

test_big_five()