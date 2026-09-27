# OCM Export — Relational Database Structure

Relational model for the Open Charge Map per-POI export in this repo
(`data/referencedata.json` + `data/<ISO2>/OCM-<id>.json`, one file per charging station).

Design goals: **as simple as possible, as close to the original JSON as possible.**
All primary keys are the original OCM IDs (natural keys, no serials).
JSON `PascalCase` fields map 1:1 to `snake_case` columns.

## ER Diagram

```mermaid
erDiagram
    charge_points {
        int id PK "OCM ID"
        text uuid
        int data_provider_id FK
        text data_providers_reference
        int operator_id FK
        text operators_reference
        int usage_type_id FK
        text usage_cost
        int number_of_points
        text general_comments
        timestamp date_planned
        timestamp date_last_confirmed
        int status_type_id FK
        timestamp date_last_status_update
        timestamp date_last_verified
        int submission_status_type_id FK
        timestamp date_created
        text country_code "folder name (ISO2)"
        int address_id "AddressInfo.ID (merged 1:1)"
        text title "AddressInfo.Title"
        text address_line1
        text address_line2
        text town
        text state_or_province
        text postcode
        int country_id FK
        double latitude
        double longitude
        int distance_unit
        text access_comments
        text related_url
        text contact_telephone1
        text contact_telephone2
        text contact_email
    }

    connections {
        int id PK
        int charge_point_id FK
        int connection_type_id FK
        text reference
        int status_type_id FK
        int level_id FK "-> charger_types"
        double amps
        double voltage
        numeric power_kw
        int current_type_id FK
        int quantity
        text comments
    }

    users {
        int id PK
        text username
    }

    user_comments {
        int id PK
        int charge_point_id FK
        int comment_type_id FK
        text user_name
        text comment
        text related_url
        int rating
        timestamp date_created
        int user_id FK
        int checkin_status_type_id FK
        boolean is_actioned_by_editor
    }

    media_items {
        int id PK
        int charge_point_id FK
        text item_url
        text item_thumbnail_url
        text comment
        boolean is_enabled
        boolean is_video
        boolean is_featured_item
        boolean is_external_resource
        int user_id FK
        timestamp date_created
    }

    metadata_values {
        int id PK
        int charge_point_id FK
        int metadata_field_id FK
        text item_value
    }

    countries {
        int id PK
        text iso_code
        text continent_code
        text title
    }

    operators {
        int id PK
        text title
        text website_url
        text comments
        text phone_primary_contact
        text phone_secondary_contact
        boolean is_private_individual
        text booking_url
        text contact_email
        text fault_report_email
        boolean is_restricted_edit
    }

    data_providers {
        int id PK
        text title
        text website_url
        text comments
        int data_provider_status_type_id FK
        boolean is_restricted_edit
        boolean is_open_data_licensed
        boolean is_approved_import
        text license
        timestamp date_last_imported
    }

    data_provider_status_types {
        int id PK
        text title
        boolean is_provider_enabled
    }

    usage_types {
        int id PK
        text title
        boolean is_pay_at_location
        boolean is_membership_required
        boolean is_access_key_required
    }

    status_types {
        int id PK
        text title
        boolean is_operational
        boolean is_user_selectable
    }

    submission_status_types {
        int id PK
        text title
        boolean is_live
    }

    connection_types {
        int id PK
        text title
        text formal_name
        boolean is_discontinued
        boolean is_obsolete
    }

    charger_types {
        int id PK "aka Level"
        text title
        text comments
        boolean is_fast_charge_capable
    }

    current_types {
        int id PK
        text title
        text description
    }

    user_comment_types {
        int id PK
        text title
    }

    checkin_status_types {
        int id PK
        text title
        boolean is_positive
        boolean is_automated_checkin
    }

    data_types {
        int id PK
        text title
    }

    metadata_groups {
        int id PK
        text title
        int data_provider_id FK
        boolean is_restricted_edit
        boolean is_public_interest
    }

    metadata_fields {
        int id PK
        int metadata_group_id FK
        text title
        int data_type_id FK
    }

    metadata_field_options {
        int id PK
        int metadata_field_id FK
        text title
    }

    import_state {
        text key PK
        text value
    }

    charge_points ||--o{ connections : "Connections[]"
    charge_points ||--o{ user_comments : "UserComments[]"
    charge_points ||--o{ media_items : "MediaItems[]"
    charge_points ||--o{ metadata_values : "MetadataValues[]"

    countries ||--o{ charge_points : ""
    operators ||--o{ charge_points : ""
    data_providers ||--o{ charge_points : ""
    usage_types ||--o{ charge_points : ""
    status_types ||--o{ charge_points : ""
    submission_status_types ||--o{ charge_points : ""

    connection_types ||--o{ connections : ""
    charger_types ||--o{ connections : "LevelID"
    current_types ||--o{ connections : ""
    status_types ||--o{ connections : ""

    users ||--o{ user_comments : "User{}"
    users ||--o{ media_items : "User{}"
    user_comment_types ||--o{ user_comments : ""
    checkin_status_types ||--o{ user_comments : ""

    data_provider_status_types ||--o{ data_providers : ""
    data_providers ||--o{ metadata_groups : ""
    metadata_groups ||--o{ metadata_fields : ""
    data_types ||--o{ metadata_fields : ""
    metadata_fields ||--o{ metadata_field_options : ""
    metadata_fields ||--o{ metadata_values : ""
```

## JSON → table mapping

| JSON source | Table |
|---|---|
| `data/<CC>/OCM-<id>.json` (top level) | `charge_points` |
| `.AddressInfo` (merged, see notes) | `charge_points` (`address_id`, `title`, `address_line1` … `contact_email`) |
| `.Connections[]` | `connections` |
| `.UserComments[]` | `user_comments` |
| `.MediaItems[]` | `media_items` |
| `.MetadataValues[]` | `metadata_values` |
| `.UserComments[].User`, `.MediaItems[].User` | `users` (deduped) |
| `referencedata.json .Countries` | `countries` |
| `… .Operators` | `operators` |
| `… .DataProviders` | `data_providers` |
| `… .DataProviders[].DataProviderStatusType` | `data_provider_status_types` (deduped) |
| `… .UsageTypes` | `usage_types` |
| `… .StatusTypes` | `status_types` |
| `… .SubmissionStatusTypes` | `submission_status_types` |
| `… .ConnectionTypes` | `connection_types` |
| `… .ChargerTypes` | `charger_types` |
| `… .CurrentTypes` | `current_types` |
| `… .UserCommentTypes` | `user_comment_types` |
| `… .CheckinStatusTypes` | `checkin_status_types` |
| `… .DataTypes` | `data_types` |
| `… .MetadataGroups` | `metadata_groups` |
| `… .MetadataGroups[].MetadataFields[]` | `metadata_fields` |
| `… .MetadataGroups[].MetadataFields[].MetadataFieldOptions[]` | `metadata_field_options` |
| (bookkeeping, not from JSON) | `import_state` |

## Design notes

- **AddressInfo is merged into `charge_points`.** Verified against the data: every one
  of 23,376 checked files has exactly one `AddressInfo` object, no `AddressInfo.ID` is
  shared between two stations, and the ID stays stable when the address is edited
  (60 address edits in one commit, 0 ID changes). Addresses are edited in place — the
  export carries no address history (history lives in git). The original
  `AddressInfo.ID` is preserved as `charge_points.address_id`.
- **`charge_points.country_code`** is the containing folder name (ISO2). It duplicates
  what `country_id → countries.iso_code` provides, but makes per-country queries and
  git-diff reconciliation trivial.
- **`ChargerTypes` = "Level".** `connections.level_id` references `charger_types.id`
  (OCM calls the same entity ChargerType in reference data and `LevelID` in connections).
- **`users`** contains only `{ID, Username}` — that is all the export embeds. Users are
  global entities: the incremental update only upserts them and never deletes a user
  whose comments/photos have disappeared, so `users` may retain rows no longer referenced.
- **`Operators[].AddressInfo`** is null for all 968 operators in the current export and
  is therefore omitted.
- **FK safety:** station files can reference IDs missing from `referencedata.json`.
  The import scripts NULL-out (and log) any dangling reference rather than fail.
- **`import_state`** stores the last-imported git commit (`key='last_commit'`) so the
  incremental update script knows its diff base.
- Types are database-neutral: `INTEGER`, `TEXT`, `BOOLEAN`, `TIMESTAMP`,
  `DOUBLE PRECISION`, `NUMERIC`. Timestamps are stored as given (UTC, `Z`-suffixed
  in source).
