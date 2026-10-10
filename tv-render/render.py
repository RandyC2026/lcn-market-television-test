"""Encode a finite HLS test batch from six sanitized quote snapshots."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 960, 540, 24
SCROLL_PX_PER_SECOND = 96


def font_path():
    candidates = [
        os.environ.get('TV_FONT'),
        r'C:\Windows\Fonts\consolab.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError('No monospace font found; set TV_FONT')


def ffmpeg_path():
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError('FFmpeg unavailable') from exc


def validate_feed(feed):
    if feed.get('mode') not in ('TEST', 'MARKET') or len(feed.get('snapshots', [])) != 6:
        raise ValueError('Feed must have mode TEST or MARKET and exactly six snapshots')
    for snapshot in feed['snapshots']:
        quotes = snapshot.get('quotes', [])
        if not 1 <= len(quotes) <= 60:
            raise ValueError('Each snapshot needs 1–60 quotes')
        for quote in quotes:
            symbol = quote.get('symbol', '')
            if not isinstance(symbol, str) or not symbol.isalnum() or len(symbol) > 6 or symbol.upper() != symbol:
                raise ValueError('Invalid quote symbol')
            for key in ('price', 'changePercent'):
                value = quote.get(key)
                if not isinstance(value, (float, int)) or not math.isfinite(value):
                    raise ValueError(f'Invalid {key}')


def ticker_text(snapshot):
    return ''.join(f"   |   {q['symbol']}  ${q['price']:.2f}  {q['changePercent']:+.2f}%"
                   for q in snapshot['quotes']) + '   |   '


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('feed', type=Path)
    parser.add_argument('frames', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error('--seconds must be 1–60')
    feed = json.loads(args.feed.read_text(encoding='utf-8'))
    validate_feed(feed)
    args.output.mkdir(parents=True, exist_ok=True)
    images = [Image.open(args.frames / f'screen-{i}.png').convert('RGB').resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS) for i in range(6)]
    font = ImageFont.truetype(font_path(), 25)
    texts = [ticker_text(snapshot) for snapshot in feed['snapshots']]
    width = max(math.ceil(ImageDraw.Draw(images[0]).textlength(t, font=font)) for t in texts) + 24
    strips = []
    for ticker in texts:
        strip = Image.new('RGB', (width, 65), (2, 8, 8))
        ImageDraw.Draw(strip).text((0, 16), ticker, font=font, fill=(222, 220, 189))
        strips.append(strip)
    command = [ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{WIDTH}x{HEIGHT}', '-r', str(FPS), '-i', 'pipe:0',
               '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24', '-pix_fmt', 'yuv420p',
               '-profile:v', 'main', '-g', str(FPS * 2), '-sc_threshold', '0',
               '-f', 'hls', '-hls_time', '10', '-hls_list_size', '0', '-hls_playlist_type', 'vod',
               '-hls_segment_filename', str(args.output / 'segment-%03d.ts'),
               str(args.output / 'batch.m3u8')]
    start = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in range(FPS * args.seconds):
            index = min(frame // (FPS * 10), 5)
            canvas = images[index].copy()
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((0, 414, WIDTH, 483), fill=(2, 8, 8))
            offset = -((frame * SCROLL_PX_PER_SECOND // FPS) % width)
            while offset < WIDTH:
                canvas.paste(strips[index], (offset, 418))
                offset += width
            process.stdin.write(canvas.tobytes())
    except BrokenPipeError:
        pass
    finally:
        process.stdin.close()
    error = process.stderr.read().decode('utf-8', errors='replace')
    if process.wait() != 0:
        raise RuntimeError(f'FFmpeg failed: {error}')
    print(f'Encoded {args.seconds} seconds of HLS in {time.monotonic() - start:.1f} wall seconds', flush=True)


if __name__ == '__main__':
    main()
