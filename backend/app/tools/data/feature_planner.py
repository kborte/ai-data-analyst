from uuid import NAMESPACE_DNS, UUID, uuid5

from app.schemas.common import DataType, FeatureOperationType
from app.schemas.features import FeatureDefinition
from app.schemas.profile import ColumnProfile, DataProfile

_MAX_SUGGESTIONS = 8
_REVENUE_KEYWORDS = ("revenue", "sales", "amount", "price", "total")
_ORDER_KEYWORDS = ("order",)
_USER_KEYWORDS = ("user", "customer", "client")
_CHANNEL_KEYWORDS = ("channel", "campaign", "source", "medium")


def _matches(col: ColumnProfile, keywords: tuple[str, ...]) -> bool:
    return any(k in col.column_name.lower() for k in keywords)


def _fid(seed: str) -> UUID:
    return uuid5(NAMESPACE_DNS, seed)


def generate_feature_suggestions(profile: DataProfile) -> list[FeatureDefinition]:
    cols = profile.column_profiles
    table = profile.table_name
    suggestions: list[FeatureDefinition] = []

    revenue_cols = [c for c in cols if _matches(c, _REVENUE_KEYWORDS)]
    order_cols = [c for c in cols if _matches(c, _ORDER_KEYWORDS)]
    user_cols = [c for c in cols if _matches(c, _USER_KEYWORDS)]
    channel_cols = [c for c in cols if _matches(c, _CHANNEL_KEYWORDS)]
    date_cols = [
        c for c in cols
        if c.is_likely_date or c.data_type in (DataType.date, DataType.datetime)
    ]
    categorical_cols = [c for c in cols if c.is_likely_categorical]

    def _add(f: FeatureDefinition) -> bool:
        if len(suggestions) >= _MAX_SUGGESTIONS:
            return False
        suggestions.append(f)
        return True

    for dc in date_cols:
        if not _add(FeatureDefinition(
            feature_id=_fid(f"{table}.date_extract.{dc.column_name}"),
            feature_name=f"date_parts_{dc.column_name}",
            display_name=f"Date parts from {dc.column_name}",
            operation_type=FeatureOperationType.date_extract,
            formula_display=(
                f"year({dc.column_name}), month({dc.column_name}), "
                f"week({dc.column_name}), weekday({dc.column_name})"
            ),
            input_table=table,
            output_column=f"{dc.column_name}_year",
            required_columns=[dc.column_name],
            parameters={
                "source_column": dc.column_name,
                "parts": ["year", "month", "week", "weekday"],
            },
            requires_human_approval=True,
        )):
            break

    if revenue_cols and order_cols:
        rev = revenue_cols[0].column_name
        ord_col = order_cols[0].column_name
        _add(FeatureDefinition(
            feature_id=_fid(f"{table}.ratio.aov"),
            feature_name="aov",
            display_name="Average Order Value (AOV)",
            operation_type=FeatureOperationType.ratio,
            formula_display=f"{rev} / {ord_col}",
            input_table=table,
            output_column="aov",
            required_columns=[rev, ord_col],
            parameters={"numerator": rev, "denominator": ord_col},
            requires_human_approval=True,
        ))

    if revenue_cols and user_cols:
        rev = revenue_cols[0].column_name
        user_col = user_cols[0].column_name
        _add(FeatureDefinition(
            feature_id=_fid(f"{table}.ratio.arpu"),
            feature_name="arpu",
            display_name="Average Revenue Per User (ARPU)",
            operation_type=FeatureOperationType.ratio,
            formula_display=f"{rev} / count_distinct({user_col})",
            input_table=table,
            output_column="arpu",
            required_columns=[rev, user_col],
            parameters={"numerator": rev, "denominator_distinct": user_col},
            requires_human_approval=True,
        ))

    if date_cols and revenue_cols:
        dc = date_cols[0].column_name
        rev = revenue_cols[0].column_name
        _add(FeatureDefinition(
            feature_id=_fid(f"{table}.window.running_revenue"),
            feature_name="running_revenue",
            display_name="Running Revenue",
            operation_type=FeatureOperationType.window,
            formula_display=f"cumsum({rev}) order by {dc}",
            input_table=table,
            output_column="running_revenue",
            required_columns=[dc, rev],
            parameters={"value_column": rev, "sort_column": dc},
            requires_human_approval=True,
        ))

    if date_cols and revenue_cols and channel_cols:
        dc = date_cols[0].column_name
        rev = revenue_cols[0].column_name
        ch = channel_cols[0].column_name
        _add(FeatureDefinition(
            feature_id=_fid(f"{table}.window.running_revenue_by_{ch}"),
            feature_name=f"running_revenue_by_{ch}",
            display_name=f"Running Revenue by {ch}",
            operation_type=FeatureOperationType.window,
            formula_display=f"cumsum({rev}) partition by {ch} order by {dc}",
            input_table=table,
            output_column=f"running_revenue_by_{ch}",
            required_columns=[dc, rev, ch],
            parameters={"value_column": rev, "sort_column": dc, "partition_column": ch},
            requires_human_approval=True,
        ))

    if categorical_cols and revenue_cols:
        cat = categorical_cols[0].column_name
        rev = revenue_cols[0].column_name
        _add(FeatureDefinition(
            feature_id=_fid(f"{table}.aggregate.revenue_by_{cat}"),
            feature_name=f"revenue_by_{cat}",
            display_name=f"Revenue by {cat}",
            operation_type=FeatureOperationType.aggregate,
            formula_display=f"sum({rev}) group by {cat}",
            input_table=table,
            output_table=f"revenue_by_{cat}",
            required_columns=[cat, rev],
            parameters={"value_column": rev, "group_by": cat, "aggregation": "sum"},
            requires_human_approval=True,
        ))

    return suggestions
