// NEW FILE — added for manual/auto tick control.
// Small fetch wrapper for the backend's REST control endpoints. This is
// the frontend's first REST call of any kind -- everything else so far
// is websocket-only (see hooks/useLiveState.js). Kept separate from
// mockData.js/useLiveState.js on purpose: this only ever talks to the
// REAL backend, it has no mock equivalent (there's nothing to "control"
// about the canned mock snapshot playback via this path, that's handled
// by useLiveState's own playMock/pauseMock/stepMock functions instead).

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';

async function request(path, options) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON, fall back to statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

// { mode: 'auto' | 'manual', current_tick: number }
export function getSimulationMode() {
  return request('/simulation/mode');
}

export function setSimulationMode(mode) {
  return request('/simulation/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });
}

export function stepSimulation() {
  return request('/simulation/step', { method: 'POST' });
}
