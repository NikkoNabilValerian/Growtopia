-- Skema lengkap (instalasi baru). Untuk database yang SUDAH ada, jalankan
-- migrations/002_multi_item_and_analysis.sql sebagai gantinya.
--
-- Harga disimpan dalam BGL. 1 BGL = 100 DL = 10.000 WL, jadi 1 WL = 0.0001 BGL.

-- Ringkasan harga harian (permanen). Satu baris per item per hari.
CREATE TABLE IF NOT EXISTS daily_item_prices (
    id             BIGSERIAL PRIMARY KEY,
    item_name      VARCHAR(100)   NOT NULL,
    date           DATE           NOT NULL,
    -- Harga median (utama): gabungan, per sisi, dan 1-suara-per-penulis
    median_price   NUMERIC(14, 4) NOT NULL,   -- gabungan buy + sell
    buy_median     NUMERIC(14, 4),            -- NULL = postingan sisi itu < 3
    sell_median    NUMERIC(14, 4),
    author_median  NUMERIC(14, 4),            -- median dari median tiap penulis (anti-spam)
    -- Statistik pendukung (gabungan)
    avg_price      NUMERIC(14, 4) NOT NULL,
    min_price      NUMERIC(14, 4) NOT NULL,
    max_price      NUMERIC(14, 4) NOT NULL,
    -- Jumlah postingan
    total_volume   INT            NOT NULL,
    buy_volume     INT            NOT NULL DEFAULT 0,
    sell_volume    INT            NOT NULL DEFAULT 0,
    -- Jumlah penulis unik (0 = belum dihitung pada data lama)
    total_authors  INT            NOT NULL DEFAULT 0,
    buy_authors    INT            NOT NULL DEFAULT 0,
    sell_authors   INT            NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_item_date UNIQUE (item_name, date)
);
CREATE INDEX IF NOT EXISTS idx_item_date ON daily_item_prices (item_name, date DESC);

-- Catatan hari yang sudah selesai di-scrape, PER ITEM, agar tidak dikerjakan dua kali.
CREATE TABLE IF NOT EXISTS scrape_log (
    item_name  VARCHAR(100) NOT NULL,
    date       DATE         NOT NULL,
    offers     INT          NOT NULL DEFAULT 0,
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    channels_key TEXT,                       -- sidik jari daftar channel yang dibaca (lihat channels.py)
    PRIMARY KEY (item_name, date)
);

-- Metadata item (diisi otomatis oleh pipeline dari scraper/items.py).
CREATE TABLE IF NOT EXISTS items (
    item_name  VARCHAR(100) PRIMARY KEY,
    label      TEXT NOT NULL,
    sort_order INT  NOT NULL DEFAULT 0
);

-- Kalender event / kejadian penting. Diisi manual (Table Editor atau import CSV).
-- start_date = end_date -> ditampilkan sebagai garis vertikal (mis. perubahan sistem).
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'event',   -- 'event' | 'structural'
    notes      TEXT,
    CHECK (end_date >= start_date)
);

-- Keluaran model analisis (diisi oleh skrip sinyal harian; kosong sampai model aktif).
CREATE TABLE IF NOT EXISTS item_signals (
    item_name VARCHAR(100) NOT NULL,
    date      DATE         NOT NULL,
    predicted NUMERIC(14, 4),          -- harga prediksi model (BGL)
    resid_z   NUMERIC(8, 3),
    spread_z  NUMERIC(8, 3),
    signal    TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD', 'NO_TRADE')),
    reason    TEXT,
    PRIMARY KEY (item_name, date)
);

-- Daftar item untuk dropdown (urut sesuai items.py, lalu yang paling ramai).
CREATE OR REPLACE VIEW item_list WITH (security_invoker = true) AS
SELECT p.item_name,
       COALESCE(i.label, p.item_name)  AS label,
       COALESCE(i.sort_order, 999)     AS sort_order,
       SUM(p.total_volume)::INT        AS total_volume,
       MIN(p.date)                     AS first_date,
       MAX(p.date)                     AS last_date
FROM daily_item_prices p
LEFT JOIN items i ON i.item_name = p.item_name
GROUP BY p.item_name, i.label, i.sort_order
ORDER BY COALESCE(i.sort_order, 999), SUM(p.total_volume) DESC;

-- Keamanan: website (publishable/anon key) hanya boleh MEMBACA.
-- Scraper memakai secret key, yang melewati RLS.
ALTER TABLE daily_item_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE items             ENABLE ROW LEVEL SECURITY;
ALTER TABLE events            ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_signals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_log        ENABLE ROW LEVEL SECURITY;   -- tanpa policy: hanya scraper

CREATE POLICY "public read" ON daily_item_prices FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON items             FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON events            FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON item_signals      FOR SELECT TO anon USING (true);

GRANT SELECT ON item_list TO anon;