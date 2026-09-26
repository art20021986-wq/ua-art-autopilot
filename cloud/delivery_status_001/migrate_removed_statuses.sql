-- SQLite: run only after a verified backup and live schema check (cars.status).
BEGIN IMMEDIATE;

UPDATE cars
SET status = 'hidden'
WHERE status IN (
    'Продано в пути', 'Продано · в пути', 'sold_transit',
    'Выехало в Киев', 'ge_to_kyiv',
    'Продано', 'sold',
    'Архив', 'archive'
);

SELECT changes() AS hidden_rows;
COMMIT;
