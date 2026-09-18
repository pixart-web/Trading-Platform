from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pocket_alpha.database import Base
from pocket_alpha.research.models import StudyPlan, Variant
from pocket_alpha.research.service import HoldoutConsumed, ResearchService, consume_final
from pocket_alpha.research.storage import HoldoutRecord, ResearchRepository
from pocket_alpha.research.temporal import economic_key
from tests.research_fixtures import CLOCK, Callback, Factory, plan, seed


def test_holdout_is_committed_once_freezes_artifact_and_cannot_retry(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "holdout.sqlite"))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            repository = ResearchRepository(session)
            data = seed(repository)
            study = plan(data)
            experiments = ResearchService(repository, CLOCK).run(study, Factory())
            session.commit()
        factory = Factory()
        final = consume_final(engine, study.study_id, "baseline", factory, CLOCK)
        assert factory.training == []
        assert len(final.trials) == 1 and final.stage == "FINAL_HOLDOUT"
        assert final.trials[0].fitted_artifact_hash == next(
            t.fitted_artifact_hash
            for t in experiments.trials
            if t.variant == "baseline" and t.fold == study.folds[-1].name and t.partition == "TEST"
        )
        with Session(engine) as session:
            assert ResearchRepository(session).get(final.report_id) == final
            assert session.get(HoldoutRecord, economic_key(data)) is not None
        with pytest.raises(HoldoutConsumed):
            consume_final(engine, study.study_id, "quantity", Factory(), CLOCK)
        # A renamed study cannot grant another final attempt for the same economic asset.
        second = StudyPlan.model_validate(
            study.model_dump() | dict(version="synthetic-study-renamed")
        )
        with Session(engine) as session:
            ResearchService(ResearchRepository(session), CLOCK).run(second, Factory())
            session.commit()
        with pytest.raises(HoldoutConsumed):
            consume_final(engine, second.study_id, "baseline", Factory(), CLOCK)
    finally:
        engine.dispose()


def test_failed_final_materialization_does_not_release_consumption(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "failed.sqlite"))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            repository = ResearchRepository(session)
            study = plan(seed(repository))
            ResearchService(repository, CLOCK).run(study, Factory())
            session.commit()

        class Failed(Factory):
            def materialize(self, artifact_json: str, variant: Variant) -> Callback:
                raise RuntimeError("research dependency unavailable")

        with pytest.raises(RuntimeError):
            consume_final(engine, study.study_id, "baseline", Failed(), CLOCK)
        with pytest.raises(HoldoutConsumed):
            consume_final(engine, study.study_id, "baseline", Factory(), CLOCK)
    finally:
        engine.dispose()
