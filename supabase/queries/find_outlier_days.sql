-- Cari hari yang median gabungannya menyimpang dari hari-hari di sekitarnya.
-- Dibandingkan dengan MEDIAN harga 10 hari sebelum dan sesudah (tanpa hari itu sendiri),
-- jadi satu deretan 3 hari yang sama-sama salah pun tetap terdeteksi.
-- rasio > 1.6 atau < 0.625 dianggap mencurigakan. Ubah angka itu sesuai selera.
--
-- Hasilnya DAFTAR KANDIDAT, bukan vonis: lonjakan harga yang nyata (mis. akibat update game)
-- juga akan muncul. Periksa dengan:
--   python pipeline.py --date TANGGAL --dry-run
-- Perbaiki satu hari dengan:
--   python pipeline.py --date TANGGAL --force
SELECT d.item_name,
       d.date,
       d.median_price,
       round(m.nb::numeric, 4)                   AS median_tetangga,
       round((d.median_price / m.nb)::numeric, 2) AS rasio,
       d.total_volume
FROM daily_item_prices d
CROSS JOIN LATERAL (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY p.median_price) AS nb
    FROM daily_item_prices p
    WHERE p.item_name = d.item_name
      AND p.date BETWEEN d.date - 10 AND d.date + 10
      AND p.date <> d.date
) m
WHERE m.nb IS NOT NULL
  AND (d.median_price / m.nb > 1.6 OR d.median_price / m.nb < 0.625)
ORDER BY d.item_name, d.date;