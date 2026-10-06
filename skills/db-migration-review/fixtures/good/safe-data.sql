--liquibase formatted sql

--changeset calin:2026-10-06-30
--comment: ~40 rows, reference data
UPDATE shipping_zones SET code = upper(code) WHERE code <> upper(code) AND id BETWEEN 1 AND 100;
--rollback empty
