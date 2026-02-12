-- Migration: E3DC Timestamps von Intervallende auf Intervallanfang shiften
-- Issue: #177
--
-- E3DC exportiert Timestamps am ENDE des Intervalls (08:00 = Produktion 07:00-08:00).
-- Diese Migration verschiebt alle bestehenden Timestamps um -1h auf Intervallanfang.
--
-- ACHTUNG: Nur EINMAL ausführen! Idempotenz-Check unten.
-- Ausführung: sqlite3 /pfad/zur/data.db < migrate_e3dc_timestamps.sql
--
-- Idempotenz-Check: Prüfe ob bereits migriert wurde
-- (Wenn der Marker existiert, wird nichts gemacht)

-- Marker setzen um doppelte Ausführung zu verhindern
INSERT OR IGNORE INTO metadata (key, value)
    SELECT 'migration_177_timestamp_shift', 'pending'
    WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key = 'migration_177_timestamp_shift');

-- Nur ausführen wenn Status 'pending' (noch nicht migriert)
UPDATE pv_readings SET timestamp = timestamp - 3600
    WHERE EXISTS (
        SELECT 1 FROM metadata
        WHERE key = 'migration_177_timestamp_shift' AND value = 'pending'
    );

-- Marker auf 'done' setzen
UPDATE metadata SET value = datetime('now') || ' migrated'
    WHERE key = 'migration_177_timestamp_shift' AND value = 'pending';

SELECT 'Migration Status: ' || value FROM metadata WHERE key = 'migration_177_timestamp_shift';
