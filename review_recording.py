from pathlib import Path
import cv2
from PIL import Image, ImageDraw

source = next(Path(r'C:\Users\12503\Videos\Captures').glob('PageSpeed Insights and 9 more pages*2026-09-08 17-01-37.mp4'))
folder = Path(__file__).parent / 'reports' / 'recording_review'
folder.mkdir(parents=True, exist_ok=True)
cap = cv2.VideoCapture(str(source))
fps = cap.get(cv2.CAP_PROP_FPS)
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
print('Duration seconds:', duration, 'FPS:', fps, flush=True)
times = [duration * i / 11 for i in range(12)]
montage = Image.new('RGB', (1440, 4 * 300), 'white')
draw = ImageDraw.Draw(montage)
for i, timestamp in enumerate(times):
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, min(timestamp, duration - 0.3)) * 1000)
    ok, frame = cap.read()
    if not ok:
        continue
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    image.save(folder / f'frame_{i:02d}.png')
    image.thumbnail((480, 270))
    x, y = (i % 3) * 480, (i // 3) * 300
    montage.paste(image, (x, y + 25))
    draw.text((x + 10, y + 5), f'{i}: {timestamp:.1f}s', fill='black')
montage.save(folder / 'montage.jpg')
cap.release()
