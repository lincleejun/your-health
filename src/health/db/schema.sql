-- SQLite schema for the personal health database.
-- Re-runnable: every CREATE uses IF NOT EXISTS so initialize() is idempotent.

CREATE TABLE IF NOT EXISTS activities (
    activity_id     INTEGER PRIMARY KEY,
    start_ts        TEXT    NOT NULL,
    sport           TEXT    NOT NULL,
    duration_s      REAL,
    distance_m      REAL,
    avg_hr          REAL,
    training_load   REAL,
    aerobic_te      REAL,
    anaerobic_te    REAL,
    raw_json        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activities_start_ts ON activities(start_ts);

CREATE TABLE IF NOT EXISTS daily_summary (
    date              TEXT PRIMARY KEY,
    steps             INTEGER,
    resting_hr        REAL,
    body_battery_min  INTEGER,
    body_battery_max  INTEGER,
    stress_avg        REAL,
    calories_active   REAL,
    raw_json          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON daily_summary(date);

CREATE TABLE IF NOT EXISTS sleep (
    date           TEXT PRIMARY KEY,
    total_sleep_s  INTEGER,
    deep_s         INTEGER,
    light_s        INTEGER,
    rem_s          INTEGER,
    awake_s        INTEGER,
    sleep_score    REAL,
    raw_json       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep(date);

CREATE TABLE IF NOT EXISTS hrv (
    date             TEXT PRIMARY KEY,
    weekly_avg       REAL,
    last_night_avg   REAL,
    status           TEXT,
    raw_json         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hrv_date ON hrv(date);

CREATE TABLE IF NOT EXISTS body_composition (
    date             TEXT PRIMARY KEY,
    weight_kg        REAL,
    body_fat_pct     REAL,
    muscle_mass_kg   REAL,
    raw_json         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_body_composition_date ON body_composition(date);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    days_requested  INTEGER NOT NULL,
    rows_written    INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);
