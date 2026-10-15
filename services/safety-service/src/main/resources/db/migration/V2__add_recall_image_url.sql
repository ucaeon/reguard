ALTER TABLE recalls ADD COLUMN image_url TEXT;

COMMENT ON COLUMN products.image_url IS 'Representative product image URL; NULL when unavailable';
COMMENT ON COLUMN recalls.image_url IS 'First source-provided image URL; all source URLs remain in raw_payload; NULL when unavailable';

UPDATE recalls
SET image_url = btrim(split_part(raw_payload ->> 'IMG_FILE_PATH', ',', 1))
WHERE source = 'FOOD_I0490'
  AND btrim(split_part(raw_payload ->> 'IMG_FILE_PATH', ',', 1)) ~ '^https?://[^[:space:]]+$';
