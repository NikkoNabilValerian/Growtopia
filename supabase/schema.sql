-- Ringkasan harga harian (permanen). Satu baris per item per hari.
-- Harga disimpan dalam BGL. 1 BGL = 100 DL = 10.000 WL, jadi 1 WL = 0.0001 BGL.
-- NUMERIC(14,4) dipakai agar harga murah seperti "20 WL" tidak dibulatkan menjadi 0.00.
CREATE TABLE IF NOT EXISTS daily_item_prices (
    id           BIGSERIAL PRIMARY KEY,
    item_name    VARCHAR(100)   NOT NULL,
    date         DATE           NOT NULL,
    -- Harga median (utama untuk chart): gabungan, lalu per sisi
    median_price NUMERIC(14, 4) NOT NULL,   -- gabungan buy + sell
    buy_median   NUMERIC(14, 4),            -- NULL = postingan hari itu terlalu sedikit
    sell_median  NUMERIC(14, 4),
    -- Statistik pendukung (gabungan)
    avg_price    NUMERIC(14, 4) NOT NULL,
    min_price    NUMERIC(14, 4) NOT NULL,
    max_price    NUMERIC(14, 4) NOT NULL,
    -- Jumlah postingan yang terekam
    total_volume INT            NOT NULL,
    buy_volume   INT            NOT NULL DEFAULT 0,
    sell_volume  INT            NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_item_date UNIQUE (item_name, date)
);

CREATE INDEX IF NOT EXISTS idx_item_date
    ON daily_item_prices (item_name, date DESC);

-- Daftar item untuk dropdown (diurutkan dari yang paling ramai).
CREATE OR REPLACE VIEW item_list WITH (security_invoker = true) AS
SELECT item_name,
       SUM(total_volume)::INT AS total_volume,
       MIN(date)              AS first_date,
       MAX(date)              AS last_date
FROM daily_item_prices
GROUP BY item_name
ORDER BY total_volume DESC;

-- Frontend (publishable/anon key) hanya boleh MEMBACA.
-- Scraper memakai secret key, yang melewati RLS.
ALTER TABLE daily_item_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read" ON daily_item_prices
    FOR SELECT TO anon USING (true);

GRANT SELECT ON item_list TO anon;

-- Catatan hari yang sudah selesai di-scrape, agar tidak dikerjakan dua kali.
-- RLS aktif tanpa policy: hanya scraper (secret key) yang bisa membaca/menulis.
CREATE TABLE IF NOT EXISTS scrape_log (
    date       DATE PRIMARY KEY,
    offers     INT NOT NULL DEFAULT 0,   -- jumlah penawaran yang terbaca hari itu
    scraped_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE scrape_log ENABLE ROW LEVEL SECURITY;

-- Hanya sekali, untuk data yang sudah ada sebelum scrape_log dibuat:
-- INSERT INTO scrape_log (date) SELECT DISTINCT date FROM daily_item_prices ON CONFLICT DO NOTHING;