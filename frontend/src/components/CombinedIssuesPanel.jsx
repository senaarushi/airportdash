import { useState } from 'react';
import { DisruptionPanel } from './DisruptionPanel';
import { ConflictPanel } from './ConflictPanel';

export function CombinedIssuesPanel({ disruptions, conflicts, isExpanded, onExpand, onClose }) {
  const [activeTab, setActiveTab] = useState('disruptions');
  
  const activeDisruptions = disruptions.filter(d => !d.resolved).length;
  const activeConflicts = conflicts.filter(c => !c.resolved).length;

  return (
    <div className="panel panel-flex-col">
      <div className="panel-header panel-header-tabs">
        <div className="flex-between-full">
          <div className="tab-bar tab-bar-borderless">
            <button 
              className={`tab-btn tab-btn-thick ${activeTab === 'disruptions' ? 'active' : ''}`}
              onClick={() => setActiveTab('disruptions')}
            >
              Disruptions 
              {activeDisruptions > 0 && <span className="tab-badge">{activeDisruptions}</span>}
            </button>
            <button 
              className={`tab-btn tab-btn-thick ${activeTab === 'conflicts' ? 'active' : ''}`}
              onClick={() => setActiveTab('conflicts')}
            >
              Conflicts
              {activeConflicts > 0 && <span className="tab-badge">{activeConflicts}</span>}
            </button>
          </div>
          {onExpand && (
            <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
              {isExpanded ? 'Minimize' : 'Expand'}
            </button>
          )}
        </div>
      </div>
      
      <div className="panel-flex-col-inner">
        <div className="tab-content-wrapper" style={{ display: activeTab === 'disruptions' ? 'flex' : 'none' }}>
          <DisruptionPanel disruptions={disruptions} hideWrapper={true} />
        </div>
        <div className="tab-content-wrapper" style={{ display: activeTab === 'conflicts' ? 'flex' : 'none' }}>
          <ConflictPanel conflicts={conflicts} hideWrapper={true} />
        </div>
      </div>
    </div>
  );
}
