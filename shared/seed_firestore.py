# shared/seed_firestore.py
"""
シードデータをFirestoreに投入するスクリプト。

Usage:
  python -m shared.seed_firestore           # 全データ投入
  python -m shared.seed_firestore fillers   # 特定キーのみ
  python -m shared.seed_firestore --list    # キー一覧表示
"""

import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SEED_PATH = Path(__file__).parent / 'seed_data.json'
COLLECTION = 'config'


def main():
    # JSONシードデータ読み込み
    with open(SEED_PATH, 'r', encoding='utf-8') as f:
        seed = json.load(f)

    if '--list' in sys.argv:
        print(f'シードデータキー ({len(seed)}件):')
        for key in seed:
            val = seed[key]
            size = len(json.dumps(val, ensure_ascii=False))
            print(f'  {key}: {size} chars')
        return

    # Firestore接続
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH',
                          './firebase-service-account.json')
    if not os.path.exists(cred_path):
        print(f'認証ファイルが見つかりません: {cred_path}')
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # 投入するキーを決定
    keys = sys.argv[1:] if len(sys.argv) > 1 else list(seed.keys())
    keys = [k for k in keys if not k.startswith('--')]

    print(f'Firestoreに投入: {len(keys)}キー')
    for key in keys:
        if key not in seed:
            print(f'  ❌ {key}: シードデータに存在しない')
            continue
        data = seed[key]
        # Firestoreのドキュメントはdictである必要がある
        if not isinstance(data, dict):
            data = {'data': data}
        db.collection(COLLECTION).document(key).set(data)
        print(f'  ✅ {key}')

    print('完了')


if __name__ == '__main__':
    main()
