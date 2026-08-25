import { useState } from 'react';

export function GateBoard({ gates, flights, onFlightClick, isExpanded, onExpand, onClose }) {
  const [hovered, setHovered] = useState(null);

  const gateList = Object.values(gates).sort((a, b) => {
    const n = g => parseInt(g.gate_id.replace(/\D/g, '')) || 0;
    return n(a) - n(b);
  });

  const cls = { OPEN: 'open', OCCUPIED: 'occupied', UNAVAILABLE: 'unavailable' };

  const openCt  = gateList.filter(g => g.gate_status === 'OPEN').length;
  const occCt   = gateList.filter(g => g.gate_status === 'OCCUPIED').length;
  const unavCt  = gateList.filter(g => g.gate_status === 'UNAVAILABLE').length;

  return (
    <div className="panel panel-full-height">
      <div className="panel-header">
        <div className="flex-center-gap">
          <h2>Gate Board</h2>
          {onExpand && (
            <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
              {isExpanded ? 'Minimize' : 'Expand'}
            </button>
          )}
        </div>
        <div className="flex-gap-sm">
          <span className="badge" style={{ background: 'rgba(16,185,129,0.12)', color: 'var(--gate-open)', border: '1px solid rgba(16,185,129,0.25)' }}>
            {openCt} Open
          </span>
          <span className="badge" style={{ background: 'rgba(245,158,11,0.12)', color: 'var(--gate-occupied)', border: '1px solid rgba(245,158,11,0.25)' }}>
            {occCt} Occ.
          </span>
          {unavCt > 0 && (
            <span className="badge" style={{ background: 'rgba(244,63,94,0.12)', color: 'var(--gate-unavail)', border: '1px solid rgba(244,63,94,0.25)' }}>
              {unavCt} N/A
            </span>
          )}
        </div>
      </div>

      <div className="panel-body">
        <div className="gate-grid">
          {gateList.map(gate => {
            const flight = gate.assigned_flight ? flights[gate.assigned_flight] : null;
            const statusCls = cls[gate.gate_status] ?? 'open';
            return (
              <div
                key={gate.gate_id}
                className={`gate-cell ${statusCls}`}
                title={`${gate.gate_id} · ${gate.gate_status}${flight ? ` · ${flight.airline} (${flight.flight_id})` : ''}`}
                onClick={() => flight && onFlightClick?.(flight)}
                onMouseEnter={() => setHovered(gate.gate_id)}
                onMouseLeave={() => setHovered(null)}
                style={hovered === gate.gate_id ? {
                  transform: 'translateY(-3px)',
                  boxShadow: '0 6px 16px rgba(0,0,0,0.5)',
                } : {}}
              >
                <div className="gate-id">{gate.gate_id}</div>
                <div className="gate-status-indicator" />
                <div className="gate-flight-id">
                  {gate.gate_status === 'UNAVAILABLE'
                    ? <span style={{ color: 'var(--gate-unavail)' }}>N/A</span>
                    : gate.assigned_flight || <span style={{ color: 'var(--text-dim)' }}>free</span>
                  }
                </div>

              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
