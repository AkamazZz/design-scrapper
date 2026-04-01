#!/usr/bin/env python3
"""Extract dominant colors from design screenshots. Outputs palette.json per directory."""

import os
import sys
import json
from pathlib import Path
from collections import Counter


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


def color_distance(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def cluster_colors(pixels, n_colors=6, min_distance=40):
    """Simple color clustering by quantization + frequency."""
    # Quantize to reduce color space
    quantized = []
    for r, g, b in pixels:
        qr, qg, qb = (r // 16) * 16, (g // 16) * 16, (b // 16) * 16
        quantized.append((qr, qg, qb))

    # Count frequencies
    freq = Counter(quantized)

    # Pick top colors that are visually distinct
    candidates = freq.most_common(50)
    selected = []
    for color, count in candidates:
        if len(selected) >= n_colors:
            break
        # Skip near-black and near-white (usually backgrounds)
        brightness = sum(color) / 3
        if brightness < 15 or brightness > 245:
            continue
        # Check distance from already selected
        too_close = False
        for s in selected:
            if color_distance(color, s[0]) < min_distance:
                too_close = True
                break
        if not too_close:
            selected.append((color, count))

    # If we don't have enough, relax the brightness filter
    if len(selected) < 3:
        for color, count in candidates:
            if len(selected) >= n_colors:
                break
            too_close = False
            for s in selected:
                if color_distance(color, s[0]) < min_distance:
                    too_close = True
                    break
            if not too_close:
                selected.append((color, count))

    return selected


def extract_palette(image_path, n_colors=6):
    """Extract dominant colors from an image."""
    try:
        from PIL import Image
        img = Image.open(image_path).convert('RGB')
        # Resize for speed
        img.thumbnail((150, 300), Image.LANCZOS)
        pixels = list(img.getdata())

        colors = cluster_colors(pixels, n_colors)

        total = len(pixels)
        result = {
            'dominant_colors': [rgb_to_hex(*c) for c, _ in colors],
            'color_percentages': {
                rgb_to_hex(*c): round(count / total * 100, 1)
                for c, count in colors
            },
            'brightness': round(sum(sum(p) / 3 for p in pixels) / total, 1),
            'is_dark_mode': sum(sum(p) / 3 for p in pixels) / total < 128,
        }
        return result
    except Exception as e:
        return {'error': str(e)}


def process_directory(directory):
    """Extract palettes for all images in directory, save palette.json."""
    extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    results = {}

    for root, dirs, files in os.walk(directory):
        dir_results = {}
        for f in sorted(files):
            if Path(f).suffix.lower() in extensions:
                filepath = os.path.join(root, f)
                print(f"  Extracting: {os.path.relpath(filepath, directory)}")
                palette = extract_palette(filepath)
                dir_results[f] = palette

        if dir_results:
            palette_path = os.path.join(root, 'palette.json')
            with open(palette_path, 'w') as pf:
                json.dump(dir_results, pf, indent=2)
            print(f"  -> Saved {palette_path}")
            results.update({os.path.relpath(os.path.join(root, k), directory): v for k, v in dir_results.items()})

    # Summary
    dark_count = sum(1 for v in results.values() if v.get('is_dark_mode'))
    light_count = len(results) - dark_count
    all_colors = []
    for v in results.values():
        all_colors.extend(v.get('dominant_colors', []))

    summary = {
        'total_files': len(results),
        'dark_mode_count': dark_count,
        'light_mode_count': light_count,
        'most_common_colors': [c for c, _ in Counter(all_colors).most_common(10)],
    }

    summary_path = os.path.join(directory, 'color_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary: {len(results)} files analyzed, {dark_count} dark mode, {light_count} light mode")
    print(f"Top colors: {', '.join(summary['most_common_colors'][:5])}")
    return summary


if __name__ == '__main__':
    directory = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    process_directory(directory)
