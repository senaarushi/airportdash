import { useState } from 'react';
import { GateBoard } from '../components/GateBoard';
import { FlightTimeline } from '../components/FlightTimeline';
import { DecisionLog } from '../components/DecisionLog';
import { CombinedIssuesPanel } from '../components/CombinedIssuesPanel';
import { RadarView } from '../components/RadarView';
import { CrewPanel } from '../components/CrewPanel';

export function CommandCenter({ state, onFlightClick }) {
  const [expandedWidget, setExpandedWidget] = useState(null);

  const flights = state.flights ?? {};
  const gates = state.gates ?? {};
  const crew = state.crew ?? {};
  const disruptions = state.open_disruptions ?? [];
  const conflicts = state.open_conflicts ?? [];
  const decisionLog = state.decision_log ?? [];
  const tick = state.current_tick ?? 0;

  const renderWidget = (id) => {
    const isExpanded = expandedWidget === id;
    const props = {
      isExpanded,
      onExpand: () => setExpandedWidget(id),
      onClose: () => setExpandedWidget(null)
    };

    switch (id) {
      case 'gates':
        return <GateBoard gates={gates} flights={flights} onFlightClick={onFlightClick} {...props} />;
      case 'timeline':
        return <FlightTimeline flights={flights} onFlightClick={onFlightClick} {...props} />;
      case 'log':
        return <DecisionLog entries={decisionLog} currentTick={tick} {...props} />;
      case 'issues':
        return <CombinedIssuesPanel disruptions={disruptions} conflicts={conflicts} {...props} />;
      case 'radar':
        return (
          <div className="panel panel-full-height">
            <RadarView flights={flights} onFlightClick={onFlightClick} isWidget={!props.isExpanded} />
            {props.onExpand && (
              <button 
                className="btn btn-sm" 
                onClick={props.isExpanded ? props.onClose : props.onExpand}
              >
                {props.isExpanded ? 'Minimize' : 'Expand'}
              </button>
            )}
          </div>
        );
      case 'crew':
        return <CrewPanel crew={crew} {...props} />;
      default:
        return null;
    }
  };

  return (
    <div className="command-center fade-in cc-container">
      <div className="widget-grid">
        <div className="cc-widget-wrapper">{renderWidget('gates')}</div>
        <div className="cc-widget-wrapper">{renderWidget('timeline')}</div>
        <div className="cc-widget-wrapper">{renderWidget('issues')}</div>
        <div className="cc-widget-wrapper">{renderWidget('crew')}</div>
        <div className="cc-widget-wrapper">{renderWidget('radar')}</div>
        <div className="cc-widget-wrapper">{renderWidget('log')}</div>
      </div>
      
      {expandedWidget && (
        <div className="widget-modal-overlay" onClick={() => setExpandedWidget(null)}>
          <div className="widget-modal-content" onClick={e => e.stopPropagation()}>
            {renderWidget(expandedWidget)}
          </div>
        </div>
      )}
    </div>
  );
}
