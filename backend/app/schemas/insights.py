from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ArtifactStatus, InsightSeverity


class Insight(BaseModel):
    insight_id: UUID
    title: str
    observation: str
    possible_explanations: list[str] = []
    evidence: list[str] = []
    caveats: list[str] = []
    severity: InsightSeverity
    recommended_followups: list[str] = []


class InsightReport(BaseModel):
    report_id: UUID
    dataset_version_id: UUID
    analysis_run_id: UUID | None = None
    executive_summary: str
    key_observations: list[str] = []
    insights: list[Insight] = []
    data_quality_caveats: list[str] = []
    status: ArtifactStatus
    created_at: datetime
