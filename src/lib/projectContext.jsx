import React from 'react';
import { apiGet, pickList } from './api';

const STORAGE_KEY = 'aitest:selectedProjectId';

const ProjectContext = React.createContext(null);

export function ProjectProvider({ children }) {
  const [projects, setProjects] = React.useState([]);
  const [selectedProjectId, setSelectedProjectIdState] = React.useState(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY) || '';
    } catch {
      return '';
    }
  });
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  const refreshProjects = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const payload = await apiGet('/projects', { params: { page: 1, pageSize: 200 } });
      const nextProjects = pickList(payload);
      setProjects(nextProjects);
      setSelectedProjectIdState((current) => {
        const currentExists = nextProjects.some((project) => String(project.id) === String(current));
        const nextId = currentExists ? current : String(nextProjects[0]?.id || '');
        try {
          if (nextId) window.localStorage.setItem(STORAGE_KEY, nextId);
        } catch {
          // localStorage may be unavailable in restricted browser modes.
        }
        return nextId;
      });
    } catch (err) {
      setProjects([]);
      setError(err?.message || 'Project list unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  const setSelectedProjectId = React.useCallback((projectId) => {
    const nextId = String(projectId || '');
    setSelectedProjectIdState(nextId);
    try {
      if (nextId) window.localStorage.setItem(STORAGE_KEY, nextId);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // localStorage may be unavailable in restricted browser modes.
    }
  }, []);

  const selectedProject = React.useMemo(
    () => projects.find((project) => String(project.id) === String(selectedProjectId)) || projects[0] || null,
    [projects, selectedProjectId]
  );

  const value = React.useMemo(
    () => ({
      projects,
      selectedProject,
      selectedProjectId: selectedProject?.id ? String(selectedProject.id) : '',
      setSelectedProjectId,
      refreshProjects,
      loading,
      error
    }),
    [projects, selectedProject, setSelectedProjectId, refreshProjects, loading, error]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjectContext() {
  const context = React.useContext(ProjectContext);
  if (!context) {
    return {
      projects: [],
      selectedProject: null,
      selectedProjectId: '',
      setSelectedProjectId: () => {},
      refreshProjects: () => Promise.resolve(),
      loading: false,
      error: ''
    };
  }
  return context;
}
