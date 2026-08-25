import { RadarView } from '../components/RadarView';
import { DecisionLog } from '../components/DecisionLog';
import { RadioTower } from 'lucide-react';

export function RadarPage({ state, onFlightClick }) {
  const flights = state.flights ?? {};
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;

  return (
    <div className="agent-page fade-in">
      <div className="page-header">
        <div className="page-icon radar-page-icon"><RadioTower /></div>
        <h1 className="page-title">Air Traffic Control Radar</h1>
      </div>

      <div className="page-content-wrapper">
        {/* Radar Scope */}
        <div className="panel panel-no-padding">
           <RadarView flights={flights} onFlightClick={onFlightClick} />
        </div>
        <div className="panel decision-log-strip">
          <DecisionLog 
            entries={decisionLog} 
            currentTick={tick} 
            hideFilters={true}
          />
        </div>
      </div>
    </div>
  );
}
