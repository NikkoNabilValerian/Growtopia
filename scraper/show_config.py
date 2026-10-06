"""Lihat atau periksa konfigurasi tanpa token apa pun (hanya stdlib).

    python show_config.py                                 # tampilkan semua item, channel, preset
    python show_config.py --check "growscan,preset:harian"   # validasi pilihan; keluar kode 1 bila salah
"""
import sys


def main() -> int:
    args = sys.argv[1:]
    try:  # kesalahan penulisan di config.py muncul saat impor; tampilkan sebagai pesan ramah
        import offer_parser  # noqa: F401  (memeriksa alias ganda dan alias lemah)
        from selection import describe, resolve_selection, validate
    except ValueError as e:
        print(f"KONFIGURASI SALAH: {e}")
        return 1
    problems = validate()
    if problems:
        print("KONFIGURASI SALAH:\n  - " + "\n  - ".join(problems))
        return 1
    if args and args[0] == "--check":
        spec = args[1] if len(args) > 1 else ""
        try:
            chosen = resolve_selection(spec)
        except ValueError as e:
            print(f"PILIHAN SALAH: {e}")
            return 1
        if not chosen:
            print("PILIHAN SALAH: tidak ada item aktif. Atur <item>_aktif = True di config.py atau sebut namanya.")
            return 1
        print(f"OK, item yang akan diproses: {', '.join(chosen)}")
        return 0
    print(describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())