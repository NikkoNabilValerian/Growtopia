-- Ringkasan harga harian (permanen). Satu baris per item per hari.
-- Harga disimpan dalam BGL. 1 BGL = 100 DL = 10.000 WL, jadi 1 WL = 0.0001 BGL.
-- NUMERIC(14,4) dipakai (bukan (10,2)) supaya harga murah seperti "20 WL"
-- tidak dibulatkan menjadi 0.00.
CREATE TABLE IF NOT EXISTS daily_item_prices (
    id           BIGSERIAL PRIMARY KEY,
    item_name    VARCHAR(100)   NOT NULL,
    date         DATE           NOT NULL,
    avg_price    NUMERIC(14, 4) NOT NULL,
    median_price NUMERIC(14, 4) NOT NULL,  -- harga utama untuk chart
    min_price    NUMERIC(14, 4) NOT NULL,
    max_price    NUMERIC(14, 4) NOT NULL,
    total_volume INT            NOT NULL,  -- jumlah postingan unik yang terekam
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_item_date UNIQUE (item_name, date)
);

CREATE INDEX IF NOT EXISTS idx_item_date
    ON daily_item_prices (item_name, date DESC);

-- Daftar item untuk dropdown (diurutkan dari yang paling ramai).
CREATE OR REPLACE VIEW item_list AS
SELECT item_name,
       SUM(total_volume)::INT AS total_volume,
       MIN(date)              AS first_date,
       MAX(date)              AS last_date
FROM daily_item_prices
GROUP BY item_name
ORDER BY total_volume DESC;

-- Keamanan: frontend (anon key) hanya boleh MEMBACA.
-- Scraper memakai service_role key, yang melewati RLS.
ALTER TABLE daily_item_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read" ON daily_item_prices
    FOR SELECT TO anon USING (true);

GRANT SELECT ON item_list TO anon;