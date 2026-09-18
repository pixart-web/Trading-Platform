"""Local CLI mechanics on committed SQLite; no network or broker calls."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from pocket_alpha.common.clock import FrozenClock
from pocket_alpha.database import Base
from pocket_alpha.paper_trading import __main__ as cli
from pocket_alpha.paper_trading.models import PaperConfig
from tests.backtest_fixtures import config, dataset
from tests.market_fixtures import START


def test_observer_cli_commits_and_exposes_only_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "paper.sqlite"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(cli, "build_engine", lambda settings: engine)
    monkeypatch.setattr(cli, "SystemClock", lambda: FrozenClock(START + timedelta(seconds=10)))
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    data = dataset().inputs
    cfg = PaperConfig(
        origin="SYNTHETIC",
        asset=data.asset,
        market=data.market,
        venue=data.venue,
        mapping=data.mapping,
        timeframe=data.query.timeframe,
        start=START,
        maximum_events=20,
        run=config(strategy=cli.Observer.identity),
    )
    path = tmp_path / "config.json"
    path.write_text(cfg.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["paper", "create", str(path)])
    cli.main()
    state = json.loads(capsys.readouterr().out)
    key = state["account_id"]
    assert state["mode"] == "PAPER" and not state["fills"] and not state["live_ready"]
    for command in ("inspect", "heartbeat", "disconnect", "reconcile", "kill", "close"):
        monkeypatch.setattr("sys.argv", ["paper", command, key])
        cli.main()
        result = json.loads(capsys.readouterr().out)
        assert result["mode"] == "PAPER" and not result["live_ready"]
    assert result["status"] == "CLOSED"
    monkeypatch.setattr("sys.argv", ["paper", "inspect", "00000000-0000-0000-0000-000000000000"])
    with pytest.raises(LookupError):
        cli.main()
    path.write_text(cfg.model_copy(update={"run": config()}).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["paper", "create", str(path)])
    with pytest.raises(ValueError, match="observation only"):
        cli.main()
    with pytest.raises(ValueError, match="checkpoint"):
        cli.Observer().restore('{"other":1}')
