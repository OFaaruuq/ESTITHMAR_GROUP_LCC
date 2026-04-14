-- One-time: rename member public codes IST-* -> EST-* (table ``members``, column ``member_id``).
-- Run after deploy that uses MEMBER_PUBLIC_ID_PREFIX = EST. Verify in a transaction first.

-- Microsoft SQL Server
UPDATE members
SET member_id = CONCAT('EST-', SUBSTRING(member_id, 5, 32))
WHERE member_id LIKE 'IST-%';

-- PostgreSQL (use instead of the block above when on Postgres)
-- UPDATE members
-- SET member_id = 'EST-' || SUBSTRING(member_id FROM 5)
-- WHERE member_id LIKE 'IST-%';
