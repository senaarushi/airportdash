import { CrewPanel } from '../components/CrewPanel';
import { DecisionLog } from '../components/DecisionLog';
import { getAgentConfig } from '../utils/config';

export function CrewAgentPage({ state }) {
  const crew = state.crew ?? {};
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;
  
  const cfg = getAgentConfig('crew_agent');

  return (
    <div className="agent-page fade-in">
      <div className="page-header">
        <div className="page-icon" style={{ color: cfg.color, borderColor: cfg.color }}>{cfg.icon}</div>
        <h1 className="page-title">Ground Crew Operations</h1>
      </div>

      <div className="agent-page-grid">
        {/* LEFT: Crew Board */}
        <div className="panel panel-flex-col">
          <div className="panel-header">
            <h2>CREW ROSTER & SHIFTS</h2>
          </div>
          <div className="panel-body">
             <CrewPanel crew={crew} />
          </div>
        </div>

        {/* RIGHT: Agent Log */}
        <div className="panel-flex-col">
          <DecisionLog 
            entries={decisionLog} 
            currentTick={tick} 
            defaultFilter="crew_agent"
            hideFilters={true}
          />
        </div>
      </div>
    </div>
  );
}
