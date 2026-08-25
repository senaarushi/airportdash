#region Imports
import logging

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq

from app.core.models import DisruptionEvent
# REQUIRES: langchain-anthropic added to requirements.txt (currently
# missing; it pulls in the `anthropic` SDK as a transitive dependency).
# Also requires ANTHROPIC_API_KEY set in the environment, wire this up in
# config.py once that file exists rather than relying on an ambient env var.
#endregion Imports

logger = logging.getLogger("airport_ops.decisions.disruption")


class _PriorityAssessment(BaseModel):
    """
    Internal structured-output schema for this LLM call. Kept local to
    this file rather than in core/models.py or core/proposals.py, it's an
    implementation detail of this one decision function, not a domain
    object anything else depends on.
    """
    reasoning: str = Field(
        description="A concise, human-readable explanation of why this disruption needs attention and how urgently, suitable for direct display in a live decision log."
    )


# Haiku, not Sonnet/Opus: this call fires once per unresolved disruption
# per tick, a fast/cheap model is the right tradeoff for a high-frequency,
# low-complexity reasoning task. Escalate to a larger model only if
# response quality in testing actually needs it.
from app.config import get_settings, sync_groq_env
sync_groq_env(get_settings())
_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0)
_structured_llm = _llm.with_structured_output(_PriorityAssessment)


async def decide_disruption_priority(disruption: DisruptionEvent) -> str:
    """
    LLM-based: how urgently a specific disruption should be prioritized,
    given its type, severity, and how many flights it's touching, is a
    genuine judgment call, not a lookup, which is the split rationale for
    this file being LLM-based while gate/crew/ats_decisions.py are
    rule-based.

    NOTE: this function is async (it makes a network call). The current
    agents/disruption_agent.py shell computes its placeholder reasoning
    synchronously and inline, the call site needs to change to
    `reasoning = await decide_disruption_priority(disruption)` once this
    file is wired in.

    Falls back to a deterministic string on any API failure, a disruption
    with less nuanced priority text is a far better failure mode than one
    that crashes the simulation tick.

    EDITED (bug fix): the fallback previously swallowed the real exception,
    only `exc.__class__.__name__` (e.g. "BadRequestError") ever reached the
    decision log, with no way to see WHY. Every single call in an actual
    end-to-end run failed with BadRequestError and it was impossible to
    diagnose from the logs alone. Now logs the full exception (message,
    traceback) via logger.exception() before falling back, the fallback
    behavior itself (never crash the tick) is unchanged.
    """
    try:
        prompt = (
            f"A {disruption.disruption_type.value} disruption (severity "
            f"{int(disruption.severity)}/5) is affecting "
            f"{len(disruption.affected_flights)} flight(s): "
            f"{', '.join(disruption.affected_flights)}. "
            f"Description: {disruption.disruption_description}\n\n"
            "In one or two sentences, explain how urgently this needs "
            "attention and why, for an airport operations dashboard."
        )
        result: _PriorityAssessment = await _structured_llm.ainvoke(prompt)
        return result.reasoning
    except Exception as exc:
        # EDITED: log the real error so it's actually diagnosable, instead
        # of only the exception class name reaching the decision log.
        logger.exception(
            "decide_disruption_priority: LLM call failed for disruption %s, falling back to deterministic reasoning.",
            disruption.event_id,
        )
        # Never let an LLM/API failure take down the simulation tick.
        return (
            f"Disruption {disruption.event_id} (severity {int(disruption.severity)}) "
            f"remains unresolved, affecting {len(disruption.affected_flights)} flight(s). "
            f"[priority assessment unavailable: {exc.__class__.__name__}]"
        )
