import { useState, useEffect, useRef } from 'react';
import { getAgentConfig, AGENT_CONFIG } from '../utils/config';

const AGENTS = ['all', ...Object.keys(AGENT_CONFIG)];

export function DecisionLog({ entries, currentTick, defaultFilter = 'all', hideFilters = false, isExpanded, onExpand, onClose }) {
  const [activeFilter, setActiveFilter] = useState(defaultFilter);
  const [prevLen, setPrevLen] = useState(entries.length);
  const bottomRef = useRef(null);

  const filtered = activeFilter === 'all'
    ? entries
    : entries.filter(e => e.agent_id === activeFilter);

  useEffect(() => {
    if (entries.length !== prevLen) {
      setPrevLen(entries.length);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 150);
    }
  }, [entries.length, prevLen]);

  return (
    <div className="panel panel-full-height">
      <div className="panel-header">
        <div className="flex-center-gap">
          <h2>Decision Log</h2>
          {onExpand && (
            <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
              {isExpanded ? 'Minimize' : 'Expand'}
            </button>
          )}
        </div>
        <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Live Reasoning Trace
        </span>
      </div>

      {/* Filter bar */}
      {!hideFilters && (
        <div className="tab-bar tab-bar-borderless">
          {AGENTS.map(agent => {
            const cfg = agent === 'all' ? null : getAgentConfig(agent);
            const isActive = activeFilter === agent;
            return (
              <button
                key={agent}
                className={`tab-btn tab-btn-thick ${isActive ? 'active' : ''}`}
                onClick={() => setActiveFilter(agent)}
                style={isActive && cfg
                  ? { color: cfg.color, borderBottomColor: cfg.color }
                  : isActive
                    ? { color: 'var(--accent-light)', borderBottomColor: 'var(--accent-light)' }
                    : {}
                }
              >
                {cfg ? <><span style={{ display: 'flex', alignItems: 'center' }}>{cfg.icon}</span> {cfg.label}</> : '◆ ALL'}
              </button>
            );
          })}
        </div>
      )}

      {/* Entries */}
      <div className="scroll-container">
        <div className="log-list">
          {filtered.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon"></div>
              <div className="empty-state-text">No decisions logged — press Play to run simulation</div>
            </div>
          )}

          {filtered.map((entry, i) => {
            const cfg = getAgentConfig(entry.agent_id);
            const isNew = entry.tick === currentTick && currentTick > 0;
            return (
              <div
                key={`${entry.tick}-${entry.agent_id}-${i}`}
                className={`log-entry ${isNew ? 'new-entry' : ''}`}
              >
                <div className="log-accent-bar" style={{ background: 'var(--border)' }} />
                <div className="log-body">
                  <div className="log-meta">
                    <span
                      className="agent-tag"
                      style={{ background: cfg.soft, color: cfg.color, borderColor: `${cfg.color}40` }}
                    >
                      {cfg.icon} {cfg.label}
                    </span>
                    <span className="action-tag">{entry.action}</span>
                    <span className="tick-tag">T+{entry.tick}</span>
                  </div>
                  <div className="log-detail">{entry.detail}</div>
                  {entry.affected_flights?.length > 0 && (
                    <div className="log-flights">
                      {entry.affected_flights.map(fid => (
                        <span key={fid} className="flight-tag">{fid}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
