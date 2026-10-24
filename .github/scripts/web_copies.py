"""Make the web-sized copies the gallery loads, and record each photo's shape.

For every photo in the site's photo folder this writes web/<photo name>-<width>.webp at the widths
the page asks for, and lists the photo's width, height and a short fingerprint in web/sizes.json.
A photo whose fingerprint hasn't changed is skipped, so a run after one upload only does that
photo; copies of photos that are gone are removed. GitHub runs this after every upload
(.github/workflows/web-copies.yml), and it can be run by hand from the repository's root.
"""

import hashlib
import json
import sys
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parents[2]
PHOTOS = ROOT                         # the page's GITHUB_FOLDER; empty there means the root
WEB = ROOT / 'web'
WIDTHS = (400, 600, 800, 1000, 1600)  # the page's THUMB_WIDTHS, then 1600 for the full-screen viewer
EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}
QUALITY = 80


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def copy_names(name):
    return [f'{name}-{w}.webp' for w in WIDTHS]


def make_copies(path):
    with Image.open(path) as im:
        icc = im.info.get('icc_profile')  # kept, so Display P3 photos keep their colours
        im = ImageOps.exif_transpose(im)

        alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        im = im.convert('RGBA' if alpha else 'RGB')

        if alpha and im.getchannel('A').getextrema() == (255, 255):
            im = im.convert('RGB')

        width, height = im.size

        # never wider than the photo itself
        for w in WIDTHS:
            size = (w, round(height * w / width)) if width > w else im.size
            small = im.resize(size, Image.LANCZOS, reducing_gap=3.0) if size != im.size else im
            small.save(WEB / f'{path.name}-{w}.webp', 'WEBP', quality=QUALITY, method=6, icc_profile=icc)

    return width, height


def main():
    WEB.mkdir(exist_ok=True)
    sizes_file = WEB / 'sizes.json'

    try:
        sizes = json.loads(sizes_file.read_text())
    except (FileNotFoundError, ValueError):
        sizes = {}

    photos = sorted(p for p in PHOTOS.iterdir() if p.is_file() and p.suffix.lower() in EXTS)
    keep = set()
    made = 0

    for path in photos:
        name = path.name
        keep.update(copy_names(name))
        v = fingerprint(path)
        entry = sizes.get(name)

        if entry and entry.get('v') == v and all((WEB / c).exists() for c in copy_names(name)):
            continue

        try:
            w, h = make_copies(path)
        except Exception as e:  # one unreadable file shouldn't stop the rest; the page loads it through wsrv
            print(f'Skipped {name}: {e}', file=sys.stderr)
            sizes.pop(name, None)
            continue

        sizes[name] = {'w': w, 'h': h, 'v': v}
        made += 1
        print(f'Made copies of {name} ({w}x{h})')

    names = {p.name for p in photos}

    for name in [n for n in sizes if n not in names]:
        del sizes[name]
        print(f'Removed copies of {name}')

    for f in WEB.glob('*.webp'):
        if f.name not in keep:
            f.unlink()

    # one photo per line, in name order, so a change shows as a one-line difference
    lines = [f'  {json.dumps(n)}: {json.dumps(sizes[n])}' for n in sorted(sizes)]
    sizes_file.write_text('{\n' + ',\n'.join(lines) + '\n}\n')

    print(f'{made} photo(s) updated, {len(sizes)} listed in web/sizes.json')


if __name__ == '__main__':
    main()
