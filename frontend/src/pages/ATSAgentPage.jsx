import { FlightTimeline } from '../components/FlightTimeline';
import { DecisionLog } from '../components/DecisionLog';
import { getAgentConfig } from '../utils/config';

export function ATSAgentPage({ state, onFlightClick }) {
  const flights = state.flights ?? {};
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;
  
  const cfg = getAgentConfig('ats_agent');

  return (
    <div className="agent-page fade-in">
      <div className="page-header">
        <div className="page-icon" style={{ color: cfg.color, borderColor: cfg.color }}>{cfg.icon}</div>
        <h1 className="page-title">Air Traffic & Schedule (ATS)</h1>
      </div>

      <div className="page-legend-row">
        <div className="legend-group">
          <div className="legend-group-title">Flight Status:</div>
          <div className="legend-item"><div className="legend-dot bg-status-scheduled" /> Scheduled</div>
          <div className="legend-item"><div className="legend-dot bg-status-in-air" /> In Air</div>
          <div className="legend-item"><div className="legend-dot bg-status-landed" /> Landed</div>
          <div className="legend-item"><div className="legend-dot bg-status-at-gate" /> At Gate</div>
          <div className="legend-item"><div className="legend-dot bg-status-pushback" /> Pushback</div>
          <div className="legend-item"><div className="legend-dot bg-status-departed" /> Departed</div>
          <div className="legend-item"><div className="legend-dot bg-status-cancelled" /> Cancelled</div>
        </div>
      </div>

      <div className="agent-page-grid">
        {/* LEFT: Flight Timeline */}
        <div className="panel panel-flex-col">
          <div className="panel-header">
            <h2>FLIGHT SCHEDULE OVERVIEW</h2>
          </div>
          <div className="panel-body">
             <FlightTimeline flights={flights} onFlightClick={onFlightClick} />
          </div>
        </div>

        {/* RIGHT: Agent Log */}
        <div className="panel-flex-col">
          <DecisionLog 
            entries={decisionLog} 
            currentTick={tick} 
            defaultFilter="ats_agent"
            hideFilters={true}
          />
        </div>
      </div>
    </div>
  );
}
