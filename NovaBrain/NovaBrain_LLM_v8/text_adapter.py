"""Optional validated LoRA for the original local Qwen only; frozen releases stay separate."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACTIVE = ROOT / 'data/text-training/active-adapter.json'


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(2**20), b''):
            digest.update(block)
    return digest.hexdigest()


def resolve_adapter(model):
    if Path(model).resolve() != (ROOT / 'model.gguf').resolve():
        return None, None
    override = os.getenv('NOVABRAIN_TEXT_LORA')
    if override == 'off':
        return None, None
    if override:
        metadata = {'path': override, 'name': 'candidate LoRA', 'candidate': True}
    elif ACTIVE.exists():
        metadata = json.loads(ACTIVE.read_text(encoding='utf-8'))
        if not metadata.get('enabled'):
            return None, None
    else:
        return None, None
    path = (ROOT / metadata['path']).resolve()
    if not path.is_relative_to(ROOT) or path.suffix != '.gguf' or not path.is_file():
        raise ValueError('Text adapter must be a GGUF file inside this installation')
    digest = file_hash(path)
    if metadata.get('sha256') and metadata['sha256'] != digest:
        raise ValueError('Text adapter checksum changed')
    if metadata.get('base_sha256') and file_hash(Path(model)) != metadata['base_sha256']:
        raise ValueError('Base model changed; adapter disabled')
    return str(path), {'name': metadata['name'], 'sha256': digest, 'candidate': bool(override)}
