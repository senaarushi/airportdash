export function CrewPanel({ crew, isExpanded, onExpand, onClose }) {
  const crewList = Object.values(crew);

  const roles = {
    BAGGAGE:  { label: 'Baggage',  icon: '', color: 'var(--agent-crew)',  fillStyle: 'linear-gradient(90deg, #0891b2, #06b6d4)' },
    PUSHBACK: { label: 'Pushback', icon: '', color: 'var(--agent-gate)',  fillStyle: 'linear-gradient(90deg, #4f46e5, #6366f1)' },
    CLEANING: { label: 'Cleaning', icon: '', color: 'var(--agent-ats)',   fillStyle: 'linear-gradient(90deg, #d97706, #f59e0b)' },
  };

  const byRole = { BAGGAGE: [], PUSHBACK: [], CLEANING: [] };
  crewList.forEach(c => { if (byRole[c.role]) byRole[c.role].push(c); });

  const totalFree     = crewList.filter(c => c.available).length;
  const totalTotal    = crewList.length;

  return (
    <div className="panel panel-full-height">
      <div className="panel-header">
        <div className="flex-center-gap">
          <h2>Ground Crew</h2>
          {onExpand && (
            <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
              {isExpanded ? 'Minimize' : 'Expand'}
            </button>
          )}
        </div>
        <div className="flex-gap-sm">
          <span className="badge" style={{ background: 'rgba(16,185,129,0.1)', color: 'var(--gate-open)', border: '1px solid rgba(16,185,129,0.25)' }}>
            {totalFree} Free
          </span>
          <span className="badge" style={{ background: 'rgba(148,163,184,0.1)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
            {totalTotal} Total
          </span>
        </div>
      </div>

      <div className="panel-body">
        {/* Summary cards */}
        <div className="crew-summary-grid">
          {Object.entries(roles).map(([role, cfg]) => {
            const members = byRole[role] ?? [];
            const avail   = members.filter(c => c.available).length;
            return (
              <div key={role} className="crew-summary-card">
                <div style={{ fontSize: '1.1rem', marginBottom: 3 }}>{cfg.icon}</div>
                <div className="crew-count" style={{ color: cfg.color }}>{avail}/{members.length}</div>
                <div className="crew-count-label">{cfg.label}</div>
              </div>
            );
          })}
        </div>

        <div className="divider" />

        {/* Role availability bars */}
        {Object.entries(roles).map(([role, cfg]) => {
          const members = byRole[role] ?? [];
          const avail   = members.filter(c => c.available).length;
          const pct     = members.length > 0 ? (avail / members.length) * 100 : 0;
          return (
            <div key={role} className="role-bar-row">
              <div className="role-bar-label">
                <span>{cfg.icon} {cfg.label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: cfg.color }}>
                  {avail}/{members.length} available
                </span>
              </div>
              <div className="role-bar-track">
                <div className="role-bar-fill" style={{ width: `${pct}%`, background: cfg.fillStyle }} />
              </div>
            </div>
          );
        })}

        <div className="divider" />

        {/* Assigned crew list */}
        <div className="section-label">On Duty</div>
        {crewList.filter(c => !c.available).length === 0 && (
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            All crew are currently available
          </div>
        )}
        {crewList.filter(c => !c.available).map(c => {
          const cfg = roles[c.role] ?? {};
          return (
            <div key={c.crew_id} className="crew-member-row">
              <span style={{ fontSize: '0.9rem' }}>{cfg.icon}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--text-muted)', minWidth: 38 }}>{c.crew_id}</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', flex: 1 }}>{cfg.label}</span>
              <span className="flight-tag">{c.assigned_flight}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--text-dim)' }}>{c.shift_minutes_remaining}m</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
