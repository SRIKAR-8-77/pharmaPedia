-- Migration 005: add is_paused flag to projects
-- Allows users to pause all Celery scrape + pipeline jobs for a project
-- without deleting it. Celery beat tasks check this before processing.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS is_paused BOOLEAN NOT NULL DEFAULT FALSE;
