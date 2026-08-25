import { getAgentConfig } from '../utils/config';

export function ConflictPanel({ conflicts, isExpanded, onExpand, onClose, hideWrapper }) {
  const open     = conflicts.filter(c => !c.resolved);
  const resolved = conflicts.filter(c => c.resolved);

  const content = (
    <>
      {!hideWrapper && (
        <div className="panel-header">
          <div className="flex-center-gap">
            <h2>
              Conflicts
              {open.length > 0 && (
                <span className="badge" style={{
                  background: 'rgba(245,158,11,0.12)',
                  color: 'var(--gate-occupied)',
                  border: '1px solid rgba(245,158,11,0.3)',
                  marginLeft: 5,
                }}>
                  {open.length} Open
                </span>
              )}
            </h2>
            {onExpand && (
              <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
                {isExpanded ? 'Minimize' : 'Expand'}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="scroll-container">
        <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 7 }}>
          {conflicts.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon"></div>
              <div className="empty-state-text">No conflicts detected</div>
            </div>
          )}

          {open.length > 0 && (
            <>
              <div className="section-label">Open</div>
              {open.map(c => <ConflictCard key={c.conflict_id} conflict={c} />)}
            </>
          )}

          {resolved.length > 0 && (
            <>
              <div className="section-label" style={{ marginTop: 4 }}>Resolved</div>
              {resolved.map(c => <ConflictCard key={c.conflict_id} conflict={c} />)}
            </>
          )}
        </div>
      </div>
    </>
  );

  if (hideWrapper) return <div className="panel-full-height">{content}</div>;
  return <div className="panel panel-flex-col panel-full-height">{content}</div>;
}

function ConflictCard({ conflict }) {
  const cfg = getAgentConfig(conflict.agent_id);
  return (
    <div className={`conflict-card ${conflict.resolved ? 'resolved' : ''}`}>
      <div className="conflict-card-header">
        <span className="conflict-agent-label" style={{ color: cfg.color }}>
          {cfg.icon} {cfg.label}
        </span>
        <span className={`conflict-status-badge ${conflict.resolved ? 'resolved' : 'open'}`}>
          {conflict.resolved ? '✓ Resolved' : '● Open'}
        </span>
      </div>
      <div className="conflict-desc">{conflict.conflict_description}</div>
      {conflict.affected_flights.length > 0 && (
        <div className="log-flights" style={{ marginTop: 5 }}>
          {conflict.affected_flights.map(fid => (
            <span key={fid} className="flight-tag">{fid}</span>
          ))}
        </div>
      )}
      <div style={{ fontSize: '0.58rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)', marginTop: 5 }}>
        {conflict.conflict_id}
      </div>
    </div>
  );
}
