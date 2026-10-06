--liquibase formatted sql

--changeset calin:2026-10-06-05
CREATE INDEX CONCURRENTLY idx_audit_created_at ON audit_log (created_at);
