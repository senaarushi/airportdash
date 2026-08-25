import { Briefcase, Plane, AlertTriangle, Activity, Map, CloudLightning, Wrench, Users } from 'lucide-react';

// Agent color config — single source of truth used across all components
export const AGENT_CONFIG = {
  gate_agent: {
    label: 'Gate Agent',
    color: '#7c3aed',
    soft: 'rgba(124,58,237,0.15)',
    icon: <Briefcase />,
  },
  crew_agent: {
    label: 'Crew Agent',
    color: '#0d9488',
    soft: 'rgba(13,148,136,0.15)',
    icon: <Users />,
  },
  ats_agent: {
    label: 'ATS Agent',
    color: '#d97706',
    soft: 'rgba(217,119,6,0.15)',
    icon: <Plane />,
  },
  disruption_agent: {
    label: 'Disruption',
    color: '#dc2626',
    soft: 'rgba(220,38,38,0.15)',
    icon: <AlertTriangle />,
  },
  orchestrator: {
    label: 'Orchestrator',
    color: '#2563eb',
    soft: 'rgba(37,99,235,0.15)',
    icon: <Activity />,
  },
};

export function getAgentConfig(agentId) {
  return AGENT_CONFIG[agentId] ?? {
    label: agentId,
    color: '#64748b',
    soft: 'rgba(100,116,139,0.15)',
    icon: <Map />,
  };
}

export function formatTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toUTCString().slice(17, 22) + ' UTC';
}

export function formatShortTime(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toUTCString().slice(17, 22);
}

export const DISRUPTION_ICONS = {
  WEATHER: <CloudLightning />,
  TECH_ISSUE: <Wrench />,
  CREW_SHORTAGE: <Users />,
};

export const DISRUPTION_LABELS = {
  WEATHER: 'Weather',
  TECH_ISSUE: 'Tech Issue',
  CREW_SHORTAGE: 'Crew Shortage',
};
