# video/clip_selector.py
"""
クリップセレクター v4 — VTuber Presence Model

設計思想:
  まおは「ずっとそこにいる」。画像の切り替わり感をゼロに。
  
  ホームショット: マルチフレームの talking クリップが永続ループ。
  カットアウェイ: 【間】タイミングで短時間だけアイテムを表示、すぐホームに戻る。
  話題変更: ホームショットを別のtalkingクリップにクロスフェード（切替感なし）。
"""

import os
import json
import random
from loguru import logger

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), 'manifest.json')
ROOM_STATE_PATH = os.path.join(os.path.dirname(__file__), 'room_state.json')


class ClipSelector:
    """VTuber Presence: ホームショット常駐 + 稀なカットアウェイ"""

    def __init__(self, overlay_server=None):
        self.overlay = overlay_server
        self._manifest = self._load_json(MANIFEST_PATH)
        self._room = self._load_json(ROOM_STATE_PATH)
        self._home_id = None       # 現在のホームショットclip_id
        self._used_homes = []      # 使用済みホームショット（重複回避）
        self._used_cutaways = []   # 使用済みカットアウェイ
        self._topic_items = []

    def _load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    @property
    def has_clips(self):
        for entry in self._manifest.get('clips', {}).values():
            if self._has_asset(entry): return True
        return False

    def _has_asset(self, entry):
        vid = entry.get('video', '')
        img = entry.get('image', '')
        frames = entry.get('frames', [])
        return ((vid and os.path.exists(vid)) or
                (img and os.path.exists(img)) or
                any(os.path.exists(f) for f in frames))

    def reload_manifest(self):
        self._manifest = self._load_json(MANIFEST_PATH)

    # ===== メイン操作 =====

    def on_topic_change(self, topic_key):
        """話題変更 → 新しいホームショットを選んでクロスフェード"""
        self._topic_items = self._get_topic_items(topic_key)
        home = self._pick_home()
        if home:
            self._send_home(home)
            logger.info(f'[映像] ホーム: {home["id"]} (topic: {topic_key[:20]})')

    def send_cutaway(self):
        """【間】タイミングで短いカットアウェイを送る。ホームには自動で戻る。"""
        cut = self._pick_cutaway()
        if cut:
            self._send_cutaway_msg(cut)
            logger.info(f'[映像] カットアウェイ: {cut["id"]}')
            return True
        return False

    def on_comment(self, spike):
        """コメントreaction（将来用。今は何もしない）"""
        pass

    def on_speak(self, topic_key):
        """発話開始。ホームが未設定なら設定する。"""
        if self._home_id is None:
            self.on_topic_change(topic_key)

    def on_silence(self, topic_key):
        """沈黙。何もしない（ホームショットがループし続ける）"""
        pass

    def on_timer(self, topic_key):
        """定期呼び出し。何もしない（ホームショットがループし続ける）"""
        pass

    # ===== ホームショット選択 =====

    def _pick_home(self):
        """talkingカテゴリからホームを選ぶ（1枚画像）"""
        clips = self._manifest.get('clips', {})
        candidates = []
        for cid, entry in clips.items():
            if not cid.startswith('talk_'): continue
            if not self._has_asset(entry): continue
            if cid in self._used_homes: continue
            candidates.append((cid, entry))

        if not candidates:
            self._used_homes = []
            for cid, entry in clips.items():
                if cid.startswith('talk_') and self._has_asset(entry):
                    candidates.append((cid, entry))

        if not candidates: return None
        random.shuffle(candidates)
        cid, entry = candidates[0]
        self._used_homes.append(cid)
        self._home_id = cid
        return {'id': cid, **entry}

    def _pick_cutaway(self):
        """話題アイテムのcam=B/Cクリップからカットアウェイを選ぶ"""
        clips = self._manifest.get('clips', {})
        candidates = []
        # 話題アイテムのクリップを優先
        item_ids = self._collect_clip_ids(self._topic_items)
        for cid in item_ids:
            if cid.startswith('talk_'): continue
            if cid in self._used_cutaways: continue
            entry = clips.get(cid, {})
            if self._has_asset(entry):
                candidates.append((cid, entry))
        if not candidates:
            self._used_cutaways = []
            for cid in item_ids:
                if cid.startswith('talk_'): continue
                entry = clips.get(cid, {})
                if self._has_asset(entry):
                    candidates.append((cid, entry))
        if not candidates: return None
        random.shuffle(candidates)
        cid, entry = candidates[0]
        self._used_cutaways.append(cid)
        return {'id': cid, **entry}

    # ===== 送信 =====

    def _send_home(self, clip):
        """ホームショットを送信。バッチの最初のアイテムとして。"""
        if not (self.overlay and self.overlay.is_running): return
        port = self.overlay._http_port
        item = self._clip_to_item(clip, port)
        if item:
            logger.info(f'[映像] 送信: type={item.get("type")} frames={len(item.get("frames",[]))} url={item.get("url","")[:50]}')
            self.overlay._broadcast({
                'type': 'clip_batch',
                'items': [item],
            })

    def _send_cutaway_msg(self, clip):
        """カットアウェイを送信。ホームとは別メッセージ。"""
        if not (self.overlay and self.overlay.is_running): return
        port = self.overlay._http_port
        item = self._clip_to_item(clip, port)
        if item:
            item['type_msg'] = 'cutaway'  # cutawayであることを明示
            self.overlay._broadcast({
                'type': 'cutaway',
                **item,
            })

    def _clip_to_item(self, clip, port):
        """clipデータをWebSocket送信用のdictに変換"""
        vid = clip.get('video', '')
        img = clip.get('image', '')
        vid_ok = vid and os.path.exists(vid)
        img_ok = img and os.path.exists(img)
        # 動画 > 画像の優先順（Klingで動画化されたら自動的にそちらを使う）
        if vid_ok:
            return {'type': 'video', 'url': f'http://127.0.0.1:{port}/video/cache/{os.path.basename(vid)}', 'role': 'talk'}
        if img_ok:
            return {'type': 'image', 'url': f'http://127.0.0.1:{port}/video/cache/img/{os.path.basename(img)}', 'role': 'talk'}
        return None

    # ===== ヘルパー =====

    def _get_topic_items(self, topic):
        topic_items = self._room.get('topic_items', {})
        for key, items in topic_items.items():
            if key in topic:
                return items
        return self._room.get('default_items', ['desk', 'mug'])

    def _collect_clip_ids(self, item_ids):
        ids = []
        room = self._room
        for iid in item_ids:
            if iid in room.get('furniture', {}):
                for c in room['furniture'][iid]['clips']:
                    ids.append(c['id'])
            if iid in room.get('items', {}):
                for c in room['items'][iid]['clips']:
                    ids.append(c['id'])
        for c in room.get('transitions', []):
            ids.append(c['id'])
        return ids
