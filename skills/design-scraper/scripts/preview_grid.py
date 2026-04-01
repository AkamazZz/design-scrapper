#!/usr/bin/env python3
"""Generate an HTML contact sheet / preview grid for all scraped designs."""

import os
import sys
import base64
import json
from pathlib import Path


def get_media_files(directory):
    """Recursively find all image/video files."""
    extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4'}
    files = []
    for root, dirs, filenames in os.walk(directory):
        for f in sorted(filenames):
            if Path(f).suffix.lower() in extensions:
                files.append(os.path.join(root, f))
    return files


def get_video_poster_data_uri(filepath, max_size=300):
    """Extract a poster frame from MP4 using macOS qlmanage, return as base64 data URI."""
    import subprocess
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ['qlmanage', '-t', '-s', str(max_size), '-o', tmpdir, filepath],
                capture_output=True, timeout=10
            )
            # qlmanage outputs filename.mp4.png
            poster_path = os.path.join(tmpdir, os.path.basename(filepath) + '.png')
            if os.path.exists(poster_path):
                from PIL import Image
                import io
                img = Image.open(poster_path)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                b64 = base64.b64encode(buf.getvalue()).decode()
                return f"data:image/png;base64,{b64}"
    except Exception:
        pass
    return None


def get_thumbnail_data_uri(filepath, max_size=300):
    """Create a small base64 thumbnail for embedding in HTML."""
    ext = Path(filepath).suffix.lower()
    if ext == '.mp4':
        poster = get_video_poster_data_uri(filepath, max_size)
        return {'poster': poster, 'abs_path': filepath}, 'video'
    try:
        from PIL import Image
        img = Image.open(filepath)
        img.thumbnail((max_size, max_size * 2), Image.LANCZOS)
        import io
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}", 'image'
    except Exception:
        return None, 'image'


def read_palette(filepath):
    """Read palette.json if it exists next to the file."""
    palette_path = os.path.join(os.path.dirname(filepath), 'palette.json')
    if os.path.exists(palette_path):
        with open(palette_path) as f:
            return json.load(f)
    # Check parent directory too
    parent_palette = os.path.join(os.path.dirname(os.path.dirname(filepath)), 'palette.json')
    return None


def generate_html(directory, output_path):
    """Generate the preview grid HTML."""
    files = get_media_files(directory)
    if not files:
        print(f"No media files found in {directory}")
        return

    cards = []
    for filepath in files:
        rel_path = os.path.relpath(filepath, directory)
        data_uri, media_type = get_thumbnail_data_uri(filepath)

        # Try to read color palette
        palette_dir = os.path.dirname(filepath)
        palette_file = os.path.join(palette_dir, 'palette.json')
        colors = []
        if os.path.exists(palette_file):
            try:
                with open(palette_file) as f:
                    palette_data = json.load(f)
                    # Find this file's colors
                    basename = os.path.basename(filepath)
                    if basename in palette_data:
                        colors = palette_data[basename].get('dominant_colors', [])[:5]
            except Exception:
                pass

        cards.append({
            'path': rel_path,
            'abs_path': filepath,
            'data_uri': data_uri,
            'media_type': media_type,
            'colors': colors,
            'size_kb': os.path.getsize(filepath) // 1024,
        })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Design Inspiration Grid</title>
<link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0a0a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', sans-serif; padding: 24px; }}
  h1 {{ font-size: 24px; font-weight: 600; margin-bottom: 8px; }}
  .stats {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
  .filters {{ display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }}
  .filter-btn {{ background: #1a1a1a; border: 1px solid #333; color: #ccc; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 13px; transition: all 0.2s; }}
  .filter-btn:hover, .filter-btn.active {{ background: #fff; color: #000; border-color: #fff; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }}
  .card {{ background: #141414; border-radius: 12px; overflow: hidden; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; position: relative; }}
  .card:hover {{ transform: translateY(-4px); box-shadow: 0 8px 32px rgba(0,0,0,0.4); }}
  .card img {{ width: 100%; display: block; }}
  .card .video-wrap {{ position: relative; overflow: hidden; }}
  .card .video-wrap video {{ width: 100%; display: block; }}
  .card .video-wrap .poster-img {{ width: 100%; display: block; }}
  .card .video-wrap .play-badge {{ position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.75); color: #fff; font-size: 10px; padding: 3px 10px; border-radius: 6px; font-weight: 600; pointer-events: none; z-index: 2; letter-spacing: 0.5px; }}
  .card .video-wrap .play-overlay {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.15); opacity: 0; transition: opacity 0.2s; z-index: 1; }}
  .card:hover .video-wrap .play-overlay {{ opacity: 1; }}
  .card .video-wrap .play-overlay svg {{ width: 48px; height: 48px; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.5)); }}
  .card .video-placeholder {{ width: 100%; aspect-ratio: 3/4; background: #1a1a1a; display: flex; align-items: center; justify-content: center; font-size: 48px; }}
  .card .info {{ padding: 10px 12px; }}
  .card .info .path {{ font-size: 11px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .card .info .size {{ font-size: 11px; color: #555; }}
  .card .colors {{ display: flex; height: 4px; }}
  .card .colors .swatch {{ flex: 1; }}
  .lightbox {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.97); z-index: 100; flex-direction: column; align-items: center; justify-content: center; padding: 40px; }}
  .lightbox.active {{ display: flex; }}
  .lightbox img {{ max-width: 90vw; max-height: 85vh; object-fit: contain; border-radius: 8px; }}
  .lightbox .video-container {{ max-width: 90vw; max-height: 85vh; width: 800px; }}
  .lightbox .video-container video {{ width: 100%; border-radius: 8px; }}
  .lightbox .close {{ position: absolute; top: 16px; right: 24px; font-size: 28px; color: #888; cursor: pointer; z-index: 101; transition: color 0.2s; }}
  .lightbox .close:hover {{ color: #fff; }}
  .lightbox .nav {{ position: absolute; top: 50%; font-size: 48px; color: #555; cursor: pointer; z-index: 101; user-select: none; transition: color 0.2s; }}
  .lightbox .nav:hover {{ color: #fff; }}
  .lightbox .nav.prev {{ left: 16px; }}
  .lightbox .nav.next {{ right: 16px; }}
  .lightbox .lb-label {{ color: #666; padding: 12px 0 0; font-size: 13px; text-align: center; }}
  .dup-badge {{ position: absolute; top: 8px; right: 8px; background: #ff4444; color: white; font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
  /* Plyr overrides for dark theme */
  .plyr {{ border-radius: 8px; }}
  .plyr--video {{ border-radius: 8px; }}
  :root {{ --plyr-color-main: #fff; }}
</style>
</head>
<body>
<h1>Design Inspiration</h1>
<div class="stats">{len(cards)} assets &middot; served from localhost</div>

<div class="filters">
  <button class="filter-btn active" onclick="filterAll()">All</button>
  <button class="filter-btn" onclick="filterBy('png')">PNG</button>
  <button class="filter-btn" onclick="filterBy('mp4')">MP4</button>
  <button class="filter-btn" onclick="filterBy('gif')">GIF</button>
</div>

<div class="grid" id="grid">
"""

    play_svg = '<svg viewBox="0 0 24 24" fill="white"><polygon points="5,3 19,12 5,21"/></svg>'

    for i, card in enumerate(cards):
        ext = Path(card['path']).suffix.lower().replace('.', '')
        color_bar = ''
        if card['colors']:
            swatches = ''.join(f'<div class="swatch" style="background:{c}"></div>' for c in card['colors'])
            color_bar = f'<div class="colors">{swatches}</div>'

        if card['media_type'] == 'video' and isinstance(card['data_uri'], dict):
            vdata = card['data_uri']
            poster_attr = f' src="{vdata["poster"]}"' if vdata.get('poster') else ''
            # Card shows poster + play overlay; hover previews the video
            media_el = f'''<div class="video-wrap" onmouseenter="previewVideo(this, '{card['path']}')" onmouseleave="stopPreview(this)">
              <img class="poster-img"{poster_attr} alt="{card['path']}">
              <div class="play-overlay">{play_svg}</div>
              <span class="play-badge">MP4</span>
            </div>'''
        elif card['data_uri'] and card['media_type'] == 'image':
            media_el = f'<img src="{card["data_uri"]}" alt="{card["path"]}" loading="lazy">'
        else:
            media_el = '<div class="video-placeholder">?</div>'

        html += f"""
  <div class="card" data-index="{i}" data-ext="{ext}" onclick="openLightbox({i})">
    {media_el}
    {color_bar}
    <div class="info">
      <div class="path" title="{card['path']}">{card['path']}</div>
      <div class="size">{card['size_kb']}KB &middot; {ext.upper()}</div>
    </div>
  </div>
"""

    html += """
</div>

<div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
  <span class="close" onclick="closeLightbox()">&times;</span>
  <span class="nav prev" onclick="navLightbox(-1, event)">&lsaquo;</span>
  <span class="nav next" onclick="navLightbox(1, event)">&rsaquo;</span>
  <div id="lb-content"></div>
  <div class="lb-label" id="lb-label"></div>
</div>

<script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
<script>
const cards = CARDS_JSON_PLACEHOLDER;
let currentIndex = 0;
let currentPlyr = null;

// Hover preview for video cards
function previewVideo(wrap, src) {
  if (wrap.querySelector('video')) return;
  const img = wrap.querySelector('.poster-img');
  const vid = document.createElement('video');
  vid.src = src;
  vid.autoplay = true;
  vid.muted = true;
  vid.loop = true;
  vid.playsInline = true;
  vid.style.width = '100%';
  vid.style.display = 'block';
  if (img) img.style.display = 'none';
  wrap.querySelector('.play-overlay').style.display = 'none';
  wrap.insertBefore(vid, wrap.firstChild);
}

function stopPreview(wrap) {
  const vid = wrap.querySelector('video');
  const img = wrap.querySelector('.poster-img');
  if (vid) { vid.pause(); vid.remove(); }
  if (img) img.style.display = 'block';
  wrap.querySelector('.play-overlay').style.display = '';
}

function filterAll() {
  document.querySelectorAll('.card').forEach(c => c.style.display = '');
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('.filter-btn').classList.add('active');
}

function filterBy(ext) {
  document.querySelectorAll('.card').forEach(c => {
    c.style.display = c.dataset.ext === ext ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.toLowerCase() === ext);
  });
}

function openLightbox(i) {
  currentIndex = i;
  showLightboxContent();
  document.getElementById('lightbox').classList.add('active');
}

function destroyCurrentPlyr() {
  if (currentPlyr) { currentPlyr.destroy(); currentPlyr = null; }
}

function closeLightbox(e) {
  if (!e || e.target.classList.contains('lightbox') || e.target.classList.contains('close')) {
    destroyCurrentPlyr();
    const vid = document.querySelector('#lb-content video');
    if (vid) vid.pause();
    document.getElementById('lightbox').classList.remove('active');
  }
}

function navLightbox(dir, e) {
  e && e.stopPropagation();
  destroyCurrentPlyr();
  const vid = document.querySelector('#lb-content video');
  if (vid) vid.pause();
  currentIndex = (currentIndex + dir + cards.length) % cards.length;
  showLightboxContent();
}

function showLightboxContent() {
  destroyCurrentPlyr();
  const card = cards[currentIndex];
  const el = document.getElementById('lb-content');
  const label = document.getElementById('lb-label');
  label.textContent = card.rel + ' (' + (currentIndex + 1) + '/' + cards.length + ')';

  if (card.type === 'video') {
    el.innerHTML = '<div class="video-container"><video id="lb-player" src="' + card.path + '" playsinline></video></div>';
    currentPlyr = new Plyr('#lb-player', {
      autoplay: true,
      loop: { active: true },
      controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'fullscreen'],
      ratio: null,
    });
  } else {
    el.innerHTML = '<img src="' + card.path + '">';
  }
}

document.addEventListener('keydown', e => {
  if (!document.getElementById('lightbox').classList.contains('active')) return;
  if (e.key === 'Escape') closeLightbox();
  if (e.key === 'ArrowLeft') navLightbox(-1);
  if (e.key === 'ArrowRight') navLightbox(1);
  if (e.key === ' ') {
    e.preventDefault();
    if (currentPlyr) currentPlyr.togglePlay();
  }
});
</script>
</body>
</html>"""

    # Build cards JSON for JS (outside f-string to avoid brace conflicts)
    cards_js = json.dumps([
        {
            'path': c['abs_path'],
            'type': c['media_type'],
            'rel': c['path'],
            'video_b64': c['data_uri'].get('video_b64', '') if isinstance(c['data_uri'], dict) else ''
        }
        for c in cards
    ])
    html = html.replace('CARDS_JSON_PLACEHOLDER', cards_js)

    with open(output_path, 'w') as f:
        f.write(html)
    print(f"Preview grid saved to {output_path} ({len(cards)} assets)")


if __name__ == '__main__':
    directory = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    output = sys.argv[2] if len(sys.argv) > 2 else os.path.join(directory, 'preview.html')
    generate_html(directory, output)
