"""Stage the reviewed Forge release in a prebuilt NOVERA desktop distribution."""
import argparse
import hashlib
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT / "forge-534"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, data):
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage(app, pack, portable):
    release = json.loads((RELEASE / "release.json").read_text(encoding="utf-8"))
    adapter = RELEASE / release["adapter"]["file"]
    absolute_base = pack / "models/qwen/model.gguf"
    if digest(adapter) != release["adapter"]["sha256"] or digest(absolute_base) != release["base"]["sha256"]:
        raise ValueError("Forge adapter or base model checksum mismatch")
    bundle = app / "_internal"
    manifest = bundle / "assets/model-sources.json"
    catalog = json.loads(manifest.read_text(encoding="utf-8"))
    relative = f"adapters/text/{release['adapter']['sha256']}.gguf"
    target = pack / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
        shutil.copyfile(adapter, temporary)
        temporary.replace(target)
    if digest(target) != release["adapter"]["sha256"]:
        raise ValueError("Model pack contains a corrupt adapter")
    row = {
        "id": "qwen-viona", "name": "NOVERA Forge 1.5B · 534 steps", "kind": "text",
        "relative": "models/qwen/model.gguf", "sha256": release["base"]["sha256"],
        "size": absolute_base.stat().st_size, "license": "Apache-2.0",
        "text_adapter": {"name": "NOVERA Forge 1.5B · 534 steps", "relative": relative,
                         "sha256": release["adapter"]["sha256"], "base_sha256": release["base"]["sha256"]},
    }
    if portable:
        catalog = {"models": [row], "adapters": []}
        # An empty project reference prevents the distributable from following a workstation.
        write(bundle/"assets/website-source.json", {})
    else:
        catalog["models"] = [row, *(m for m in catalog["models"] if m["id"] != row["id"])]
    shutil.copyfile(RELEASE/"NOTICE.txt", bundle/"licenses/NOVERA-Forge-NOTICE.txt")
    shutil.copyfile(RELEASE/"LICENSE-Qwen.txt", bundle/"licenses/Qwen-LICENSE.txt")
    shutil.copyfile(ROOT/"licenses/DISTRIBUTION.txt", bundle/"licenses/DISTRIBUTION.txt")
    write(manifest, catalog)
    write(app/"app-version.json", {"app_id": "NOVERA_AI_Desktop", "version": release["desktop_version"]})
    print(row["text_adapter"]["sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--model-pack", required=True, type=Path)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    stage(args.app, args.model_pack, args.portable)
