import { formatTime } from '../utils/config';

const STATUS_LABEL = {
  SCHEDULED: 'Scheduled', IN_AIR: 'In Air', LANDED: 'Landed',
  AT_GATE: 'At Gate', READY_FOR_PUSHBACK: 'Pushback',
  DEPARTED: 'Departed', CANCELLED: 'Cancelled',
};

export function FlightDetailModal({ flight, crew, gates, onClose }) {
  if (!flight) return null;

  const gate        = flight.assigned_gate ? gates[flight.assigned_gate] : null;
  const crewMembers = (flight.assigned_crew ?? []).map(id => crew[id]).filter(Boolean);

  const roleIcon    = { BAGGAGE: 'Baggage', PUSHBACK: 'Pushback', CLEANING: 'Cleaning' };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        {/* Modal header */}
        <div className="modal-header">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>

              <div>
                <div style={{ fontSize: '1rem', fontWeight: 800, letterSpacing: '-0.01em', fontFamily: 'var(--font-mono)' }}>
                  {flight.flight_id}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{flight.airline}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span className={`status-chip ${flight.status}`}>
                {STATUS_LABEL[flight.status] ?? flight.status}
              </span>
              {flight.is_delayed && <span className="delay-chip">DELAYED</span>}
              <span className="badge" style={{
                background: 'var(--bg-card)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
              }}>
                {flight.aircraft_type.replace('_', ' ')}
              </span>
              <span className="badge" style={{
                background: 'var(--bg-card)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                fontFamily: 'var(--font-mono)',
              }}>
                TAT: {flight.turnaround_time}min
              </span>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {/* Schedule */}
          <div>
            <div className="section-label">Schedule</div>
            <div className="detail-grid">
              {[
                { label: 'Sched. Arrival',    val: formatTime(flight.scheduled_arrival),  highlight: false },
                { label: 'Actual Arrival',     val: formatTime(flight.actual_arrival),     highlight: flight.is_delayed },
                { label: 'Sched. Departure',   val: formatTime(flight.scheduled_departure), highlight: false },
                { label: 'Actual Departure',   val: formatTime(flight.actual_departure),   highlight: false },
              ].map(item => (
                <div key={item.label} className="detail-item">
                  <div className="detail-item-label">{item.label}</div>
                  <div className="detail-item-value" style={item.highlight ? { color: 'var(--gate-unavail)' } : {}}>
                    {item.val}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Gate */}
          <div>
            <div className="section-label">Gate</div>
            {gate ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <div className="detail-item-label">Assigned Gate</div>
                  <div className="detail-item-value" style={{ fontSize: '1.1rem', color: '#a5b4fc' }}>
                    {gate.gate_id}
                  </div>
                </div>
                <div className="detail-item">
                  <div className="detail-item-label">Gate Capability</div>
                  <div className="detail-item-value" style={{ fontSize: '0.75rem' }}>
                    {gate.supports_wide_body ? 'Wide Body Capable' : 'Narrow Body Only'}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No gate assigned yet
              </div>
            )}
          </div>

          {/* Crew */}
          <div>
            <div className="section-label">Ground Crew ({crewMembers.length})</div>
            {crewMembers.length === 0 ? (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No crew assigned yet
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {crewMembers.map(c => (
                  <div key={c.crew_id} className="crew-member-row">
                    <span>{roleIcon[c.role] ?? 'Crew'}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--text-muted)', minWidth: 42 }}>
                      {c.crew_id}
                    </span>
                    <span style={{ flex: 1, fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{c.role}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--text-dim)' }}>
                      {c.shift_minutes_remaining}min rem.
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
