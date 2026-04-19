import { useQuery } from "@tanstack/react-query";
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, setToken } from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/states";

export function ProjectsPage() {
  const [token, setTokenState] = useState("");

  useEffect(() => {
    async function bootstrap() {
      const response = await api.post("/auth/login", { userId: "demo-user", role: "owner" });
      setToken(response.data.accessToken);
      setTokenState(response.data.accessToken);
    }

    bootstrap().catch(() => null);
  }, []);

  const projectsQuery = useQuery({
    queryKey: ["projects", token],
    queryFn: async () => (await api.get("/projects")).data,
    enabled: !!token,
  });

  if (!token) return <LoadingState />;
  if (projectsQuery.isLoading) return <LoadingState />;
  if (projectsQuery.error) return <ErrorState error="Failed to load projects" onRetry={() => projectsQuery.refetch()} />;

  const projects = projectsQuery.data || [];

  return (
    <div>
      <h2>Projects</h2>
      {projects.length === 0 ? (
        <EmptyState message="No projects yet. Use API POST /projects to add one." />
      ) : (
        <ul>
          {projects.map((project: { id: string; name: string }) => (
            <li key={project.id}>
              <Link to={`/projects/${project.id}`}>{project.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
