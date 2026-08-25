export function Header({
  tick, isMock, connected, isPlaying, snapshotIndex, totalSnapshots,
  onPlay, onPause, onReset, onStep,
  // NEW (manual/auto tick control): only relevant when connected && !isMock
  simMode, simModeError, onSetLiveMode, onStepLive,
  isStepping, stepTimedOut,
}) {
  return (
    <header className="header">
      {/* LEFT — Branding */}
      <div className="header-left">
        <div className="logo-block">
          <div className="logo-emblem">
            {/* Stylised plane icon */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M21 16L3 10.5V13.5L10 16L9 21H12L14 16L21 16Z" fill="white" opacity="0.9"/>
              <path d="M21 8L3 10.5V7.5L10 8L9 3H12L14 8L21 8Z" fill="white" opacity="0.55"/>
            </svg>
          </div>
          <div>
            <div className="logo-text-main">AAI Ops Centre</div>
            <div className="logo-text-sub">Multi-Agent Airport Operations · Delhi</div>
          </div>
        </div>

        <div className="header-divider" />


      </div>

      {/* CENTER — Tick + Controls */}
      <div className="header-center">
        <div className="tick-block">
          <div className="tick-label">Sim Tick</div>
          <div className="tick-value">T+{tick}</div>
        </div>

        <div className="header-divider" />

        {isMock && (
          <div className="sim-controls">
            <button className="btn" onClick={onReset} title="Reset simulation">
              Reset
            </button>
            <button
              className={`btn ${isPlaying ? 'btn-danger' : 'btn-primary'}`}
              onClick={isPlaying ? onPause : onPlay}
            >
              {isPlaying ? 'Pause' : 'Play Demo'}
            </button>
            <button className="btn" onClick={onStep} title="Step one tick forward">
              Step
            </button>

            <div className="sim-progress">
              {Array.from({ length: totalSnapshots }, (_, i) => (
                <div
                  key={i}
                  className={`sim-pip ${i < snapshotIndex ? 'active' : ''} ${i === snapshotIndex ? 'current' : ''}`}
                />
              ))}
              <span className="sim-counter">{snapshotIndex + 1}/{totalSnapshots}</span>
            </div>
          </div>
        )}

        {/* NEW (manual/auto tick control): live-backend equivalent of the
            mock controls above. Shown only when actually connected to the
            real simulator, not the mock fallback -- distinct control
            surface since it drives the real backend's SimulationController
            rather than replaying a canned MOCK_SNAPSHOTS array. */}
        {connected && !isMock && (
          <div className="sim-controls">
            <div className="mode-toggle" role="group" aria-label="Simulation tick mode">
              <button
                className={`btn ${simMode === 'auto' ? 'btn-primary' : ''}`}
                onClick={() => onSetLiveMode('auto')}
                disabled={simMode === null}
                title="Tick automatically on a fixed interval"
              >
                Auto
              </button>
              <button
                className={`btn ${simMode === 'manual' ? 'btn-primary' : ''}`}
                onClick={() => onSetLiveMode('manual')}
                disabled={simMode === null}
                title="Tick only when you press Step"
              >
                Manual
              </button>
            </div>

            {simMode === 'manual' && (
              <button 
                className="btn" 
                onClick={onStepLive} 
                title="Advance the live simulation by one tick"
                disabled={isStepping}
              >
                {isStepping ? 'Stepping…' : 'Step'}
              </button>
            )}

            {simModeError && (
              <span
                className="sim-error-text"
                title={simModeError}
              >
                Error: {simModeError}
              </span>
            )}
          </div>
        )}
      </div>

      {/* RIGHT — Status */}
      <div className="header-right">
        <div className={`connection-pill ${connected ? 'connected' : 'mock'}`}>
          <div className="conn-dot" />
          {connected ? 'Live Backend' : 'Simulation Mode'}
        </div>
      </div>
    </header>
  );
}
