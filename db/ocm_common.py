"""Shared flattening logic for OCM export JSON -> relational rows.

Used by import_full.py (bulk COPY) and import_update.py (targeted upserts).
Column order in the *_COLS tuples matches db/schema.sql.
"""

import json
import subprocess

# ---------------------------------------------------------------- column maps

CHARGE_POINT_COLS = (
    "id", "uuid", "data_provider_id", "data_providers_reference",
    "operator_id", "operators_reference", "usage_type_id", "usage_cost",
    "number_of_points", "general_comments", "date_planned",
    "date_last_confirmed", "status_type_id", "date_last_status_update",
    "date_last_verified", "submission_status_type_id", "date_created",
    "country_code",
    # merged AddressInfo
    "address_id", "title", "address_line1", "address_line2", "town",
    "state_or_province", "postcode", "country_id", "latitude", "longitude",
    "distance_unit", "access_comments", "related_url", "contact_telephone1",
    "contact_telephone2", "contact_email",
)

CONNECTION_COLS = (
    "id", "charge_point_id", "connection_type_id", "reference",
    "status_type_id", "level_id", "amps", "voltage", "power_kw",
    "current_type_id", "quantity", "comments",
)

USER_COMMENT_COLS = (
    "id", "charge_point_id", "comment_type_id", "user_name", "comment",
    "related_url", "rating", "date_created", "user_id",
    "checkin_status_type_id", "is_actioned_by_editor",
)

MEDIA_ITEM_COLS = (
    "id", "charge_point_id", "item_url", "item_thumbnail_url", "comment",
    "is_enabled", "is_video", "is_featured_item", "is_external_resource",
    "user_id", "date_created",
)

METADATA_VALUE_COLS = ("id", "charge_point_id", "metadata_field_id", "item_value")

USER_COLS = ("id", "username")

# Reference tables: table name -> (json list key, cols, json field per col)
REFERENCE_TABLES = {
    "countries": ("Countries",
        ("id", "iso_code", "continent_code", "title"),
        ("ID", "ISOCode", "ContinentCode", "Title")),
    "operators": ("Operators",
        ("id", "title", "website_url", "comments", "phone_primary_contact",
         "phone_secondary_contact", "is_private_individual", "booking_url",
         "contact_email", "fault_report_email", "is_restricted_edit"),
        ("ID", "Title", "WebsiteURL", "Comments", "PhonePrimaryContact",
         "PhoneSecondaryContact", "IsPrivateIndividual", "BookingURL",
         "ContactEmail", "FaultReportEmail", "IsRestrictedEdit")),
    "usage_types": ("UsageTypes",
        ("id", "title", "is_pay_at_location", "is_membership_required",
         "is_access_key_required"),
        ("ID", "Title", "IsPayAtLocation", "IsMembershipRequired",
         "IsAccessKeyRequired")),
    "status_types": ("StatusTypes",
        ("id", "title", "is_operational", "is_user_selectable"),
        ("ID", "Title", "IsOperational", "IsUserSelectable")),
    "submission_status_types": ("SubmissionStatusTypes",
        ("id", "title", "is_live"),
        ("ID", "Title", "IsLive")),
    "connection_types": ("ConnectionTypes",
        ("id", "title", "formal_name", "is_discontinued", "is_obsolete"),
        ("ID", "Title", "FormalName", "IsDiscontinued", "IsObsolete")),
    "charger_types": ("ChargerTypes",
        ("id", "title", "comments", "is_fast_charge_capable"),
        ("ID", "Title", "Comments", "IsFastChargeCapable")),
    "current_types": ("CurrentTypes",
        ("id", "title", "description"),
        ("ID", "Title", "Description")),
    "user_comment_types": ("UserCommentTypes",
        ("id", "title"),
        ("ID", "Title")),
    "checkin_status_types": ("CheckinStatusTypes",
        ("id", "title", "is_positive", "is_automated_checkin"),
        ("ID", "Title", "IsPositive", "IsAutomatedCheckin")),
    "data_types": ("DataTypes",
        ("id", "title"),
        ("ID", "Title")),
}

DATA_PROVIDER_COLS = (
    "id", "title", "website_url", "comments", "data_provider_status_type_id",
    "is_restricted_edit", "is_open_data_licensed", "is_approved_import",
    "license", "date_last_imported",
)

METADATA_GROUP_COLS = ("id", "title", "data_provider_id", "is_restricted_edit",
                       "is_public_interest")
METADATA_FIELD_COLS = ("id", "metadata_group_id", "title", "data_type_id")
METADATA_FIELD_OPTION_COLS = ("id", "metadata_field_id", "title")
DATA_PROVIDER_STATUS_TYPE_COLS = ("id", "title", "is_provider_enabled")


# ------------------------------------------------------------- reference data

def flatten_reference_data(ref):
    """referencedata.json dict -> {table_name: [row_tuple, ...]} in insert order."""
    tables = {}

    # DataProviderStatusType is embedded in each DataProvider -> dedupe
    dpst = {}
    dp_rows = []
    for dp in ref.get("DataProviders") or []:
        st = dp.get("DataProviderStatusType")
        st_id = None
        if st:
            st_id = st["ID"]
            dpst[st_id] = (st_id, st.get("Title"), st.get("IsProviderEnabled"))
        dp_rows.append((
            dp["ID"], dp.get("Title"), dp.get("WebsiteURL"), dp.get("Comments"),
            st_id, dp.get("IsRestrictedEdit"), dp.get("IsOpenDataLicensed"),
            dp.get("IsApprovedImport"), dp.get("License"),
            dp.get("DateLastImported"),
        ))
    tables["data_provider_status_types"] = list(dpst.values())
    tables["data_providers"] = dp_rows

    for table, (key, _cols, fields) in REFERENCE_TABLES.items():
        tables[table] = [tuple(item.get(f) for f in fields)
                         for item in ref.get(key) or []]

    # MetadataGroups -> MetadataFields -> MetadataFieldOptions (nested)
    groups, fields_rows, options = [], [], []
    for g in ref.get("MetadataGroups") or []:
        groups.append((g["ID"], g.get("Title"), g.get("DataProviderID"),
                       g.get("IsRestrictedEdit"), g.get("IsPublicInterest")))
        for f in g.get("MetadataFields") or []:
            fields_rows.append((f["ID"], f.get("MetadataGroupID") or g["ID"],
                                f.get("Title"), f.get("DataTypeID")))
            for o in f.get("MetadataFieldOptions") or []:
                options.append((o["ID"], o.get("MetadataFieldID") or f["ID"],
                                o.get("Title")))
    tables["metadata_groups"] = groups
    tables["metadata_fields"] = fields_rows
    tables["metadata_field_options"] = options
    return tables


# Insert order respecting FK dependencies
REFERENCE_INSERT_ORDER = (
    "countries", "operators", "data_provider_status_types", "data_providers",
    "usage_types", "status_types", "submission_status_types",
    "connection_types", "charger_types", "current_types",
    "user_comment_types", "checkin_status_types", "data_types",
    "metadata_groups", "metadata_fields", "metadata_field_options",
)

REFERENCE_TABLE_COLS = {
    "data_provider_status_types": DATA_PROVIDER_STATUS_TYPE_COLS,
    "data_providers": DATA_PROVIDER_COLS,
    "metadata_groups": METADATA_GROUP_COLS,
    "metadata_fields": METADATA_FIELD_COLS,
    "metadata_field_options": METADATA_FIELD_OPTION_COLS,
    **{t: cols for t, (_k, cols, _f) in REFERENCE_TABLES.items()},
}


# ------------------------------------------------------------- charge points

class RefIds:
    """Known reference-table IDs, used to NULL-out dangling FKs."""

    def __init__(self, ref_tables):
        self.ids = {t: {row[0] for row in rows} for t, rows in ref_tables.items()}
        self.dangling = {}  # (table, id) -> count

    def check(self, table, value):
        if value is None or value in self.ids.get(table, ()):
            return value
        key = (table, value)
        self.dangling[key] = self.dangling.get(key, 0) + 1
        return None


def flatten_charge_point(d, country_code, ref_ids=None):
    """One OCM-<id>.json dict -> rows for charge_points and child tables.

    Returns dict: table -> list of row tuples (charge_points has exactly one).
    users rows may duplicate across files; caller dedupes.
    """
    def fk(table, value):
        return ref_ids.check(table, value) if ref_ids else value

    cp_id = d["ID"]
    a = d.get("AddressInfo") or {}
    cp_row = (
        cp_id, d.get("UUID"),
        fk("data_providers", d.get("DataProviderID")),
        d.get("DataProvidersReference"),
        fk("operators", d.get("OperatorID")),
        d.get("OperatorsReference"),
        fk("usage_types", d.get("UsageTypeID")),
        d.get("UsageCost"), d.get("NumberOfPoints"), d.get("GeneralComments"),
        d.get("DatePlanned"), d.get("DateLastConfirmed"),
        fk("status_types", d.get("StatusTypeID")),
        d.get("DateLastStatusUpdate"), d.get("DateLastVerified"),
        fk("submission_status_types", d.get("SubmissionStatusTypeID")),
        d.get("DateCreated"), country_code,
        a.get("ID"), a.get("Title"), a.get("AddressLine1"),
        a.get("AddressLine2"), a.get("Town"), a.get("StateOrProvince"),
        a.get("Postcode"), fk("countries", a.get("CountryID")),
        a.get("Latitude"), a.get("Longitude"), a.get("DistanceUnit"),
        a.get("AccessComments"), a.get("RelatedURL"),
        a.get("ContactTelephone1"), a.get("ContactTelephone2"),
        a.get("ContactEmail"),
    )

    conns = [(
        c["ID"], cp_id,
        fk("connection_types", c.get("ConnectionTypeID")),
        c.get("Reference"),
        fk("status_types", c.get("StatusTypeID")),
        fk("charger_types", c.get("LevelID")),
        c.get("Amps"), c.get("Voltage"), c.get("PowerKW"),
        fk("current_types", c.get("CurrentTypeID")),
        c.get("Quantity"), c.get("Comments"),
    ) for c in d.get("Connections") or []]

    users, comments, media, mvalues = [], [], [], []

    for uc in d.get("UserComments") or []:
        u = uc.get("User")
        if u:
            users.append((u["ID"], u.get("Username")))
        comments.append((
            uc["ID"], cp_id,
            fk("user_comment_types", uc.get("CommentTypeID")),
            uc.get("UserName"), uc.get("Comment"), uc.get("RelatedURL"),
            uc.get("Rating"), uc.get("DateCreated"),
            u["ID"] if u else None,
            fk("checkin_status_types", uc.get("CheckinStatusTypeID")),
            uc.get("IsActionedByEditor"),
        ))

    for mi in d.get("MediaItems") or []:
        u = mi.get("User")
        if u:
            users.append((u["ID"], u.get("Username")))
        media.append((
            mi["ID"], cp_id, mi.get("ItemURL"), mi.get("ItemThumbnailURL"),
            mi.get("Comment"), mi.get("IsEnabled"), mi.get("IsVideo"),
            mi.get("IsFeaturedItem"), mi.get("IsExternalResource"),
            u["ID"] if u else None, mi.get("DateCreated"),
        ))

    for mv in d.get("MetadataValues") or []:
        mvalues.append((mv["ID"], cp_id,
                        fk("metadata_fields", mv.get("MetadataFieldID")),
                        mv.get("ItemValue")))

    return {
        "charge_points": [cp_row],
        "connections": conns,
        "users": users,
        "user_comments": comments,
        "media_items": media,
        "metadata_values": mvalues,
    }


CHILD_TABLE_COLS = {
    "connections": CONNECTION_COLS,
    "user_comments": USER_COMMENT_COLS,
    "media_items": MEDIA_ITEM_COLS,
    "metadata_values": METADATA_VALUE_COLS,
}


# ---------------------------------------------------------------------- misc

def git_output(repo_root, *args):
    return subprocess.run(("git", "-C", repo_root) + args,
                          capture_output=True, text=True, check=True).stdout

def git_show_json(repo_root, ref, path):
    """Load a JSON file as it exists at the given git ref."""
    return json.loads(git_output(repo_root, "show", f"{ref}:{path}"))
