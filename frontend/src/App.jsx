import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useLiveState } from './hooks/useLiveState';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { FlightDetailModal } from './components/FlightDetailModal';

// Pages
import { CommandCenter } from './pages/CommandCenter';
import { GateAgentPage } from './pages/GateAgentPage';
import { CrewAgentPage } from './pages/CrewAgentPage';
import { ATSAgentPage } from './pages/ATSAgentPage';
import { DisruptionAgentPage } from './pages/DisruptionAgentPage';
import { RadarPage } from './pages/RadarPage';

export default function App() {
  const {
    state,
    connected,
    isMock,
    isPlaying,
    snapshotIndex,
    totalSnapshots,
    playMock,
    pauseMock,
    resetMock,
    stepMock,
    simMode,
    simModeError,
    setLiveMode,
    stepLive,
    isStepping,
    stepTimedOut,
    thinkingPhrase,
  } = useLiveState();

  const [selectedFlight, setSelectedFlight] = useState(null);

  const disruptions = state.open_disruptions ?? [];
  const conflicts = state.open_conflicts ?? [];
  const activeDisruptions = disruptions.filter(d => !d.resolved).length;
  const openConflicts = conflicts.filter(c => !c.resolved).length;

  return (
    <Router>
      <div className="app">
        <Header
          tick={state.current_tick ?? 0}
          isMock={isMock}
          connected={connected}
          isPlaying={isPlaying}
          snapshotIndex={snapshotIndex}
          totalSnapshots={totalSnapshots}
          onPlay={playMock}
          onPause={pauseMock}
          onReset={resetMock}
          onStep={stepMock}
          simMode={simMode}
          simModeError={simModeError}
          onSetLiveMode={setLiveMode}
          onStepLive={stepLive}
          isStepping={isStepping}
          stepTimedOut={stepTimedOut}
        />

        <div 
          className="app-main-layout" 
          style={{ 
            filter: isStepping && !isMock ? 'blur(4px)' : 'none', 
            pointerEvents: isStepping && !isMock ? 'none' : 'auto', 
            transition: 'filter 0.2s ease-in-out' 
          }}
        >
          <Sidebar 
            activeDisruptions={activeDisruptions} 
            openConflicts={openConflicts} 
          />
          
          <main className="page-container">
            <Routes>
              <Route path="/" element={<CommandCenter state={state} onFlightClick={setSelectedFlight} />} />
              <Route path="/gate" element={<GateAgentPage state={state} onFlightClick={setSelectedFlight} />} />
              <Route path="/crew" element={<CrewAgentPage state={state} />} />
              <Route path="/ats" element={<ATSAgentPage state={state} onFlightClick={setSelectedFlight} />} />
              <Route path="/radar" element={<RadarPage state={state} onFlightClick={setSelectedFlight} />} />
              <Route path="/disruptions" element={<DisruptionAgentPage state={state} />} />
            </Routes>
          </main>
        </div>

        {isStepping && !isMock && (
          <div className="loading-overlay">
            <div className="loading-dots">
              <span></span><span></span><span></span>
            </div>
            <div className="loading-text">
              {stepTimedOut ? "Still waiting on a response — this is taking longer than usual." : thinkingPhrase}
            </div>
          </div>
        )}

        {selectedFlight && (
          <FlightDetailModal
            flight={selectedFlight}
            crew={state.crew ?? {}}
            gates={state.gates ?? {}}
            onClose={() => setSelectedFlight(null)}
          />
        )}
      </div>
    </Router>
  );
}
