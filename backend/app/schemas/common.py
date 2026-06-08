from enum import StrEnum


class ArtifactStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class WorkspaceRole(StrEnum):
    owner = "owner"
    manager = "manager"
    editor = "editor"
    viewer = "viewer"


class DataSourceKind(StrEnum):
    uploaded_file = "uploaded_file"
    google_sheets = "google_sheets"
    sql_database = "sql_database"
    s3 = "s3"
    api = "api"
    manual = "manual"


class UploadedFileKind(StrEnum):
    csv = "csv"
    excel = "excel"
    text = "text"
    markdown = "markdown"
    pdf = "pdf"
    other = "other"


class DatasetSourceRole(StrEnum):
    primary = "primary"
    lookup = "lookup"
    context = "context"
    supplementary = "supplementary"
    joined = "joined"
    reference = "reference"


class DatasetVersionType(StrEnum):
    original = "original"
    cleaned = "cleaned"
    enriched = "enriched"
    filtered = "filtered"
    joined = "joined"
    aggregated = "aggregated"


class DataType(StrEnum):
    integer = "integer"
    float_ = "float"
    string = "string"
    boolean = "boolean"
    date = "date"
    datetime = "datetime"
    categorical = "categorical"
    unknown = "unknown"


class ImpactLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    modified = "modified"


class DefaultDecision(StrEnum):
    approve = "approve"
    reject = "reject"
    require_review = "require_review"


class UserDecision(StrEnum):
    approve = "approve"
    reject = "reject"
    modify = "modify"


class IssueType(StrEnum):
    missing_values = "missing_values"
    duplicate_rows = "duplicate_rows"
    outlier = "outlier"
    type_mismatch = "type_mismatch"
    inconsistent_format = "inconsistent_format"
    invalid_value = "invalid_value"
    whitespace = "whitespace"
    encoding_error = "encoding_error"
    numeric_stored_as_text = "numeric_stored_as_text"
    date_stored_as_text = "date_stored_as_text"
    high_cardinality_category = "high_cardinality_category"
    mixed_types = "mixed_types"


class CleaningOperationType(StrEnum):
    drop_rows = "drop_rows"
    fill_missing = "fill_missing"
    replace_value = "replace_value"
    cast_type = "cast_type"
    strip_whitespace = "strip_whitespace"
    normalize_format = "normalize_format"
    drop_column = "drop_column"
    rename_column = "rename_column"
    deduplicate = "deduplicate"
    clip_outlier = "clip_outlier"
    ignore_issue = "ignore_issue"
    parse_dates = "parse_dates"


class FeatureOperationType(StrEnum):
    ratio = "ratio"
    arithmetic = "arithmetic"
    aggregate = "aggregate"
    window = "window"
    period_change = "period_change"
    date_extract = "date_extract"
    bucketize = "bucketize"
    custom_formula = "custom_formula"


class ChartType(StrEnum):
    line = "line"
    bar = "bar"
    scatter = "scatter"
    histogram = "histogram"
    pie = "pie"
    heatmap = "heatmap"
    box = "box"
    area = "area"
    table = "table"


class InsightSeverity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AnalysisRunStatus(StrEnum):
    created = "created"
    profiling = "profiling"
    cleaning = "cleaning"
    feature_engineering = "feature_engineering"
    visualization = "visualization"
    insight_generation = "insight_generation"
    completed = "completed"
    failed = "failed"


class ExecutionStatus(StrEnum):
    success = "success"
    skipped = "skipped"
    failed = "failed"
    partial = "partial"
