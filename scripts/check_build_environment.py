"""Fail before packaging if native wheels do not match the build interpreter."""
import importlib
import importlib.metadata
import sys

from packaging.tags import parse_tag, sys_tags


def main():
    supported = set(sys_tags())
    errors = []
    for distribution in importlib.metadata.distributions():
        tags = set()
        for line in (distribution.read_text("WHEEL") or "").splitlines():
            if line.startswith("Tag: "):
                tags.update(parse_tag(line[5:]))
        if tags and not tags.intersection(supported):
            errors.append(f"{distribution.metadata['Name']}=={distribution.version}: incompatible wheel {tags}")
    if not errors:
        for module in ("cryptography.hazmat.bindings._rust", "_cffi_backend", "aiohttp", "frozenlist", "multidict", "yarl", "google.genai", "groq"):
            try:
                importlib.import_module(module)
            except Exception as exc:
                errors.append(f"{module}: {exc}")
    if errors:
        print("Build environment is incompatible with Python", sys.version.split()[0])
        for error in errors:
            print(" -", error)
        print("Reinstall matching wheels in .venv before building.")
        return 1
    print("Build environment OK: Python", sys.version.split()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
