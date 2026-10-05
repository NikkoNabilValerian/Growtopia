-- 004: catat "sidik jari" daftar channel di scrape_log, supaya perubahan isi kelompok channel
-- (lihat scraper/channels.py) otomatis membuat hari-hari terkait dikerjakan ulang.
-- Aman dijalankan berulang. Jalankan SEBELUM memakai pipeline versi kelompok channel.
-- Setelah itu jalankan sekali:  python pipeline.py --stamp-log
ALTER TABLE scrape_log ADD COLUMN IF NOT EXISTS channels_key TEXT;