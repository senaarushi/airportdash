#region Imports
from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.proposals import DisruptionInjectionProposal
from app.decisions.disruption_decisions import decide_disruption_priority

if TYPE_CHECKING:
    from app.agents.graph import GraphState
#endregion Imports


async def disruption_agent_node(state: "GraphState") -> dict:
    """
    IMPORTANT DESIGN NOTE, still true and worth keeping in mind: core/
    simulator.py already auto-injects scripted disruptions directly into
    board.open_disruptions once their trigger_time arrives (Decision #22),
    independent of this agent entirely. So this agent's current role is
    narrower than its name suggests, it does NOT decide *whether* a
    scripted disruption fires, Simulator's world-clock already owns that.
    What it DOES do: scans already-injected, unresolved disruptions and
    re-emits them as DisruptionInjectionProposals each tick they remain
    unresolved, now with an LLM-generated priority/reasoning (Decision
    #30/#31) rather than a canned string, essentially escalating/keeping
    them in Orchestrator's attention until resolved.

    The more interesting future role for this agent (proposing genuinely
    NEW disruptions the agent itself predicts or derives, not scripted
    ones) still isn't implemented here, this shell only handles the
    escalation case.

    Never writes shared state (Decision #19).
    """
    proposals: list[DisruptionInjectionProposal] = []
    board = state.snapshot

    for disruption in board.open_disruptions:
        if disruption.resolved:
            continue

        reasoning = await decide_disruption_priority(disruption)

        proposals.append(
            DisruptionInjectionProposal(
                agent_id="disruption_agent",
                tick=board.current_tick,
                reasoning=reasoning,
                disruption_event=disruption,
            )
        )

    return {"proposals": proposals}