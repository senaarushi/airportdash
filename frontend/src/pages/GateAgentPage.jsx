import { GateBoard } from '../components/GateBoard';
import { DecisionLog } from '../components/DecisionLog';
import { getAgentConfig } from '../utils/config';

export function GateAgentPage({ state, onFlightClick }) {
  const gates = state.gates ?? {};
  const flights = state.flights ?? {};
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;
  
  const cfg = getAgentConfig('gate_agent');

  return (
    <div className="agent-page fade-in">
      <div className="page-header">
        <div className="page-icon" style={{ color: cfg.color, borderColor: cfg.color }}>{cfg.icon}</div>
        <h1 className="page-title">Gate Agent Terminal</h1>
      </div>

      <div className="page-legend-row">
        <div className="legend-group">
          <div className="legend-group-title">Legend:</div>
          <div className="legend-item">
            <div className="legend-dot bg-gate-open" /> Open
          </div>
          <div className="legend-item">
            <div className="legend-dot bg-gate-occupied" /> Occupied
          </div>
          <div className="legend-item">
            <div className="legend-dot bg-gate-unavail" /> Unavailable
          </div>
        </div>
      </div>

      <div className="agent-page-grid">
        {/* LEFT: Gate Board */}
        <div className="panel panel-flex-col">
          <div className="panel-header">
            <h2>GATE OCCUPANCY OVERVIEW</h2>
          </div>
          <div className="panel-body">
             <GateBoard gates={gates} flights={flights} onFlightClick={onFlightClick} />
          </div>
        </div>

        {/* RIGHT: Agent Log */}
        <div className="panel-flex-col">
          <DecisionLog 
            entries={decisionLog} 
            currentTick={tick} 
            defaultFilter="gate_agent"
            hideFilters={true}
          />
        </div>
      </div>
    </div>
  );
}
