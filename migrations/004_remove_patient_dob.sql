-- Remove date of birth from the patients table.
-- DOB is not required for variant interpretation and is unnecessary
-- personal data under UK GDPR data-minimisation principles.
BEGIN;
ALTER TABLE patients DROP COLUMN IF EXISTS dob;
COMMIT;
