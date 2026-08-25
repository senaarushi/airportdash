import { NavLink } from 'react-router-dom';

export function Sidebar({ activeDisruptions, openConflicts }) {


  return (
    <aside className="sidebar">
      <div className="flex-col-gap-4">
        <NavLink
          to="/"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="Command Center"
        >
          <span>Command Center</span>
        </NavLink>

        <NavLink
          to="/gate"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="Gate Agent"
        >
          <span>Gate Ops</span>
        </NavLink>

        <NavLink
          to="/crew"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="Crew Agent"
        >
          <span>Ground Crew</span>
        </NavLink>

        <NavLink
          to="/ats"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="ATS Control"
        >
          <span>ATS Control</span>
        </NavLink>

        <NavLink
          to="/radar"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="ATC Radar"
        >
          <span>ATC Radar</span>
        </NavLink>

        <NavLink
          to="/disruptions"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          title="Disruption Agent"
        >
          <span>Disruptions</span>
          {(activeDisruptions > 0 || openConflicts > 0) && (
            <span className="nav-badge">
              {activeDisruptions + openConflicts}
            </span>
          )}
        </NavLink>
      </div>

    </aside>
  );
}
