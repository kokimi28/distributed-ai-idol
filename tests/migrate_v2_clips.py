"""v2クリップをv3マニフェストに仮マッピング（修正版）"""
import json, os, glob

VID_CACHE = 'C:\\Projects\\distributed-ai-idol\\video\\cache'
MANIFEST = 'C:\\Projects\\distributed-ai-idol\\video\\manifest.json'

REACT_MAP = {
    'react_surprise': 'react_48a318a016.mp4',
    'react_laugh': 'react_fed284f87a.mp4',
    'react_think': 'react_c44d5d9a66.mp4',
    'react_nod': 'react_b410769b28.mp4',
    'react_shy': 'react_3bcd341530.mp4',
    'react_wave': 'react_68bc6ef855.mp4',
}

ALL_IDS = [
    ('desk_type','furniture','desk','B'), ('desk_lean','furniture','desk','B'),
    ('desk_think','furniture','desk','A'), ('desk_close','furniture','desk','B'),
    ('shelf_browse','furniture','bookshelf','B'), ('shelf_read','furniture','bookshelf','B'),
    ('shelf_reach','furniture','bookshelf','B'), ('shelf_put','furniture','bookshelf','B'),
    ('shelf_tidy','furniture','bookshelf','C'),
    ('bed_flop','furniture','bed','C'), ('bed_read','furniture','bed','B'),
    ('bed_curl','furniture','bed','C'), ('bed_sit','furniture','bed','B'),
    ('bed_phone','furniture','bed','B'),
    ('guitar_tune','item','guitar','B'), ('guitar_play','item','guitar','B'),
    ('guitar_hum','item','guitar','A'), ('guitar_down','item','guitar','B'),
    ('scope_peer','item','telescope','B'), ('scope_wow','item','telescope','A'),
    ('scope_adjust','item','telescope','B'),
    ('cat_play','item','cat','B'), ('cat_lap','item','cat','A'),
    ('cat_show','item','cat','A'), ('cat_watch','item','cat','C'),
    ('cat_feed','item','cat','B'),
    ('mug_sip','item','mug','A'), ('mug_warm','item','mug','A'),
    ('mug_window','item','mug','B'),
    ('hp_on','item','headphones','A'), ('hp_off','item','headphones','A'),
    ('hp_dance','item','headphones','B'),
    ('plant_mist','item','plants','B'), ('plant_look','item','plants','A'),
    ('plant_talk','item','plants','A'),
    ('talk_gesture','talking','_talking','A'),
    ('talk_chin','talking','_talking','A'),
    ('talk_excited','talking','_talking','A'),
    ('talk_think','talking','_talking','A'),
    ('talk_laugh','talking','_talking','A'),
    ('talk_whisper','talking','_talking','A'),
    ('trans_desk_shelf','transition','_transition','C'),
    ('trans_bed_desk','transition','_transition','C'),
    ('trans_window','transition','_transition','C'),
    ('trans_sit','transition','_transition','B'),
]

scenes = sorted(glob.glob(os.path.join(VID_CACHE, 'scene_*.mp4')))
manifest = {'clips': {}}

# Reactions
for cid, fname in REACT_MAP.items():
    p = os.path.join(VID_CACHE, fname)
    if os.path.exists(p):
        manifest['clips'][cid] = {
            'video': p, 'category': 'reaction',
            'item': cid.replace('react_',''), 'cam': 'A',
        }

# Items/talking/transitions - cycle through scenes
for i, (cid, cat, item, cam) in enumerate(ALL_IDS):
    scene = scenes[i % len(scenes)]
    manifest['clips'][cid] = {
        'video': scene, 'category': cat,
        'item': item, 'cam': cam,
    }

with open(MANIFEST, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

total = len(manifest['clips'])
by_cat = {}
for v in manifest['clips'].values():
    c = v['category']
    by_cat[c] = by_cat.get(c, 0) + 1
print(f'Mapped {total} clips')
for c, n in sorted(by_cat.items()):
    print(f'  {c}: {n}')
