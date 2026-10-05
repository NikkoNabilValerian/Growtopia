-- MIGRASI 002: multi-item + kolom penulis unik + tabel analisis.
-- Untuk database yang sudah berisi data dari skema sebelumnya.
--
-- ATURAN PENTING:
--   * Jalankan HANYA setelah backfill di GitHub Actions SELESAI (tidak ada run yang
--     berjalan atau pending), karena scraper versi lama memakai scrape_log lama.
--   * Satu transaksi: kalau ada yang gagal, tidak ada perubahan sama sekali.
--   * Aman dijalankan ulang: bagian pembangunan ulang tabel dilewati bila kolom
--     author_median sudah ada.
--   * Tabel lama TIDAK dihapus, hanya diganti nama menjadi daily_item_prices_backup.
--     Setelah semuanya terverifikasi, hapus manual:  DROP TABLE daily_item_prices_backup;
--   * Tidak memakai tabel sementara, supaya editor Supabase tidak menampilkan
--     peringatan RLS palsu. Peringatan "destructive operations" tetap muncul (karena ada
--     DROP VIEW) dan itu normal: pilih Run.
--   * Seluruh tabel baru di skrip ini sudah mengaktifkan RLS sendiri di bagian 5.

BEGIN;

-- 1) Bangun ulang daily_item_prices dengan urutan kolom rapi + kolom penulis unik.
DO $migrate$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'daily_item_prices' AND column_name = 'author_median'
  ) THEN
    DROP VIEW IF EXISTS item_list;

    ALTER TABLE daily_item_prices RENAME TO daily_item_prices_backup;
    ALTER INDEX idx_item_date RENAME TO idx_item_date_backup;
    ALTER TABLE daily_item_prices_backup RENAME CONSTRAINT unique_item_date TO unique_item_date_backup;
    ALTER TABLE daily_item_prices_backup RENAME CONSTRAINT daily_item_prices_pkey TO daily_item_prices_backup_pkey;
    ALTER SEQUENCE daily_item_prices_id_seq RENAME TO daily_item_prices_backup_id_seq;

    CREATE TABLE daily_item_prices (
        id             BIGSERIAL PRIMARY KEY,
        item_name      VARCHAR(100)   NOT NULL,
        date           DATE           NOT NULL,
        median_price   NUMERIC(14, 4) NOT NULL,
        buy_median     NUMERIC(14, 4),
        sell_median    NUMERIC(14, 4),
        author_median  NUMERIC(14, 4),
        avg_price      NUMERIC(14, 4) NOT NULL,
        min_price      NUMERIC(14, 4) NOT NULL,
        max_price      NUMERIC(14, 4) NOT NULL,
        total_volume   INT            NOT NULL,
        buy_volume     INT            NOT NULL DEFAULT 0,
        sell_volume    INT            NOT NULL DEFAULT 0,
        total_authors  INT            NOT NULL DEFAULT 0,
        buy_authors    INT            NOT NULL DEFAULT 0,
        sell_authors   INT            NOT NULL DEFAULT 0,
        created_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_item_date UNIQUE (item_name, date)
    );
    CREATE INDEX idx_item_date ON daily_item_prices (item_name, date DESC);

    INSERT INTO daily_item_prices
        (item_name, date, median_price, buy_median, sell_median, avg_price, min_price, max_price,
         total_volume, buy_volume, sell_volume, created_at)
    SELECT item_name, date, median_price, buy_median, sell_median, avg_price, min_price, max_price,
           total_volume, buy_volume, sell_volume, created_at
    FROM daily_item_prices_backup
    ORDER BY item_name, date;
  END IF;
END
$migrate$;

-- 2) scrape_log menjadi per item. Semua baris lama adalah milik growscan.
ALTER TABLE scrape_log ADD COLUMN IF NOT EXISTS item_name VARCHAR(100) NOT NULL DEFAULT 'growscan';
ALTER TABLE scrape_log DROP CONSTRAINT IF EXISTS scrape_log_pkey;
ALTER TABLE scrape_log ADD PRIMARY KEY (item_name, date);
ALTER TABLE scrape_log ALTER COLUMN item_name DROP DEFAULT;

-- 3) Tabel baru
CREATE TABLE IF NOT EXISTS items (
    item_name  VARCHAR(100) PRIMARY KEY,
    label      TEXT NOT NULL,
    sort_order INT  NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'event',
    notes      TEXT,
    CHECK (end_date >= start_date)
);

CREATE TABLE IF NOT EXISTS item_signals (
    item_name VARCHAR(100) NOT NULL,
    date      DATE         NOT NULL,
    predicted NUMERIC(14, 4),
    resid_z   NUMERIC(8, 3),
    spread_z  NUMERIC(8, 3),
    signal    TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD', 'NO_TRADE')),
    reason    TEXT,
    PRIMARY KEY (item_name, date)
);

-- Label growscan langsung diisi; item lain diisi otomatis oleh pipeline.
INSERT INTO items (item_name, label, sort_order) VALUES ('growscan', 'Growscan 9000', 0)
ON CONFLICT (item_name) DO NOTHING;

-- 4) View dropdown
DROP VIEW IF EXISTS item_list;
CREATE VIEW item_list WITH (security_invoker = true) AS
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

-- 5) Keamanan: baca-saja untuk website
ALTER TABLE daily_item_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE items             ENABLE ROW LEVEL SECURITY;
ALTER TABLE events            ENABLE ROW LEVEL SECURITY;
ALTER TABLE item_signals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_log        ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read" ON daily_item_prices;
DROP POLICY IF EXISTS "public read" ON items;
DROP POLICY IF EXISTS "public read" ON events;
DROP POLICY IF EXISTS "public read" ON item_signals;
CREATE POLICY "public read" ON daily_item_prices FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON items             FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON events            FOR SELECT TO anon USING (true);
CREATE POLICY "public read" ON item_signals      FOR SELECT TO anon USING (true);

GRANT SELECT ON item_list TO anon;

COMMIT;