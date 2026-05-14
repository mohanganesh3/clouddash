"""Two-layer guardrails: input (pre-LLM) + output (post-LLM) with self-correction.

Public API — import only from this package, never from submodules:

    from clouddash.guardrails import (
        evaluate_input,
        evaluate_output,
        build_blocked_input_response,
        InputDecision,
        OutputDecision,
    )
"""

from clouddash.guardrails.pipeline import (
    InputDecision,
    OutputDecision,
    build_blocked_input_response,
    evaluate_input,
    evaluate_output,
)

__all__ = [
    "InputDecision",
    "OutputDecision",
    "build_blocked_input_response",
    "evaluate_input",
    "evaluate_output",
]

