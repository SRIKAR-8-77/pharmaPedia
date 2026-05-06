-- Migration 003: add date_from / date_to to projects
-- date_from: start of the monitoring window (null = from the beginning)
-- date_to:   end of the monitoring window (null = ongoing live monitoring)

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS date_from TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS date_to   TIMESTAMPTZ;
