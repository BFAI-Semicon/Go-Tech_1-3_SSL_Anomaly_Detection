from __future__ import annotations

from visa_gate.model.errors import VisaGateError
from visa_gate.model.ports import GateMetrics

_EVALUATION_FRAMEWORK_UNAVAILABLE = "evaluation_framework is not implemented"


def assemble_gate_metrics() -> GateMetrics:
    raise VisaGateError(_EVALUATION_FRAMEWORK_UNAVAILABLE)
