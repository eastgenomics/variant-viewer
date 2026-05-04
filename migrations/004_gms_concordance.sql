BEGIN;

-- GMS concordance: array of [oncogenic, benign, unknown] counts from other GMS labs
-- Total always sums to 5 (number of GMS labs reporting)
ALTER TABLE variants
  ADD COLUMN gms_concordance INTEGER[] DEFAULT NULL;

-- Populate existing rows with dummy values
-- Constraints: oncogenic 1–5, benign 0–2, unknown 0–3, total = 5
UPDATE variants SET gms_concordance = (
  SELECT ARRAY[onc, ben, 5 - onc - ben]
  FROM (
    SELECT
      onc,
      LEAST(GREATEST(floor(random() * 3)::int, onc_rem - 3), LEAST(onc_rem, 2)) AS ben,
      onc_rem
    FROM (
      SELECT
        onc,
        5 - onc AS onc_rem
      FROM (
        SELECT floor(random() * 5 + 1)::int AS onc
      ) AS o
    ) AS r
  ) AS vals
);

COMMIT;
