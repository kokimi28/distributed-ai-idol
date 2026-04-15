"""期限切れのimage_urlをクリアして、prerenderがFluxを再生成できるようにする"""
import json, os
MANIFEST = 'C:/Projects/distributed-ai-idol/video/manifest.json'
m = json.load(open(MANIFEST, 'r', encoding='utf-8'))
cleared = 0
for cid, entry in m.get('clips', {}).items():
    vid = entry.get('video', '')
    has_vid = vid and os.path.exists(vid)
    if not has_vid and entry.get('image_url'):
        del entry['image_url']
        cleared += 1
        print(f'Cleared: {cid}')

with open(MANIFEST, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print(f'\n{cleared} URLs cleared')
