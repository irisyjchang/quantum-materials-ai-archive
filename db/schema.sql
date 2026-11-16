-- Local Growth Log MVP schema.
-- Replaces the pilot prototype schema (pilot/sqlite/schema.sql).
-- Callers must enable foreign keys on every connection: PRAGMA foreign_keys = ON;

-- One row per version of a growth-log PDF.
-- A version is identified by drive_file_id + file_hash; pdf_id is the internal key.
CREATE TABLE source_pdfs (
    pdf_id           TEXT PRIMARY KEY NOT NULL,
    archive_filename TEXT NOT NULL,
    drive_file_id    TEXT NOT NULL,
    file_hash        TEXT NOT NULL,
    storage_path     TEXT,
    UNIQUE (drive_file_id, file_hash)
);

-- One row per staged extraction draft awaiting reviewer action.
CREATE TABLE draft_runs (
    draft_id              TEXT PRIMARY KEY NOT NULL,
    pdf_id                TEXT NOT NULL
                          REFERENCES source_pdfs (pdf_id) ON DELETE RESTRICT,
    source_locations_json TEXT NOT NULL,
    original_json         TEXT NOT NULL,
    review_status         TEXT NOT NULL
                          CHECK (review_status IN ('Pending review', 'Held', 'Approved')),
    hold_reason           TEXT,
    updated_at            TEXT,
    CHECK (
        review_status <> 'Held'
        OR (hold_reason IS NOT NULL AND trim(hold_reason) <> '')
    )
);

CREATE INDEX draft_runs_pdf_id ON draft_runs (pdf_id);

-- One row per approved experimental run. Written only by the approval transaction.
CREATE TABLE growth_runs (
    run_id                TEXT PRIMARY KEY NOT NULL,
    pdf_id                TEXT NOT NULL
                          REFERENCES source_pdfs (pdf_id) ON DELETE RESTRICT,
    researcher_name       TEXT,
    growth_date           TEXT,
    date_precision        TEXT,
    jc_number             TEXT,
    growth_process        TEXT,
    composition_json      TEXT,
    source_locations_json TEXT NOT NULL,
    details_json          TEXT
);

-- One row per approved version of a run, including corrections.
CREATE TABLE run_revisions (
    revision_id          TEXT PRIMARY KEY NOT NULL,
    run_id               TEXT NOT NULL
                         REFERENCES growth_runs (run_id) ON DELETE RESTRICT,
    version              INTEGER NOT NULL,
    approved_values_json TEXT NOT NULL,
    changes_json         TEXT,
    edited_by            TEXT,
    edited_at            TEXT,
    approved_by          TEXT NOT NULL,
    approved_at          TEXT NOT NULL,
    UNIQUE (run_id, version)
);

-- One row per PDF version, tracking risk assessment and extraction outcome.
CREATE TABLE processing_status (
    pdf_id         TEXT PRIMARY KEY NOT NULL
                   REFERENCES source_pdfs (pdf_id) ON DELETE RESTRICT,
    file_hash      TEXT NOT NULL,
    status         TEXT NOT NULL
                   CHECK (status IN (
                       'risk_assessed',
                       'held_pending_clearance',
                       'cleared',
                       'extraction_complete',
                       'technical_failure'
                   )),
    risk_decision  TEXT
                   CHECK (risk_decision IS NULL
                          OR risk_decision IN ('non_critical', 'critical', 'uncertain')),
    issues_json    TEXT,
    clearance_by   TEXT,
    clearance_at   TEXT,
    clearance_note TEXT,
    reason         TEXT,
    updated_at     TEXT NOT NULL
);
