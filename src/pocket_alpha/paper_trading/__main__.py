"""Local, explicit PAPER observer CLI; custom strategies use the trusted Python service."""

import argparse
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from pocket_alpha.backtesting.models import Intent, StrategyIdentity, StrategyView
from pocket_alpha.common.clock import SystemClock
from pocket_alpha.config import Settings
from pocket_alpha.database import build_engine
from pocket_alpha.market_data.storage import MarketRepository
from pocket_alpha.observability import configure_logging
from pocket_alpha.paper_trading.feed import PublicPaperPoller
from pocket_alpha.paper_trading.models import PaperConfig, PaperInput, canonical_state
from pocket_alpha.paper_trading.service import PaperService
from pocket_alpha.paper_trading.storage import PaperRepository


class Observer:
    identity = StrategyIdentity(
        strategy_version="paper-observer-1", model_version="none-observation-1", parameters=()
    )

    def on_event(self, view: StrategyView) -> tuple[Intent, ...]:
        return ()

    def checkpoint(self) -> str:
        return "{}"

    def restore(self, checkpoint: str) -> None:
        if canonical_state(checkpoint) != "{}":
            raise ValueError("PAPER observer checkpoint mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PAPER only: explicit public-data observation; never real orders"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("config", type=Path)
    for name in ("inspect", "poll", "heartbeat", "disconnect", "reconcile", "kill", "close"):
        command = commands.add_parser(name)
        command.add_argument("account_id", type=UUID)
    args = parser.parse_args()
    configure_logging()
    engine = build_engine(Settings())
    try:
        with Session(engine) as session, session.begin():
            paper = PaperService(PaperRepository(session), SystemClock())
            strategy = Observer()
            if args.command == "create":
                cfg = PaperConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
                if cfg.run.strategy != strategy.identity:
                    raise ValueError(
                        "CLI supports observation only; custom strategies use the trusted service"
                    )
                MarketRepository(session).register(cfg.asset, cfg.venue, cfg.market, cfg.mapping)
                result = paper.create(cfg, strategy).model_dump_json()
            else:
                view = paper.view(args.account_id)
                if view is None:
                    raise LookupError("PAPER account not found")
                if args.command == "inspect":
                    result = view.model_dump_json()
                else:
                    if view.config.run.strategy != strategy.identity:
                        raise ValueError("CLI cannot operate a custom strategy account")
                    if args.command == "poll":
                        state = PublicPaperPoller(paper).poll(args.account_id, strategy)
                    else:
                        state = paper.process(
                            args.account_id,
                            PaperInput(
                                event_id=uuid4(),
                                at=paper.clock.now(),
                                kind=args.command.upper(),
                                reconciliation_hash=view.state.accounting_hash
                                if args.command == "reconcile"
                                else None,
                            ),
                            strategy,
                            view.state.revision,
                        )
                    result = state.model_dump_json()
        print(result)  # Only print success after the transaction commits.
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
