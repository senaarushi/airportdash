import { DISRUPTION_ICONS, DISRUPTION_LABELS } from '../utils/config';

const SEV_TEXT = { 1: 'L1 · Minor', 2: 'L2 · Low', 3: 'L3 · Moderate', 4: 'L4 · Severe', 5: 'L5 · Critical' };

export function DisruptionPanel({ disruptions, isExpanded, onExpand, onClose, hideWrapper }) {
  const active   = disruptions.filter(d => !d.resolved);
  const resolved = disruptions.filter(d => d.resolved);

  const content = (
    <>
      {!hideWrapper && (
        <div className="panel-header">
          <div className="flex-center-gap">
            <h2>
              Disruptions
              {active.length > 0 && (
                <span className="badge" style={{
                  background: 'rgba(244,63,94,0.12)',
                  color: 'var(--agent-disruption)',
                  border: '1px solid rgba(244,63,94,0.3)',
                  marginLeft: 5,
                }}>
                  {active.length} Active
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
          {disruptions.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-icon"></div>
              <div className="empty-state-text">All Clear — No active disruptions</div>
            </div>
          )}

          {active.length > 0 && (
            <>
              <div className="section-label">Active</div>
              {active.map(d => <DisruptionCard key={d.event_id} d={d} />)}
            </>
          )}

          {resolved.length > 0 && (
            <>
              <div className="section-label" style={{ marginTop: 4 }}>Resolved</div>
              {resolved.map(d => <DisruptionCard key={d.event_id} d={d} />)}
            </>
          )}
        </div>
      </div>
    </>
  );

  if (hideWrapper) return <div className="panel-full-height">{content}</div>;
  return <div className="panel panel-flex-col panel-full-height">{content}</div>;
}

function DisruptionCard({ d }) {
  const icon  = DISRUPTION_ICONS[d.disruption_type] ?? '';
  const label = DISRUPTION_LABELS[d.disruption_type] ?? d.disruption_type;
  const sev   = d.severity;

  return (
    <div className={`disruption-card sev-${sev} ${d.resolved ? 'resolved' : ''}`}>
      <div className="disruption-header">
        <div className="disruption-type-info">
          <span className={`severity-pill sev-${sev}`}>{SEV_TEXT[sev] ?? `L${sev}`}</span>
          <span className="disruption-type-name">{icon} {label}</span>
        </div>
        {d.resolved && <span className="resolved-badge">✓ Resolved</span>}
      </div>

      <div className="disruption-desc">{d.disruption_description}</div>

      <div className="disruption-footer">
        <div className="disruption-affected">
          {d.affected_flights.length > 0 && (
            <>
              <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginRight: 3, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Flt:
              </span>
              {d.affected_flights.map(fid => (
                <span key={fid} className="flight-tag">{fid}</span>
              ))}
            </>
          )}
        </div>
        <div className="disruption-id">{d.event_id}</div>
      </div>
    </div>
  );
}
