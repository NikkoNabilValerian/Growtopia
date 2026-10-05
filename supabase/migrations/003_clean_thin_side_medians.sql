-- 003: bersihkan median buy/sell yang tidak andal pada data lama (tanpa scrape ulang).
--
-- Aturan yang sama dengan scraper terbaru (offer_parser.py):
--   MIN_SIDE_POSTS = 5   satu sisi butuh minimal 5 postingan
--   SIDE_BAND      = 2.0 median satu sisi harus dalam [median gabungan / 2, x 2]
--   MAX_CROSS      = 1.15 bid tidak boleh > ask x 1.15 (sisi dengan postingan lebih sedikit dibuang)
-- Yang dibersihkan hanya buy_median / sell_median (menjadi NULL). median_price (gabungan)
-- dan semua kolom lain tidak disentuh. Garis di chart akan menyambung melewati hari NULL.
--
-- LANGKAH:  (1) jalankan bagian PREVIEW, (2) kalau jumlahnya masuk akal, jalankan bagian CLEANUP.

-- ===================== (1) PREVIEW: berapa baris yang terkena? =====================
-- SELECT
--   count(*) FILTER (WHERE buy_median  IS NOT NULL AND buy_volume  < 5)                                   AS buy_tipis,
--   count(*) FILTER (WHERE sell_median IS NOT NULL AND sell_volume < 5)                                   AS sell_tipis,
--   count(*) FILTER (WHERE buy_median  IS NOT NULL AND (buy_median  > median_price * 2 OR buy_median  < median_price / 2)) AS buy_jauh,
--   count(*) FILTER (WHERE sell_median IS NOT NULL AND (sell_median > median_price * 2 OR sell_median < median_price / 2)) AS sell_jauh,
--   count(*) FILTER (WHERE buy_median > sell_median * 1.15)                                               AS bid_di_atas_ask,
--   count(*)                                                                                              AS total_baris
-- FROM daily_item_prices;

-- ===================== (2) CLEANUP =====================
BEGIN;

UPDATE daily_item_prices SET buy_median  = NULL WHERE buy_median  IS NOT NULL AND buy_volume  < 5;
UPDATE daily_item_prices SET sell_median = NULL WHERE sell_median IS NOT NULL AND sell_volume < 5;

UPDATE daily_item_prices SET buy_median  = NULL
 WHERE buy_median  IS NOT NULL AND (buy_median  > median_price * 2 OR buy_median  < median_price / 2);
UPDATE daily_item_prices SET sell_median = NULL
 WHERE sell_median IS NOT NULL AND (sell_median > median_price * 2 OR sell_median < median_price / 2);

-- Bid di atas ask: buang sisi yang postingannya lebih sedikit.
UPDATE daily_item_prices SET buy_median  = NULL
 WHERE buy_median > sell_median * 1.15 AND buy_volume <= sell_volume;
UPDATE daily_item_prices SET sell_median = NULL
 WHERE buy_median > sell_median * 1.15 AND buy_volume >  sell_volume;

COMMIT;

-- ===================== (3) KALIBRASI (opsional): seberapa jauh sisi biasanya dari median gabungan? =====================
-- Jalankan sebelum CLEANUP bila ingin mengganti angka 2 di atas dengan nilai dari datamu sendiri.
-- SELECT 'buy' AS sisi,
--        round((percentile_cont(0.50) WITHIN GROUP (ORDER BY buy_median / median_price))::numeric, 3) AS p50,
--        round((percentile_cont(0.95) WITHIN GROUP (ORDER BY buy_median / median_price))::numeric, 3) AS p95,
--        round((percentile_cont(0.99) WITHIN GROUP (ORDER BY buy_median / median_price))::numeric, 3) AS p99,
--        round(min(buy_median / median_price)::numeric, 3) AS min, round(max(buy_median / median_price)::numeric, 3) AS max
-- FROM daily_item_prices WHERE buy_median IS NOT NULL AND buy_volume >= 10
-- UNION ALL
-- SELECT 'sell',
--        round((percentile_cont(0.50) WITHIN GROUP (ORDER BY sell_median / median_price))::numeric, 3),
--        round((percentile_cont(0.95) WITHIN GROUP (ORDER BY sell_median / median_price))::numeric, 3),
--        round((percentile_cont(0.99) WITHIN GROUP (ORDER BY sell_median / median_price))::numeric, 3),
--        round(min(sell_median / median_price)::numeric, 3), round(max(sell_median / median_price)::numeric, 3)
-- FROM daily_item_prices WHERE sell_median IS NOT NULL AND sell_volume >= 10;