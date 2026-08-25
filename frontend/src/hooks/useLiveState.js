import { useState, useEffect, useRef, useCallback } from 'react';
import { MOCK_SNAPSHOTS } from '../api/mockData';
import { AGENT_THINKING_PHRASES } from '../utils/agentFlavorText';
// NEW (manual/auto tick control): REST client for the real backend's
// simulation control endpoints. Distinct from the websocket connection
// above -- state still arrives over the socket, this is only for
// sending mode/step commands.
import { getSimulationMode, setSimulationMode, stepSimulation } from '../api/client';

// WebSocket URL.
// EDITED (wiring fix): was 'ws://localhost:8000/ws/state' — the backend's
// actual route is `@router.websocket("/ws")` in api/websocket.py, mounted
// with no prefix in main.py (`app.include_router(websocket_router)`), so
// the real path is just /ws, not /ws/state. The old URL would fail the
// websocket handshake every time and silently fall back to mock data
// forever, which is exactly what was happening.
// Overridable via VITE_WS_URL for deployments where the backend isn't on
// localhost:8000.
const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';

export function useLiveState() {
  const [state, setState] = useState(MOCK_SNAPSHOTS[0]);
  const [connected, setConnected] = useState(false);
  const [isMock, setIsMock] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  // NEW (manual/auto tick control): mode of the REAL backend's simulator,
  // as opposed to isPlaying/snapshotIndex above which only ever describe
  // the canned MOCK_SNAPSHOTS playback. null until we've successfully
  // fetched it at least once (i.e. before a live connection exists, or
  // while the initial GET /simulation/mode is in flight).
  const [simMode, setSimModeState] = useState(null);
  const [simModeError, setSimModeError] = useState(null);
  const [isStepping, setIsStepping] = useState(false);
  const [stepTimedOut, setStepTimedOut] = useState(false);
  const [thinkingPhrase, setThinkingPhrase] = useState('');
  const pendingStepTickRef = useRef(null);
  const stepStartedAtRef = useRef(null);
  const stepTimeoutRef = useRef(null);
  const thinkingIntervalRef = useRef(null);
  const wsRef = useRef(null);
  const playIntervalRef = useRef(null);

  // Try real WebSocket first; fall back to mock if it fails
  useEffect(() => {
    let ws;
    let failed = false;

    try {
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setIsMock(false);
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          // EDITED (wiring fix): the backend never sends a bare
          // AirportStatus object — every message is wrapped in a
          // WebSocketMessage envelope: { type, trigger_event, payload,
          // detail }, where `type` is "connected", "state_update", or
          // "error" (see api/schemas.py / api/websocket.py). The old code
          // did `setState(data)`, which set state to the *envelope*
          // itself, so state.flights, state.gates, etc. were all
          // undefined and every component silently rendered as empty
          // (App.jsx's `state.flights ?? {}` fallbacks masked this rather
          // than throwing, which is why it wasn't obviously broken).
          if (data.type === 'error') {
            console.warn('Server reported an error:', data.detail);
            return;
          }
          
          if (data.type === 'state_update' && data.payload) {
            const payloadTick = data.payload.current_tick ?? 0;
            if (pendingStepTickRef.current !== null && payloadTick > pendingStepTickRef.current) {
              const clearStep = () => {
                setIsStepping(false);
                pendingStepTickRef.current = null;
                clearTimeout(stepTimeoutRef.current);
                clearInterval(thinkingIntervalRef.current);
              };
              const elapsed = Date.now() - (stepStartedAtRef.current || 0);
              if (elapsed < 450) {
                setTimeout(clearStep, 450 - elapsed);
              } else {
                clearStep();
              }
            }
          }

          if (data.payload) {
            setState(data.payload);
          }
        } catch (err) {
          console.warn('Failed to parse WS message:', err);
        }
      };

      ws.onerror = () => {
        if (!failed) {
          failed = true;
          setConnected(false);
          setIsMock(true);
          // Fall back to mock
          setState(MOCK_SNAPSHOTS[0]);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        setIsMock(true);
      };
    } catch {
      setIsMock(true);
      setState(MOCK_SNAPSHOTS[0]);
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    };
  }, []);

  // NEW (manual/auto tick control): once we're actually talking to the
  // real backend (not the mock fallback), fetch its current tick mode so
  // the UI toggle starts in sync rather than defaulting to a guess. Runs
  // once per connection, not on every state update.
  useEffect(() => {
    if (!connected) return;
    let cancelled = false;
    getSimulationMode()
      .then((res) => {
        if (!cancelled) setSimModeState(res.mode);
      })
      .catch((err) => {
        if (!cancelled) setSimModeError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [connected]);

  const setLiveMode = useCallback(async (mode) => {
    try {
      const res = await setSimulationMode(mode);
      setSimModeState(res.mode);
      setSimModeError(null);
    } catch (err) {
      setSimModeError(err.message);
    }
  }, []);

  const stepLive = useCallback(async () => {
    try {
      const currentTick = state.current_tick ?? 0;
      pendingStepTickRef.current = currentTick;
      stepStartedAtRef.current = Date.now();
      
      setIsStepping(true);
      setStepTimedOut(false);
      
      const pickRandomPhrase = () => AGENT_THINKING_PHRASES[Math.floor(Math.random() * AGENT_THINKING_PHRASES.length)];
      setThinkingPhrase(pickRandomPhrase());
      
      thinkingIntervalRef.current = setInterval(() => {
        setThinkingPhrase(prev => {
          let next = pickRandomPhrase();
          while (next === prev) next = pickRandomPhrase();
          return next;
        });
      }, 1800);
      
      stepTimeoutRef.current = setTimeout(() => {
        setStepTimedOut(true);
        clearInterval(thinkingIntervalRef.current);
      }, 9000);

      await stepSimulation();
      setSimModeError(null);
      // Deliberately not setting state here -- the actual tick runs
      // asynchronously on the backend and the resulting AirportStatus
      // arrives via the websocket's tick_complete-triggered push, same
      // path as every other update. This just fires the request.
    } catch (err) {
      setSimModeError(err.message);
      setIsStepping(false);
      setStepTimedOut(false);
      clearInterval(thinkingIntervalRef.current);
      clearTimeout(stepTimeoutRef.current);
    }
  }, [state.current_tick]);

  // Mock simulation playback
  const playMock = useCallback(() => {
    if (!isMock) return;
    setIsPlaying(true);
    let idx = snapshotIndex;
    playIntervalRef.current = setInterval(() => {
      idx = (idx + 1) % MOCK_SNAPSHOTS.length;
      setSnapshotIndex(idx);
      setState(MOCK_SNAPSHOTS[idx]);
      if (idx === MOCK_SNAPSHOTS.length - 1) {
        clearInterval(playIntervalRef.current);
        setIsPlaying(false);
      }
    }, 2500);
  }, [isMock, snapshotIndex]);

  const pauseMock = useCallback(() => {
    clearInterval(playIntervalRef.current);
    setIsPlaying(false);
  }, []);

  const resetMock = useCallback(() => {
    clearInterval(playIntervalRef.current);
    setIsPlaying(false);
    setSnapshotIndex(0);
    setState(MOCK_SNAPSHOTS[0]);
  }, []);

  const stepMock = useCallback(() => {
    const next = (snapshotIndex + 1) % MOCK_SNAPSHOTS.length;
    setSnapshotIndex(next);
    setState(MOCK_SNAPSHOTS[next]);
  }, [snapshotIndex]);

  useEffect(() => {
    return () => clearInterval(playIntervalRef.current);
  }, []);

  return {
    state,
    connected,
    isMock,
    isPlaying,
    snapshotIndex,
    totalSnapshots: MOCK_SNAPSHOTS.length,
    playMock,
    pauseMock,
    resetMock,
    stepMock,
    // NEW (manual/auto tick control): only meaningful when connected &&
    // !isMock -- controls the REAL backend's simulator, distinct from
    // the mock playback controls above.
    simMode,
    simModeError,
    setLiveMode,
    stepLive,
    isStepping,
    stepTimedOut,
    thinkingPhrase,
  };
}
