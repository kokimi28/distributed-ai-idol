import json, os
m = json.load(open('C:/Projects/distributed-ai-idol/video/manifest.json','r',encoding='utf-8'))
clips = m.get('clips', {})
for cid in sorted(clips.keys()):
    e = clips[cid]
    has_vid = bool(e.get('video','')) and os.path.exists(e.get('video',''))
    has_img = bool(e.get('image','')) and os.path.exists(e.get('image',''))
    has_url = bool(e.get('image_url',''))
    cat = e.get('category','?')
    print(f'{cid:25s} cat={cat:12s} img={has_img} vid={has_vid} url={has_url}')
