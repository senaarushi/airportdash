import { DisruptionPanel } from '../components/DisruptionPanel';
import { ConflictPanel } from '../components/ConflictPanel';
import { DecisionLog } from '../components/DecisionLog';
import { getAgentConfig } from '../utils/config';

export function DisruptionAgentPage({ state }) {
  const disruptions = state.open_disruptions ?? [];
  const conflicts = state.open_conflicts ?? [];
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;
  
  const cfg = getAgentConfig('disruption_agent');

  return (
    <div className="agent-page fade-in">
      <div className="page-header">
        <div className="page-icon" style={{ color: cfg.color, borderColor: cfg.color }}>{cfg.icon}</div>
        <h1 className="page-title">Disruption & Conflict Management</h1>
      </div>

      <div className="page-legend-row">
        <div className="legend-group">
          <div className="legend-group-title">Severity:</div>
          <div className="legend-item"><div className="legend-dot bg-sev-1" /> Minor</div>
          <div className="legend-item"><div className="legend-dot bg-sev-2" /> Low</div>
          <div className="legend-item"><div className="legend-dot bg-sev-3" /> Moderate</div>
          <div className="legend-item"><div className="legend-dot bg-sev-4" /> Severe</div>
          <div className="legend-item"><div className="legend-dot bg-sev-5" /> Critical</div>
        </div>
        <div style={{ borderLeft: '1px solid var(--border)' }} />
        <div className="legend-group">
          <div className="legend-item"><div className="legend-dot bg-agent-disruption" /> Open</div>
          <div className="legend-item"><div className="legend-dot bg-status-landed" /> Resolved</div>
        </div>
      </div>

      <div className="agent-page-grid">
        {/* LEFT COL */}
        <div className="panel-flex-col-gap">
          <div className="panel panel-flex-col">
            <div className="panel-header">
              <h2>ACTIVE DISRUPTIONS</h2>
            </div>
            <div className="panel-body">
               <DisruptionPanel disruptions={disruptions} />
            </div>
          </div>
          <div className="panel panel-flex-col">
            <div className="panel-header">
              <h2>AGENT CONFLICTS</h2>
            </div>
            <div className="panel-body">
               <ConflictPanel conflicts={conflicts} />
            </div>
          </div>
        </div>

        {/* RIGHT COL: Agent Log */}
        <div className="panel-flex-col">
          <DecisionLog 
            entries={decisionLog} 
            currentTick={tick} 
            defaultFilter="disruption_agent"
            hideFilters={true}
          />
        </div>
      </div>
    </div>
  );
}
