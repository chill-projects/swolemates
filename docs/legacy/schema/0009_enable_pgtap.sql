-- pgTAP for database-level tests (supabase test db). Dev/test tooling only —
-- no application code depends on this extension.
create extension if not exists pgtap with schema extensions;
