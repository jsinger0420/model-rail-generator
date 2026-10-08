"""Built-in rail presets and the user preset library.  Pure Python (no bpy).

Built-in heights are exact (code / 1000 inch).  The other dimensions use
typical model-rail proportions and are a starting point: rail from different
manufacturers varies, so measure yours with calipers and save a custom preset
when accuracy matters.
"""

from __future__ import annotations

import json
import os
import tempfile

from .profile import RailProfile, profile_from_code

PRESET_FILE_VERSION = 1


def _builtin() -> dict[str, RailProfile]:
    """Build the built-in code presets, ordered largest rail first."""
    specs = [
        (332, "G scale (LGB / Aristo / USA Trains brass & steel)"),
        (250, "G / Fn3 fine-scale, 1:32 / 1:29"),
        (215, "O scale heavy rail"),
        (148, "O scale (Atlas O, 3-rail & 2-rail)"),
        (125, "O scale 2-rail, S scale (American Flyer hi-rail)"),
        (100, "HO standard (Atlas, Bachmann, Peco Streamline HO)"),
        (83, "HO prototype-heavy mainline (Atlas, Walthers/Shinohara)"),
        (70, "HO branchline, S fine-scale, On30"),
        (55, "N scale (Atlas Code 55, Peco Code 55)"),
        (40, "N fine-scale / HO light, Z"),
    ]
    out = {}
    for code, desc in specs:
        p = profile_from_code(code, description=desc)
        out[p.name] = p
    # Code 80 is the long-standing N scale standard rail.
    p = profile_from_code(80, description="N scale standard (Atlas, Kato-style sectional)")
    out[p.name] = p
    return dict(sorted(out.items(), key=lambda kv: -kv[1].height))


BUILTIN_PRESETS: dict[str, RailProfile] = _builtin()


class PresetError(Exception):
    """Raised when a preset can't be saved, deleted or loaded (the message says why)."""
    pass


class PresetLibrary:
    """Built-in presets plus user presets stored in a JSON file.

    Built-ins are read-only; user presets may not reuse a built-in name.
    """

    def __init__(self, user_file: str | None = None):
        """Load built-ins plus user presets from ``user_file`` (None keeps them in memory only)."""
        self.user_file = user_file
        self._user: dict[str, RailProfile] = {}
        self.reload()

    # ----------------------------------------------------------- queries
    def names(self) -> list[str]:
        """All preset names: built-ins first, then user presets alphabetically."""
        return list(BUILTIN_PRESETS) + sorted(self._user)

    def builtin_names(self) -> list[str]:
        """Names of the built-in presets."""
        return list(BUILTIN_PRESETS)

    def user_names(self) -> list[str]:
        """Names of the user presets, sorted."""
        return sorted(self._user)

    def is_builtin(self, name: str) -> bool:
        """True if ``name`` is a built-in preset."""
        return name in BUILTIN_PRESETS

    def exists(self, name: str) -> bool:
        """True if a built-in or user preset is called ``name``."""
        return name in BUILTIN_PRESETS or name in self._user

    def get(self, name: str) -> RailProfile:
        """Return a *copy* of the preset (safe to modify)."""
        if name in BUILTIN_PRESETS:
            return BUILTIN_PRESETS[name].copy()
        if name in self._user:
            return self._user[name].copy()
        raise KeyError(f"No rail preset named '{name}'")

    def all(self) -> dict[str, RailProfile]:
        """Every preset as a name -> RailProfile dict (copies)."""
        return {n: self.get(n) for n in self.names()}

    # ---------------------------------------------------------- mutation
    def save(self, profile: RailProfile, overwrite: bool = True) -> None:
        """Validate ``profile`` and save it as a user preset under its name."""
        name = (profile.name or "").strip()
        if not name:
            raise PresetError("Preset name cannot be empty")
        if name in BUILTIN_PRESETS:
            raise PresetError(f"'{name}' is a built-in preset; choose another name")
        if name in self._user and not overwrite:
            raise PresetError(f"Preset '{name}' already exists")
        errs = profile.validate()
        if errs:
            raise PresetError("; ".join(errs))
        self._user[name] = profile.copy(name=name)
        self._write()

    def delete(self, name: str) -> None:
        """Delete the user preset ``name`` (built-ins can't be deleted)."""
        if name in BUILTIN_PRESETS:
            raise PresetError("Built-in presets cannot be deleted")
        if name not in self._user:
            raise KeyError(f"No user preset named '{name}'")
        del self._user[name]
        self._write()

    # ------------------------------------------------------------- file io
    def reload(self) -> None:
        """Re-read user presets from disk, skipping any bad entries."""
        self._user = {}
        if not self.user_file or not os.path.isfile(self.user_file):
            return
        try:
            with open(self.user_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as ex:
            print(f"[Model Rail] Could not read presets file {self.user_file}: {ex}")
            return
        for d in data.get("presets", []):
            try:
                p = RailProfile.from_dict(d)
                if p.name and p.name not in BUILTIN_PRESETS:
                    self._user[p.name] = p
            except (TypeError, ValueError) as ex:
                print(f"[Model Rail] Skipping bad preset {d!r}: {ex}")

    def export_json(self, path: str, names: list[str] | None = None) -> None:
        """Write the given presets (default: all user presets) to a file."""
        names = names or self.user_names()
        data = {"version": PRESET_FILE_VERSION, "presets": [self.get(n).to_dict() for n in names]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def import_json(self, path: str, overwrite: bool = True) -> list[str]:
        """Merge presets from a file; returns the names imported."""
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        done = []
        for d in data.get("presets", []):
            p = RailProfile.from_dict(d)
            if p.name in BUILTIN_PRESETS or (p.name in self._user and not overwrite):
                continue
            if p.is_valid():
                self._user[p.name] = p
                done.append(p.name)
        self._write()
        return done

    def _write(self) -> None:
        """Save user presets to the JSON file atomically, so a crash can't corrupt it."""
        if not self.user_file:
            return
        os.makedirs(os.path.dirname(self.user_file) or ".", exist_ok=True)
        data = {"version": PRESET_FILE_VERSION,
                "presets": [self._user[n].to_dict() for n in sorted(self._user)]}
        # atomic write so a crash can't corrupt the user's presets
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.user_file) or ".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.user_file)
