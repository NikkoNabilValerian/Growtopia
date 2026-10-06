-- Hapus SELURUH data satu item dari database (harga, catatan scrape, label, sinyal).
-- Berguna untuk sisa data lama, mis. item yang pernah diberi nama lain di config.py.
-- Ganti 'NAMA_ITEM' (3 kali di bagian CLEANUP dan 1 kali di PREVIEW) dengan nama item di database.
-- Tidak bisa dibatalkan; lakukan PREVIEW dulu.

-- ======================= PREVIEW =======================
-- SELECT item_name, count(*) AS hari, min(date) AS dari, max(date) AS sampai, sum(total_volume) AS postingan
-- FROM daily_item_prices GROUP BY item_name ORDER BY item_name;
-- SELECT * FROM items ORDER BY sort_order;

-- ======================= CLEANUP =======================
BEGIN;
DELETE FROM daily_item_prices WHERE item_name = 'NAMA_ITEM';
DELETE FROM scrape_log        WHERE item_name = 'NAMA_ITEM';
DELETE FROM item_signals      WHERE item_name = 'NAMA_ITEM';
DELETE FROM items             WHERE item_name = 'NAMA_ITEM';
COMMIT;