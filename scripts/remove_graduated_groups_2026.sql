BEGIN;

CREATE TEMP TABLE groups_to_remove_2026 (
    id integer PRIMARY KEY,
    name text UNIQUE NOT NULL
) ON COMMIT DROP;

INSERT INTO groups_to_remove_2026 (id, name)
SELECT id, name
FROM groups
WHERE name ~ '^(uik|mk)[0-9]+-41m$'
   OR name ~ '^(uik|mk)[0-9]+-8[12]b$';

DO $$
BEGIN
    IF (SELECT count(*) FROM groups_to_remove_2026) <> 33 THEN
        RAISE EXCEPTION 'Expected 33 groups to remove, found %',
            (SELECT count(*) FROM groups_to_remove_2026);
    END IF;
END $$;

UPDATE users
SET group_id = NULL,
    is_active = 0
WHERE group_id IN (SELECT id FROM groups_to_remove_2026);

DELETE FROM groups
WHERE id IN (SELECT id FROM groups_to_remove_2026);

COMMIT;
