import { useMemo, useState } from 'react';
import { formatShortTime } from '../utils/config';
import './RadarView.css';

export function RadarView({ flights, onFlightClick, isWidget }) {
  const [hoveredFlightId, setHoveredFlightId] = useState(null);
  const [expandedClusterId, setExpandedClusterId] = useState(null);

  const flightList = Object.values(flights || {});

  // 1. Compute Base Blip Data using Percentages
  const baseBlips = useMemo(() => {
    // Determine min/max scheduled arrival time for dynamic window
    let minTime = Infinity;
    let maxTime = -Infinity;
    
    flightList.forEach(f => {
      if (f.scheduled_arrival) {
        const d = new Date(f.scheduled_arrival);
        const totalHours = d.getUTCHours() + d.getUTCMinutes() / 60;
        if (totalHours < minTime) minTime = totalHours;
        if (totalHours > maxTime) maxTime = totalHours;
      }
    });
    
    // Fallback if no flights or all same time
    if (minTime === Infinity) { minTime = 0; maxTime = 24; }
    else if (maxTime === minTime) { maxTime = minTime + 1; }

    return flightList.map(f => {
      let angle = 0;
      if (f.scheduled_arrival) {
        const d = new Date(f.scheduled_arrival);
        const totalHours = d.getUTCHours() + d.getUTCMinutes() / 60;
        angle = ((totalHours - minTime) / (maxTime - minTime)) * 360;
      }
      
      let radius = 320; 
      let isFadingOut = false;
      
      switch (f.status) {
        case 'IN_AIR':
        case 'SCHEDULED': radius = 320; break;
        case 'LANDED': radius = 200; break;
        case 'AT_GATE':
        case 'READY_FOR_PUSHBACK': radius = 80; break;
        case 'DEPARTED':
        case 'CANCELLED':
          radius = 320; 
          isFadingOut = true;
          break;
      }

      const rad = (angle * Math.PI) / 180;
      // Convert pixel radius (out of 400) to percentage of half-width (0 to 50%)
      const xPct = (radius / 400) * 50 * Math.sin(rad);
      const yPct = -(radius / 400) * 50 * Math.cos(rad);

      const delayStr = `-${((angle + 8) / 360) * 4}s`;

      return {
        ...f,
        xPct,
        yPct,
        angle,
        delayStr,
        isFadingOut
      };
    });
  }, [flightList]);

  // 2. Cluster Blips
  const { renderedBlips, clusters } = useMemo(() => {
    const CLUSTER_THRESHOLD = 3.5; // roughly 3.5% of container
    const clustersMap = new Map();
    const unclustered = [];
    const assigned = new Set();
    
    for (let i = 0; i < baseBlips.length; i++) {
      if (assigned.has(i)) continue;
      
      const b1 = baseBlips[i];
      const cluster = [b1];
      assigned.add(i);

      for (let j = i + 1; j < baseBlips.length; j++) {
        if (assigned.has(j)) continue;
        const b2 = baseBlips[j];
        const dist = Math.hypot(b1.xPct - b2.xPct, b1.yPct - b2.yPct);
        if (dist < CLUSTER_THRESHOLD) {
          cluster.push(b2);
          assigned.add(j);
        }
      }

      if (cluster.length > 1) {
        const cx = cluster.reduce((sum, b) => sum + b.xPct, 0) / cluster.length;
        const cy = cluster.reduce((sum, b) => sum + b.yPct, 0) / cluster.length;
        const id = `cluster-${cx.toFixed(1)}-${cy.toFixed(1)}`;
        clustersMap.set(id, { id, cx, cy, flights: cluster });
      } else {
        unclustered.push(b1);
      }
    }

    const clustersList = Array.from(clustersMap.values());
    const finalBlips = [...unclustered];
    
    const activeClusters = [];
    for (const c of clustersList) {
      if (c.id === expandedClusterId) {
        const num = c.flights.length;
        c.flights.forEach((f, idx) => {
          const spreadAngle = (idx / num) * Math.PI * 2;
          const spreadRadius = 2.5; // 2.5% fan-out
          finalBlips.push({
            ...f,
            xPct: f.xPct + Math.cos(spreadAngle) * spreadRadius,
            yPct: f.yPct + Math.sin(spreadAngle) * spreadRadius,
            isExpanded: true
          });
        });
      } else {
        activeClusters.push(c);
      }
    }

    return { renderedBlips: finalBlips, clusters: activeClusters };
  }, [baseBlips, expandedClusterId]);

  const hoveredFlight = useMemo(() => {
    return flightList.find(f => f.flight_id === hoveredFlightId);
  }, [hoveredFlightId, flightList]);

  return (
    <div 
      className={`radar-container fade-in ${isWidget ? 'is-widget' : ''}`} 
      onClick={() => setExpandedClusterId(null)}
    >
      <div className="radar-scope-wrapper">
        <svg className="radar-svg" viewBox="-400 -400 800 800" preserveAspectRatio="xMidYMid meet">
          <circle r="380" className="radar-ring edge" />
          <circle r="320" className="radar-ring" />
          <circle r="200" className="radar-ring" />
          <circle r="80" className="radar-ring inner" />
          
          {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map(deg => (
            <line 
              key={deg}
              x1="0" y1="-380" x2="0" y2="380" 
              className="radar-spoke"
              transform={`rotate(${deg})`}
            />
          ))}

          {[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map(deg => {
            const rad = ((deg - 90) * Math.PI) / 180;
            const r = 390; 
            const x = r * Math.cos(rad);
            const y = r * Math.sin(rad);
            const label = deg.toString().padStart(3, '0');
            return (
              <text key={`lbl-${deg}`} x={x} y={y} className="radar-label">{label}</text>
            );
          })}

          <text x="0" y="-310" className="radar-label-ring">IN AIR / SCHEDULED</text>
          <text x="0" y="-190" className="radar-label-ring">LANDED</text>
          <text x="0" y="-70" className="radar-label-ring">AT GATE</text>
          
          <text x="0" y="0" className="radar-label-ring radar-origin-label">ORIGIN</text>
        </svg>

        {/* Rotating Sweep Line */}
        <div className="radar-sweep" />

        {/* Flight Blips Layer */}
        <div className="radar-blips-layer">
          {renderedBlips.map(b => (
            <div 
              key={b.flight_id}
              className={`radar-blip ${b.isFadingOut ? 'fade-out-anim' : ''} ${hoveredFlightId === b.flight_id ? 'hovered' : ''} ${b.isExpanded ? 'expanded-item' : ''}`}
              style={{
                left: `calc(50% + ${b.xPct}%)`,
                top: `calc(50% + ${b.yPct}%)`,
                animationDelay: b.delayStr
              }}
              onMouseEnter={() => setHoveredFlightId(b.flight_id)}
              onMouseLeave={() => setHoveredFlightId(null)}
              onClick={(e) => { e.stopPropagation(); onFlightClick?.(b); }}
            >
              <div className="radar-blip-core" />
              {!isWidget && <div className="radar-blip-label">{b.flight_id}</div>}
            </div>
          ))}

          {clusters.map(c => (
            <div 
              key={c.id}
              className="radar-cluster"
              style={{
                left: `calc(50% + ${c.cx}%)`,
                top: `calc(50% + ${c.cy}%)`,
              }}
              onClick={(e) => { e.stopPropagation(); setExpandedClusterId(c.id); }}
              title={`${c.flights.length} flights in sector`}
            >
              {c.flights.length}
            </div>
          ))}
        </div>
      </div>

      {/* Overlays (Hide in widget view) */}
      {!isWidget && (
        <>
          <div className="radar-overlay-panel radar-legend">
            <h3>ATC RADAR SCOPE</h3>
            <div className="radar-legend-subtitle">Angle = Scheduled Arrival Time<br/>(00:00 = Top, 12:00 = Bottom)</div>
            <div className="legend-row">
              <div className="legend-swatch green" /> Active Target
            </div>
            <div className="legend-row">
              <div className="legend-swatch white" /> Selected / Hovered
            </div>
          </div>

          <div className="radar-overlay-panel radar-readout">
            <h3>TARGET IDENTIFICATION</h3>
            {hoveredFlight ? (
              <>
                <div className="readout-row">
                  <span className="readout-label">CALLSIGN</span>
                  <span className="readout-value highlight">{hoveredFlight.flight_id}</span>
                </div>
                <div className="readout-row">
                  <span className="readout-label">STATUS</span>
                  <span className="readout-value">{hoveredFlight.status}</span>
                </div>
                <div className="readout-row">
                  <span className="readout-label">GATE</span>
                  <span className="readout-value">{hoveredFlight.assigned_gate || 'UNASSIGNED'}</span>
                </div>
                <div className="readout-row">
                  <span className="readout-label">SCHED ARR</span>
                  <span className="readout-value">{formatShortTime(hoveredFlight.scheduled_arrival)}</span>
                </div>
              </>
            ) : (
              <div className="radar-empty-state">
                NO TARGET SELECTED
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
