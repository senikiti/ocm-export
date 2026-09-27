-- OCM Export relational schema
-- Target: PostgreSQL, but kept database-neutral (standard SQL types only).
-- All primary keys are original OCM IDs (natural keys).
-- See db/schema.md for the ER diagram and JSON -> column mapping.

-- Drop in reverse dependency order
DROP TABLE IF EXISTS metadata_values;
DROP TABLE IF EXISTS media_items;
DROP TABLE IF EXISTS user_comments;
DROP TABLE IF EXISTS connections;
DROP TABLE IF EXISTS charge_points;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS metadata_field_options;
DROP TABLE IF EXISTS metadata_fields;
DROP TABLE IF EXISTS metadata_groups;
DROP TABLE IF EXISTS data_types;
DROP TABLE IF EXISTS checkin_status_types;
DROP TABLE IF EXISTS user_comment_types;
DROP TABLE IF EXISTS current_types;
DROP TABLE IF EXISTS charger_types;
DROP TABLE IF EXISTS connection_types;
DROP TABLE IF EXISTS submission_status_types;
DROP TABLE IF EXISTS status_types;
DROP TABLE IF EXISTS usage_types;
DROP TABLE IF EXISTS data_providers;
DROP TABLE IF EXISTS data_provider_status_types;
DROP TABLE IF EXISTS operators;
DROP TABLE IF EXISTS countries;
DROP TABLE IF EXISTS import_state;

-- ============================================================
-- Reference tables (from data/referencedata.json)
-- ============================================================

CREATE TABLE countries (
    id              INTEGER PRIMARY KEY,
    iso_code        TEXT,
    continent_code  TEXT,
    title           TEXT
);

CREATE TABLE operators (
    id                       INTEGER PRIMARY KEY,
    title                    TEXT,
    website_url              TEXT,
    comments                 TEXT,
    phone_primary_contact    TEXT,
    phone_secondary_contact  TEXT,
    is_private_individual    BOOLEAN,
    booking_url              TEXT,
    contact_email            TEXT,
    fault_report_email       TEXT,
    is_restricted_edit       BOOLEAN
);

CREATE TABLE data_provider_status_types (
    id                   INTEGER PRIMARY KEY,
    title                TEXT,
    is_provider_enabled  BOOLEAN
);

CREATE TABLE data_providers (
    id                             INTEGER PRIMARY KEY,
    title                          TEXT,
    website_url                    TEXT,
    comments                       TEXT,
    data_provider_status_type_id   INTEGER REFERENCES data_provider_status_types (id),
    is_restricted_edit             BOOLEAN,
    is_open_data_licensed          BOOLEAN,
    is_approved_import             BOOLEAN,
    license                        TEXT,
    date_last_imported             TIMESTAMP
);

CREATE TABLE usage_types (
    id                      INTEGER PRIMARY KEY,
    title                   TEXT,
    is_pay_at_location      BOOLEAN,
    is_membership_required  BOOLEAN,
    is_access_key_required  BOOLEAN
);

CREATE TABLE status_types (
    id                  INTEGER PRIMARY KEY,
    title               TEXT,
    is_operational      BOOLEAN,
    is_user_selectable  BOOLEAN
);

CREATE TABLE submission_status_types (
    id       INTEGER PRIMARY KEY,
    title    TEXT,
    is_live  BOOLEAN
);

CREATE TABLE connection_types (
    id               INTEGER PRIMARY KEY,
    title            TEXT,
    formal_name      TEXT,
    is_discontinued  BOOLEAN,
    is_obsolete      BOOLEAN
);

-- "ChargerTypes" in reference data; referenced as LevelID from connections
CREATE TABLE charger_types (
    id                      INTEGER PRIMARY KEY,
    title                   TEXT,
    comments                TEXT,
    is_fast_charge_capable  BOOLEAN
);

CREATE TABLE current_types (
    id           INTEGER PRIMARY KEY,
    title        TEXT,
    description  TEXT
);

CREATE TABLE user_comment_types (
    id     INTEGER PRIMARY KEY,
    title  TEXT
);

CREATE TABLE checkin_status_types (
    id                    INTEGER PRIMARY KEY,
    title                 TEXT,
    is_positive           BOOLEAN,
    is_automated_checkin  BOOLEAN
);

CREATE TABLE data_types (
    id     INTEGER PRIMARY KEY,
    title  TEXT
);

CREATE TABLE metadata_groups (
    id                  INTEGER PRIMARY KEY,
    title               TEXT,
    data_provider_id    INTEGER REFERENCES data_providers (id),
    is_restricted_edit  BOOLEAN,
    is_public_interest  BOOLEAN
);

CREATE TABLE metadata_fields (
    id                 INTEGER PRIMARY KEY,
    metadata_group_id  INTEGER REFERENCES metadata_groups (id),
    title              TEXT,
    data_type_id       INTEGER REFERENCES data_types (id)
);

CREATE TABLE metadata_field_options (
    id                 INTEGER PRIMARY KEY,
    metadata_field_id  INTEGER REFERENCES metadata_fields (id),
    title              TEXT
);

-- ============================================================
-- Core tables (from data/<CC>/OCM-<id>.json)
-- ============================================================

-- Users embedded in UserComments/MediaItems ({ID, Username} only)
CREATE TABLE users (
    id        INTEGER PRIMARY KEY,
    username  TEXT
);

CREATE TABLE charge_points (
    id                          INTEGER PRIMARY KEY,          -- ID
    uuid                        TEXT,                          -- UUID
    data_provider_id            INTEGER REFERENCES data_providers (id),
    data_providers_reference    TEXT,
    operator_id                 INTEGER REFERENCES operators (id),
    operators_reference         TEXT,
    usage_type_id               INTEGER REFERENCES usage_types (id),
    usage_cost                  TEXT,
    number_of_points            INTEGER,
    general_comments            TEXT,
    date_planned                TIMESTAMP,
    date_last_confirmed         TIMESTAMP,
    status_type_id              INTEGER REFERENCES status_types (id),
    date_last_status_update     TIMESTAMP,
    date_last_verified          TIMESTAMP,
    submission_status_type_id   INTEGER REFERENCES submission_status_types (id),
    date_created                TIMESTAMP,
    country_code                TEXT,                          -- containing folder (ISO2)
    -- AddressInfo (1:1, merged; original AddressInfo.ID kept as address_id)
    address_id                  INTEGER,
    title                       TEXT,
    address_line1               TEXT,
    address_line2               TEXT,
    town                        TEXT,
    state_or_province           TEXT,
    postcode                    TEXT,
    country_id                  INTEGER REFERENCES countries (id),
    latitude                    DOUBLE PRECISION,
    longitude                   DOUBLE PRECISION,
    distance_unit               INTEGER,
    access_comments             TEXT,
    related_url                 TEXT,
    contact_telephone1          TEXT,
    contact_telephone2          TEXT,
    contact_email               TEXT
);

CREATE TABLE connections (
    id                  INTEGER PRIMARY KEY,
    charge_point_id     INTEGER NOT NULL REFERENCES charge_points (id) ON DELETE CASCADE,
    connection_type_id  INTEGER REFERENCES connection_types (id),
    reference           TEXT,
    status_type_id      INTEGER REFERENCES status_types (id),
    level_id            INTEGER REFERENCES charger_types (id),   -- LevelID
    amps                DOUBLE PRECISION,
    voltage             DOUBLE PRECISION,
    power_kw            NUMERIC(10, 3),
    current_type_id     INTEGER REFERENCES current_types (id),
    quantity            INTEGER,
    comments            TEXT
);

CREATE TABLE user_comments (
    id                       INTEGER PRIMARY KEY,
    charge_point_id          INTEGER NOT NULL REFERENCES charge_points (id) ON DELETE CASCADE,
    comment_type_id          INTEGER REFERENCES user_comment_types (id),
    user_name                TEXT,
    comment                  TEXT,
    related_url              TEXT,
    rating                   INTEGER,
    date_created             TIMESTAMP,
    -- deferred: users are bulk-loaded after comments within the same transaction
    user_id                  INTEGER REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED,
    checkin_status_type_id   INTEGER REFERENCES checkin_status_types (id),
    is_actioned_by_editor    BOOLEAN
);

CREATE TABLE media_items (
    id                     INTEGER PRIMARY KEY,
    charge_point_id        INTEGER NOT NULL REFERENCES charge_points (id) ON DELETE CASCADE,
    item_url               TEXT,
    item_thumbnail_url     TEXT,
    comment                TEXT,
    is_enabled             BOOLEAN,
    is_video               BOOLEAN,
    is_featured_item       BOOLEAN,
    is_external_resource   BOOLEAN,
    -- deferred: users are bulk-loaded after media items within the same transaction
    user_id                INTEGER REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED,
    date_created           TIMESTAMP
);

CREATE TABLE metadata_values (
    id                 INTEGER PRIMARY KEY,
    charge_point_id    INTEGER NOT NULL REFERENCES charge_points (id) ON DELETE CASCADE,
    metadata_field_id  INTEGER REFERENCES metadata_fields (id),
    item_value         TEXT
);

-- ============================================================
-- Import bookkeeping
-- ============================================================

CREATE TABLE import_state (
    key    TEXT PRIMARY KEY,   -- e.g. 'last_commit'
    value  TEXT
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX idx_charge_points_country_id   ON charge_points (country_id);
CREATE INDEX idx_charge_points_country_code ON charge_points (country_code);
CREATE INDEX idx_charge_points_town         ON charge_points (town);
CREATE INDEX idx_charge_points_operator_id  ON charge_points (operator_id);

CREATE INDEX idx_connections_charge_point_id     ON connections (charge_point_id);
CREATE INDEX idx_user_comments_charge_point_id   ON user_comments (charge_point_id);
CREATE INDEX idx_media_items_charge_point_id     ON media_items (charge_point_id);
CREATE INDEX idx_metadata_values_charge_point_id ON metadata_values (charge_point_id);
