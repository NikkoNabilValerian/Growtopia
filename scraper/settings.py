"""Membaca config.py (variabel biasa) dan mengubahnya menjadi struktur yang dipakai scraper:
ITEMS, PRESETS, CHANNEL_NAMES. Hanya stdlib. Tidak perlu diedit."""
from __future__ import annotations

import re

import config as _cfg


class ConfigError(ValueError):
    """Kesalahan penulisan di config.py (pesannya menyebut nama variabel yang salah)."""


def _values() -> dict:
    return {k: v for k, v in vars(_cfg).items() if not k.startswith("_")}


def _split(value, where: str) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[,\n]", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(x) for x in value]
    else:
        raise ConfigError(f"{where}: isinya harus teks, mis. \"a, b\" (bukan {value!r})")
    return [p.strip().lower() for p in parts if p.strip()]


def _flatten(value) -> list:
    if isinstance(value, (list, tuple, set)):
        return [y for x in value for y in _flatten(x)]
    return [value]


def _channel_ids(value, where: str) -> list[int]:
    ids: list[int] = []
    for x in _flatten(value):
        if isinstance(x, bool):
            raise ConfigError(f"{where}: ID channel harus angka")
        if isinstance(x, int):
            ids.append(x)
        elif isinstance(x, str) and x.strip().isdigit():
            ids.append(int(x.strip()))
        else:
            raise ConfigError(f"{where}: ID channel harus angka (Copy Channel ID), bukan {x!r}")
    return list(dict.fromkeys(ids))


def load():
    v = _values()
    items: dict[str, dict] = {}
    for name in v:
        m = re.fullmatch(r"(.+)_alias", name)
        if not m:
            continue
        prefix = m.group(1)
        key = prefix.lower()
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise ConfigError(f"{name}: awalan item hanya boleh huruf, angka, dan garis bawah")
        if key in items:
            raise ConfigError(f"Item '{key}' didefinisikan dua kali (huruf besar/kecil dianggap sama)")

        aliases = _split(v[name], name)
        if not aliases:
            raise ConfigError(f"{name}: daftar alias kosong")
        weak = _split(v.get(f"{prefix}_alias_lemah", ""), f"{prefix}_alias_lemah")
        for w in weak:
            if w not in aliases:
                raise ConfigError(f"{prefix}_alias_lemah: '{w}' harus juga ada di {name}")
        strong = [a for a in aliases if a not in weak]

        cfg: dict = {
            "label": str(v.get(f"{prefix}_nama") or prefix.upper()),
            "aliases": aliases,
            "weak_aliases": weak,
            "bare_dl_min": float(v.get(f"{prefix}_batas_dl", 50)),
            "enabled": bool(v.get(f"{prefix}_aktif", True)),
            "noise": [],
            "channel_ids": None,
        }
        nums = _split(v.get(f"{prefix}_nama_angka", ""), f"{prefix}_nama_angka")
        if nums and strong:
            cfg["noise"] = [
                r"(" + "|".join(re.escape(a) for a in strong) + r")\s*(?:" + "|".join(re.escape(n) for n in nums) + r")"
            ]
        if f"{prefix}_channel" in v:
            cfg["channel_ids"] = _channel_ids(v[f"{prefix}_channel"], f"{prefix}_channel")
        if f"{prefix}_harga" in v and v[f"{prefix}_harga"] is not None:
            cfg["seed_anchor_bgl"] = float(v[f"{prefix}_harga"])
        items[key] = cfg

    presets: dict[str, list[str]] = {}
    for name, value in v.items():
        m = re.fullmatch(r"PRESET_(.+)", name)
        if m:
            presets[m.group(1).lower()] = _split(value, name)

    # nama variabel untuk setiap ID channel yang dipakai (untuk tampilan)
    names: dict[int, str] = {}
    for name, value in v.items():
        if isinstance(value, int) and not isinstance(value, bool) and value >= 10**15:
            names.setdefault(value, name)
    return items, presets, names


ITEMS, PRESETS, CHANNEL_NAMES = load()