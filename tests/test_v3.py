import sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from video.image_generator import get_all_clips, get_topic_items, build_clip_prompt, ImageGenerator
from video.clip_selector import ClipSelector
from video.prerender import show_status

clips = get_all_clips()
print(f'Total clips defined: {len(clips)}')

items = get_topic_items('猫の話', ['猫'])
print(f'Cat topic items: {items}')

c = clips[0]
p = build_clip_prompt(c)
print(f'Sample clip: {c["id"]} ({c["category"]}/{c["item"]})')
print(f'  Image prompt: {p["image"][:80]}...')
print(f'  Video prompt: {p["video"][:60]}...')

ig = ImageGenerator()
print(f'ImageGenerator OK, cached: {ig.get_cached_count()}')

cs = ClipSelector()
print(f'ClipSelector OK, has_clips: {cs.has_clips}')

print()
show_status()

from broadcast.pipeline import BroadcastPipeline
print('Pipeline import OK')
