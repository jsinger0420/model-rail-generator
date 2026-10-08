"""Build an installable add-on zip:  python build.py  ->  dist/model_rail_generator-<version>.zip

Works for Blender 4.2+ (Install from Disk) and 3.6-4.1 (Add-ons > Install).
"""
import os
import tomllib
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = "model_rail_generator"


def main():
    with open(os.path.join(ROOT, PKG, "blender_manifest.toml"), "rb") as fh:
        version = tomllib.load(fh)["version"]
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"{PKG}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, PKG)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for f in sorted(filenames):
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(dirpath, f)
                zf.write(full, os.path.relpath(full, ROOT))
    print(out)


if __name__ == "__main__":
    main()
