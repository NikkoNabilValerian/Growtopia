"""Salin pilihan dari config.py ke dropdown `target` di .github/workflows/backfill.yml.

GitHub tidak bisa membaca config.py saat formulir "Run workflow" dibuka, jadi daftar pilihan di
workflow harus disalin. Jalankan skrip ini SETIAP KALI kamu menambah/mengubah item, kelompok
channel, atau preset di config.py, lalu commit kedua file.

    python scraper/sync_workflow.py            # tulis ulang pilihan di backfill.yml
    python scraper/sync_workflow.py --check    # hanya periksa; kode keluar 1 bila belum sinkron
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection import options  # noqa: E402

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "backfill.yml"
BEGIN, END = "# BEGIN-OPTIONS", "# END-OPTIONS"


def main() -> int:
    check = "--check" in sys.argv
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        b = next(i for i, l in enumerate(lines) if BEGIN in l)
        e = next(i for i, l in enumerate(lines) if END in l)
    except StopIteration:
        print(f"Penanda {BEGIN} / {END} tidak ditemukan di {WORKFLOW}")
        return 1
    indent = lines[b][: len(lines[b]) - len(lines[b].lstrip())]
    new_body = [f'{indent}- "{opt}"\n' for opt in options()]
    if lines[b + 1 : e] == new_body:
        print("Dropdown sudah sinkron dengan config.py.")
        return 0
    if check:
        print("Dropdown BELUM sinkron dengan config.py. Jalankan: python scraper/sync_workflow.py")
        return 1
    lines[b + 1 : e] = new_body
    WORKFLOW.write_text("".join(lines), encoding="utf-8")
    print("Dropdown diperbarui. Pilihan:\n  " + "\n  ".join(options()) + "\nJangan lupa commit dan push backfill.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())