"""Explicit synthetic broker for mechanism tests; it never connects to a venue."""

import hashlib
from decimal import Decimal
from typing import Literal

from pocket_alpha.common.clock import Clock, SystemClock, utc
from pocket_alpha.derivative_execution.models import (
    DerivativeBrokerReport,
    DerivativeExecutionRequest,
)


class SyntheticDerivativeBroker:
    origin: Literal["REAL", "SYNTHETIC"] = "SYNTHETIC"

    def __init__(self, *, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()
        self.reports: dict[str, DerivativeBrokerReport] = {}
        self.submissions = 0

    def submit(self, client_id: str, request: DerivativeExecutionRequest) -> DerivativeBrokerReport:
        self.submissions += 1
        existing = self.reports.get(client_id)
        if existing is not None:
            return existing
        intent = request.intent
        report = DerivativeBrokerReport(
            client_id=client_id,
            contract_id=intent.contract_id,
            position_side=intent.position_side,
            order_side=intent.order_side,
            effect=intent.effect,
            reduce_only=intent.reduce_only,
            order_id="synthetic-" + hashlib.sha256(client_id.encode()).hexdigest()[:24],
            status="NEW",
            original_contracts=intent.contracts,
            limit_price=intent.limit_price,
            executed_contracts=Decimal(0),
            cumulative_settlement_value=Decimal(0),
            commissions=(),
            realized_pnl=Decimal(0),
            funding_paid=Decimal(0),
            at=utc(self.clock.now()),
        )
        self.reports[client_id] = report
        return report

    def query(self, client_id: str, contract_id: str) -> DerivativeBrokerReport | None:
        report = self.reports.get(client_id)
        if report is not None and report.contract_id != contract_id:
            return None
        return report

    def publish(self, report: DerivativeBrokerReport) -> None:
        if report.client_id not in self.reports:
            raise ValueError("synthetic order was not submitted")
        current = self.reports[report.client_id]
        if report.order_id != current.order_id or report.contract_id != current.contract_id:
            raise ValueError("synthetic report identity mismatch")
        self.reports[report.client_id] = DerivativeBrokerReport.model_validate_json(
            report.model_dump_json()
        )
