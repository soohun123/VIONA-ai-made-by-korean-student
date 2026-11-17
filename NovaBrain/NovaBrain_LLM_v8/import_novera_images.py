"""Import user-selected local photos without changing source files."""
import argparse
import collections
import csv
import hashlib
import html
import json
import random
import re
import shutil
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from training_store import ROOT, DATASETS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    identifier = uuid.uuid4().hex
    output = ROOT / 'data/training/imports' / identifier
    (output / 'images').mkdir(parents=True, exist_ok=False)
    metadata_file = source.parent / 'metadata.csv'
    metadata = {}
    if metadata_file.exists():
        shutil.copy2(metadata_file, output / 'source-metadata.csv')
        with metadata_file.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                key = row.get('filename', '').replace('\\', '/').casefold()
                metadata[key] = row
    records, excluded, hashes = [], [], {}
    files = sorted(p for p in source.rglob('*') if p.is_file())
    for index, path in enumerate(files):
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
            excluded.append({'file': str(path), 'reason': 'unsupported extension'})
            continue
        try:
            raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as original:
                if original.width * original.height > 16000000:
                    raise ValueError('Image exceeds 16 megapixels')
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGB')
                if min(image.size) < 32:
                    raise ValueError('Image too small')
                pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                if pixel_hash in hashes:
                    excluded.append({'file': str(path), 'reason': 'duplicate pixels', 'same_as': hashes[pixel_hash]})
                    continue
                relative = path.relative_to(source)
                parts = relative.parts
                category = parts[0] if len(parts) > 1 else 'other'
                brand = parts[1] if len(parts) > 2 else ''
                row = metadata.get(path.relative_to(source.parent).as_posix().casefold(), {})
                credit = html.unescape(re.sub('<[^>]*>', '', row.get('credit', '')))
                object_name = 'aircraft' if category == 'aircraft' else 'car' if category == 'cars' else 'vehicle'
                caption = ('a photograph of a ' + brand + ' ' + object_name + '. ' + credit)[:300].strip()
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                destination = output / 'images' / (pixel_hash + '.jpg')
                image.save(destination, format='JPEG', quality=92)
            hashes[pixel_hash] = str(path)
            records.append({'image': str(destination.relative_to(ROOT)), 'relative_to_root': True,
                'caption': caption, 'category': category, 'manufacturer': brand,
                'source_file': str(path), 'source_sha256': raw_sha,
                'pixel_sha256': pixel_hash, 'attribution': row,
                'metadata_sha_matches': row.get('sha256') == raw_sha if row else None,
                'caption_review': 'folder/metadata-derived, not manually verified'})
        except Exception as exc:
            excluded.append({'file': str(path), 'reason': type(exc).__name__ + ': ' + str(exc)})
        if (index + 1) % 200 == 0:
            print('Imported', index + 1, '/', len(files), flush=True)
    if not records:
        raise ValueError('No usable photos')
    groups = collections.defaultdict(list)
    for record in records:
        groups[(record['category'], record['manufacturer'])].append(record)
    train, validation = [], []
    for group in groups.values():
        random.Random(42).shuffle(group)
        count = max(1, len(group) // 10) if len(group) >= 10 else 0
        for index, record in enumerate(group):
            record['split'] = 'validation' if index < count else 'train'
            (validation if index < count else train).append(record)
    random.Random(42).shuffle(train)
    random.Random(43).shuffle(validation)
    chunks = [train[i:i + 300] for i in range(0, len(train), 300)]
    batches = []
    for index, batch in enumerate(chunks):
        held_out = validation[index::len(chunks)]
        dataset_id = 'novera-' + identifier[:12] + '-' + str(index + 1)
        directory = DATASETS / dataset_id
        directory.mkdir(parents=True, exist_ok=False)
        dataset = {'id': dataset_id, 'name': 'NOVERA cars and aircraft ' + str(index + 1),
                   'source': str(source), 'license': 'See copied source-metadata.csv; review status retained',
                   'records': batch + held_out}
        (directory / 'dataset.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding='utf-8')
        batches.append({'dataset_id': dataset_id, 'steps': len(batch),
                        'train_images': len(batch), 'held_out_images': len(held_out)})
    report = {'import_id': identifier, 'source': str(source), 'source_file_count': len(files),
              'unique_images': len(records), 'train_images': len(train), 'held_out_images': len(validation),
              'groups': {'/'.join(k): len(v) for k, v in groups.items()}, 'batches': batches,
              'records': records, 'excluded': excluded}
    (output / 'import.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('IMPORT_MANIFEST', output / 'import.json', flush=True)


if __name__ == '__main__':
    main()
