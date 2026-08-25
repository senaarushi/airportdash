import { useState } from 'react';
import { formatShortTime } from '../utils/config';

const STATUS_LABEL = {
  SCHEDULED: 'Sched', IN_AIR: 'In Air', LANDED: 'Landed',
  AT_GATE: 'At Gate', READY_FOR_PUSHBACK: 'Pushback',
  DEPARTED: 'Departed', CANCELLED: 'Cancelled',
};

const STATUS_ORDER = ['IN_AIR','LANDED','AT_GATE','READY_FOR_PUSHBACK','SCHEDULED','DEPARTED','CANCELLED'];

export function FlightTimeline({ flights, onFlightClick, isExpanded, onExpand, onClose }) {
  const [activeTab, setActiveTab] = useState('arrivals');

  const flightList = Object.values(flights).sort((a, b) => {
    if (activeTab === 'arrivals') {
      return new Date(a.scheduled_arrival) - new Date(b.scheduled_arrival);
    } else {
      return new Date(a.scheduled_departure) - new Date(b.scheduled_departure);
    }
  });

  const inboundCt   = Object.values(flights).filter(f => f.status === 'IN_AIR').length;
  const onGroundCt  = Object.values(flights).filter(f => ['AT_GATE','LANDED','READY_FOR_PUSHBACK'].includes(f.status)).length;

  return (
    <div className="panel panel-full-height panel-flex-col">
      <div className="panel-header panel-header-tabs">
        <div className="flex-between-full" style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="tab-bar tab-bar-borderless">
            <button 
              className={`tab-btn tab-btn-thick ${activeTab === 'arrivals' ? 'active' : ''}`}
              onClick={() => setActiveTab('arrivals')}
            >
              Arrivals
              {inboundCt > 0 && <span className="tab-badge badge-flight-accent" style={{ marginLeft: 6 }}>{inboundCt}</span>}
            </button>
            <button 
              className={`tab-btn tab-btn-thick ${activeTab === 'departures' ? 'active' : ''}`}
              onClick={() => setActiveTab('departures')}
            >
              Departures
              {onGroundCt > 0 && <span className="tab-badge badge-flight-open" style={{ marginLeft: 6 }}>{onGroundCt}</span>}
            </button>
          </div>
          <div className="flex-center-gap">
            {onExpand && (
              <button className="btn btn-sm" onClick={isExpanded ? onClose : onExpand}>
                {isExpanded ? 'Minimize' : 'Expand'}
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="panel-flex-col-inner scroll-container">
        <div className="flight-list">
          <div className="flight-header-row">
            <div>Flight</div>
            <div style={{ textAlign: 'right' }}>Schedule</div>
            <div>Status</div>
            <div style={{ textAlign: 'center' }}>Gate</div>
          </div>
          {flightList.map(f => (
            <div
              key={f.flight_id}
              className="flight-row"
              onClick={() => onFlightClick?.(f)}
              title={`${f.flight_id} · ${f.airline} · Click for details`}
            >

              {/* Airline / Flight ID */}
              <div className="flight-info">
                <div className="flight-name">{f.airline}</div>
                <div className="flight-id-label">{f.flight_id}</div>
              </div>

              {/* Times */}
              <div className="flight-times-col">
                {activeTab === 'arrivals' ? (
                  <div className="flight-time-row">
                    <span className="time-dir">▼</span>
                    <span className="time-sched">{formatShortTime(f.scheduled_arrival)}</span>
                    {f.actual_arrival && <>
                      <span className="time-arrow">→</span>
                      <span className="time-actual">{formatShortTime(f.actual_arrival)}</span>
                    </>}
                  </div>
                ) : (
                  <div className="flight-time-row">
                    <span className="time-dir">▲</span>
                    <span className="time-sched">{formatShortTime(f.scheduled_departure)}</span>
                    {f.actual_departure && <>
                      <span className="time-arrow">→</span>
                      <span className="time-actual">{formatShortTime(f.actual_departure)}</span>
                    </>}
                  </div>
                )}
              </div>

              {/* Status Column */}
              <div className="flex-col-gap-4" style={{ alignItems: 'flex-start' }}>
                <span className={`status-chip ${f.status}`}>
                  {STATUS_LABEL[f.status] ?? f.status}
                </span>
                {f.is_delayed && <span className="delay-chip">DLY</span>}
              </div>

              {/* Gate Column */}
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <span className="gate-chip">{f.assigned_gate ?? '—'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
