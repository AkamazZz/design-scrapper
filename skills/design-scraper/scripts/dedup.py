#!/usr/bin/env python3
"""Detect visually similar/duplicate images using perceptual hashing."""

import os
import sys
import json
from pathlib import Path
from collections import defaultdict


def average_hash(image_path, hash_size=16):
    """Compute average perceptual hash of an image.

    Returns a hex string. Similar images produce similar hashes.
    Hamming distance < 10 = likely duplicate.
    """
    try:
        from PIL import Image
        img = Image.open(image_path).convert('L')  # Grayscale
        img = img.resize((hash_size, hash_size), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        # Convert to hex for compact storage
        hex_hash = hex(int(bits, 2))[2:].zfill(hash_size * hash_size // 4)
        return hex_hash
    except Exception as e:
        return None


def hamming_distance(hash1, hash2):
    """Compute hamming distance between two hex hashes."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return float('inf')
    b1 = bin(int(hash1, 16))[2:]
    b2 = bin(int(hash2, 16))[2:]
    # Pad to same length
    max_len = max(len(b1), len(b2))
    b1 = b1.zfill(max_len)
    b2 = b2.zfill(max_len)
    return sum(c1 != c2 for c1, c2 in zip(b1, b2))


def find_duplicates(directory, threshold=25):
    """Find visually similar images in directory.

    Args:
        directory: Path to scan
        threshold: Max hamming distance to consider as duplicate (0=identical, <15=very similar, <25=similar)

    Returns:
        List of duplicate groups
    """
    extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    files = []
    for root, dirs, filenames in os.walk(directory):
        for f in sorted(filenames):
            if Path(f).suffix.lower() in extensions:
                files.append(os.path.join(root, f))

    print(f"Hashing {len(files)} images...")
    hashes = {}
    for filepath in files:
        h = average_hash(filepath)
        if h:
            rel = os.path.relpath(filepath, directory)
            hashes[rel] = h
            sys.stdout.write('.')
            sys.stdout.flush()
    print()

    # Find pairs within threshold
    duplicates = []
    checked = set()
    files_list = list(hashes.keys())

    for i, f1 in enumerate(files_list):
        group = [f1]
        for f2 in files_list[i + 1:]:
            pair_key = (f1, f2)
            if pair_key in checked:
                continue
            checked.add(pair_key)

            dist = hamming_distance(hashes[f1], hashes[f2])
            if dist <= threshold:
                group.append(f2)

        if len(group) > 1:
            # Check if any member is already in a found group
            already_grouped = False
            for existing in duplicates:
                if any(m in existing['files'] for m in group):
                    existing['files'] = list(set(existing['files'] + group))
                    already_grouped = True
                    break
            if not already_grouped:
                duplicates.append({
                    'files': group,
                    'distance': 'similar' if threshold > 15 else 'near-identical',
                })

    # Save results
    result = {
        'total_files': len(files),
        'total_hashed': len(hashes),
        'duplicate_groups': duplicates,
        'hashes': hashes,
    }

    output_path = os.path.join(directory, 'duplicates.json')
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    if duplicates:
        print(f"\nFound {len(duplicates)} groups of similar images:")
        for i, group in enumerate(duplicates, 1):
            print(f"\n  Group {i} ({group['distance']}):")
            for f in group['files']:
                print(f"    - {f}")
    else:
        print("\nNo duplicates found.")

    return result


if __name__ == '__main__':
    directory = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    threshold = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    find_duplicates(directory, threshold)
