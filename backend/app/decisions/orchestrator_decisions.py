#region Imports
import logging

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq

from app.core.proposals import AgentProposal
# REQUIRES: langchain-anthropic added to requirements.txt (currently
# missing). Also requires ANTHROPIC_API_KEY set in the environment.
#endregion Imports

logger = logging.getLogger("airport_ops.decisions.orchestrator")


class _ResolutionChoice(BaseModel):
    winning_proposal_id: str = Field(
        description="The proposal_id of the proposal that should win this conflict."
    )
    reasoning: str = Field(
        description="A concise explanation of why this proposal was chosen over the others, suitable for the decision log."
    )

from app.config import get_settings, sync_groq_env
sync_groq_env(get_settings())
_llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0)
_structured_llm = _llm.with_structured_output(_ResolutionChoice)


async def decide_conflict_resolution(competing_proposals: list[AgentProposal]) -> AgentProposal:
    """
    LLM-based: choosing which of several competing proposals should win a
    genuine resource conflict (e.g. two flights wanting the same gate) is
    a multi-factor judgment call, not a lookup, exactly the kind of
    decision worth spending an LLM call on, and it conveniently produces
    the natural-language reasoning the decision log already wants.

    CRITICAL SAFETY CHECK: the LLM's chosen winning_proposal_id is
    validated against the actual candidate set before being trusted. An
    LLM returning an id that doesn't correspond to any real competing
    proposal (hallucination) must never be allowed to silently corrupt
    state, a hallucinated gate/crew assignment is far worse than a
    slightly-less-optimal deterministic fallback. Falls back to the first
    proposal on any invalid response or API failure.

    EDITED (bug fix): the fallback previously swallowed the real exception
    entirely (`except Exception: pass`). In an actual end-to-end run, every
    single call failed and there was no way to tell why from the logs.
    Now logs the full exception via logger.exception() before falling
    back, the fallback behavior itself (return competing_proposals[0]) is
    unchanged.
    """
    if len(competing_proposals) == 1:
        return competing_proposals[0]

    try:
        summary = "\n".join(
            f'- proposal_id={p.proposal_id}, agent={p.agent_id}, reasoning="{p.reasoning}"'
            for p in competing_proposals
        )
        prompt = (
            f"{len(competing_proposals)} agents are competing for the same "
            f"airport resource this tick:\n{summary}\n\n"
            "Choose which proposal should win, considering operational "
            "impact and the stated reasoning for each. Return the exact "
            "proposal_id of your chosen winner."
        )
        result: _ResolutionChoice = await _structured_llm.ainvoke(prompt)

        valid_ids = {p.proposal_id for p in competing_proposals}
        if result.winning_proposal_id in valid_ids:
            winner = next(p for p in competing_proposals if p.proposal_id == result.winning_proposal_id)
            # Replace reasoning with the LLM's explanation so it flows into
            # the decision log exactly as orchestrator.py expects.
            return winner.model_copy(update={"reasoning": result.reasoning})
        # LLM returned an id that doesn't correspond to any real proposal,
        # do not trust it, fall through to the deterministic fallback below.
        logger.warning(
            "decide_conflict_resolution: LLM returned an unknown proposal_id (%s), falling back to first proposal.",
            result.winning_proposal_id,
        )
    except Exception:
        # EDITED: log the real error so it's actually diagnosable, instead
        # of silently discarding it.
        logger.exception(
            "decide_conflict_resolution: LLM call failed, falling back to first proposal."
        )

    return competing_proposals[0]
