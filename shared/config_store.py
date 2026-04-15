# shared/config_store.py
"""
設定データストア

Firestore + JSON fallback + インメモリキャッシュの3層構造。
全モジュールのハードコードデータをここから読み込む。

Usage:
    from shared.config_store import config
    fillers = await config.get('fillers')
    rules = await config.get('reflex_rules')

設計:
  1. Firestore（primary）: GCPでリアルタイム更新可能
  2. JSON fallback: Firestore未接続時 or 開発時
  3. Memory cache: TTLベースで自動リフレッシュ
"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Optional, Any
from loguru import logger

# シードデータのパス
_SEED_DATA_PATH = Path(__file__).parent / 'seed_data.json'

# Firestoreコレクション名
_COLLECTION = 'config'


class ConfigStore:
    """設定データの3層ストア"""

    def __init__(self, cache_ttl_sec: float = 300.0):
        self._cache: dict[str, Any] = {}
        self._cache_ts: dict[str, float] = {}
        self._cache_ttl = cache_ttl_sec
        self._firestore_db = None
        self._seed_data: Optional[dict] = None
        self._initialized = False

        # シードデータは同期で即ロード（get_syncが起動前に使えるように）
        try:
            if _SEED_DATA_PATH.exists():
                with open(_SEED_DATA_PATH, 'r', encoding='utf-8') as f:
                    self._seed_data = json.load(f)
        except Exception:
            self._seed_data = {}

    async def initialize(self):
        """Firestore接続を試みる。失敗してもJSON fallbackで動作する"""
        if self._initialized:
            return

        # Firestore接続
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
            if not firebase_admin._apps:
                cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH',
                                      './firebase-service-account.json')
                if os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
            self._firestore_db = firestore.client()
            logger.info('ConfigStore: Firestore接続OK')
        except Exception as e:
            logger.warning(f'ConfigStore: Firestore接続失敗（JSON fallback使用）: {e}')
            self._firestore_db = None

        # JSONシードデータは__init__で読み込み済み
        self._initialized = True

    async def get(self, key: str, default: Any = None) -> Any:
        """設定データを取得する（キャッシュ→Firestore→JSON）"""
        if not self._initialized:
            await self.initialize()

        # 1. キャッシュチェック（TTL内）
        if key in self._cache:
            age = time.time() - self._cache_ts.get(key, 0)
            if age < self._cache_ttl:
                return self._cache[key]

        # 2. Firestoreから取得
        if self._firestore_db:
            try:
                doc = self._firestore_db.collection(_COLLECTION).document(key).get()
                if doc.exists:
                    data = doc.to_dict()
                    self._cache[key] = data
                    self._cache_ts[key] = time.time()
                    return data
            except Exception as e:
                logger.debug(f'ConfigStore: Firestore読み込みエラー ({key}): {e}')

        # 3. JSONシードデータから取得
        if self._seed_data and key in self._seed_data:
            data = self._seed_data[key]
            self._cache[key] = data
            self._cache_ts[key] = time.time()
            return data

        return default

    async def set(self, key: str, data: dict):
        """設定データを保存（Firestore + キャッシュ更新）"""
        if not self._initialized:
            await self.initialize()

        # Firestoreに保存
        if self._firestore_db:
            try:
                self._firestore_db.collection(_COLLECTION).document(key).set(data)
            except Exception as e:
                logger.error(f'ConfigStore: Firestore書き込みエラー ({key}): {e}')

        # キャッシュ更新
        self._cache[key] = data
        self._cache_ts[key] = time.time()

    def invalidate(self, key: str = None):
        """キャッシュを無効化。keyなしで全クリア"""
        if key:
            self._cache.pop(key, None)
            self._cache_ts.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ts.clear()

    def get_sync(self, key: str, default: Any = None) -> Any:
        """同期版get（反射層など<20ms制約のモジュール用）
        キャッシュのみ参照。事前にpreload()でキャッシュを温めること"""
        if key in self._cache:
            return self._cache[key]
        if self._seed_data and key in self._seed_data:
            data = self._seed_data[key]
            self._cache[key] = data
            self._cache_ts[key] = time.time()
            return data
        return default

    async def preload(self, keys: list[str]):
        """指定キーを事前にキャッシュに読み込む（起動時に呼ぶ）"""
        for key in keys:
            await self.get(key)
        logger.info(f'ConfigStore: {len(keys)}キーをプリロード完了')


# シングルトンインスタンス
config = ConfigStore()
