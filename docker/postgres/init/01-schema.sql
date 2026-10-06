-- =============================================================================
-- 01-schema.sql
--
-- Creates every table each of the 4 services needs, in one shared "appdb"
-- database, before any service gets a chance to connect.
--
-- One database instead of one-per-service is a deliberate simplification:
-- it lets Grafana query "total users" and "total products" with a single
-- Postgres datasource (Postgres can't query across separate databases in
-- one connection). Each service still only ever reads/writes its own
-- table - see README.docker.md.
--
-- Every service also runs SQLModel.metadata.create_all() on its own
-- startup (idempotent, "if not exists"-equivalent), so this file exists to
-- make table creation explicit and deterministic up front rather than
-- racing whichever service happens to boot first.
-- =============================================================================

\set ON_ERROR_STOP on

-- -----------------------------------------------------------------------------
-- "user" — user-service
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "user" (
    id       SERIAL PRIMARY KEY,
    name     VARCHAR NOT NULL,
    email    VARCHAR NOT NULL,
    password VARCHAR NOT NULL,
    role     VARCHAR NOT NULL DEFAULT 'user'
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON "user" (email);

-- -----------------------------------------------------------------------------
-- product — product-service
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    description VARCHAR NOT NULL DEFAULT '',
    image_url   VARCHAR NOT NULL DEFAULT ''
);

-- -----------------------------------------------------------------------------
-- "order" — order-service ("order" is a reserved word, hence the quoting)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "order" (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    status     VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_order_user_id ON "order" (user_id);

-- -----------------------------------------------------------------------------
-- inventory — inventory-service
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventory (
    product_id INTEGER PRIMARY KEY,
    stock      INTEGER NOT NULL DEFAULT 0
);
