"""
Worker entry point: uv run python -m app.worker

Polls the jobs table, claims one job at a time, executes it, then loops.
Sleeps POLL_INTERVAL seconds when the queue is empty.
"""

import logging
import time

from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds to sleep when no jobs are queued


def main() -> None:
    import app.repositories.database as db_repos  # noqa: PLC0415
    from app.db.base import SessionLocal  # noqa: PLC0415
    from app.dependencies import Repos  # noqa: PLC0415
    from app.worker.runner import run_one  # noqa: PLC0415

    from app.dependencies import get_llm_provider, get_storage  # noqa: PLC0415

    storage = get_storage()
    llm = get_llm_provider()

    logger.info("worker started, polling every %ds", POLL_INTERVAL)
    while True:
        session = SessionLocal()
        try:
            job_repo = db_repos.JobRepository(session)
            repos = Repos(
                data_source=db_repos.DataSourceRepository(session),
                uploaded_file=db_repos.UploadedFileRepository(session),
                dataset=db_repos.DatasetRepository(session),
                dataset_source=db_repos.DatasetSourceRepository(session),
                dataset_version=db_repos.DatasetVersionRepository(session),
                dataset_table=db_repos.DatasetTableRepository(session),
                context_document=db_repos.ContextDocumentRepository(session),
                profile=db_repos.DataProfileRepository(session),
                cleaning_plan=db_repos.CleaningPlanRepository(session),
                cleaning_result=db_repos.CleaningResultRepository(session),
                feature_plan=db_repos.FeaturePlanRepository(session),
                feature_result=db_repos.FeatureResultRepository(session),
                visualization_plan=db_repos.VisualizationPlanRepository(session),
                visualization_result=db_repos.VisualizationResultRepository(session),
                job=job_repo,
            )
            processed = run_one(job_repo, repos, storage=storage, llm=llm)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("unexpected error in worker loop")
            processed = False
        finally:
            session.close()

        if not processed:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
