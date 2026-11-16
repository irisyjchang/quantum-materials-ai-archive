CREATE TABLE IF NOT EXISTS growth_logs (
    record_id TEXT PRIMARY KEY NOT NULL,
    original_json TEXT NOT NULL CHECK (json_valid(original_json)),
    working_json TEXT NOT NULL CHECK (json_valid(working_json)),
    CHECK (json_extract(original_json, '$.record_id') IS record_id),
    CHECK (json_extract(working_json, '$.record_id') IS record_id),
    CHECK (json_extract(original_json, '$.source') IS json_extract(working_json, '$.source'))
);

CREATE VIEW IF NOT EXISTS growth_log_index AS
SELECT record_id,
       json_extract(working_json, '$.source.file') AS source_file,
       json_extract(working_json, '$.source.page') AS source_page,
       json_extract(working_json, '$.fields.name.value') AS name,
       json_extract(working_json, '$.fields.date.value') AS growth_date,
       json_extract(working_json, '$.fields.jc.value.full') AS jc_number,
       json_extract(working_json, '$.fields.jc.value.raw') AS jc_written,
       json_extract(working_json, '$.fields.technique.value') AS technique,
       json_extract(working_json, '$.fields.furnace_layout.value.present') AS layout_present,
       json_extract(working_json, '$.fields.furnace_layout.value.image') AS layout_image
FROM growth_logs;
