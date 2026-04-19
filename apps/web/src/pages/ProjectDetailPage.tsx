import { useQuery } from "@tanstack/react-query";
import React from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/states";

export function ProjectDetailPage() {
  const { id } = useParams();

  const casesQuery = useQuery({
    queryKey: ["cases", id],
    queryFn: async () => (await api.get(`/projects/${id}/test-cases`)).data,
    enabled: !!id,
  });

  if (casesQuery.isLoading) return <LoadingState />;
  if (casesQuery.error) return <ErrorState error="Failed to load test cases" onRetry={() => casesQuery.refetch()} />;

  const testCases = casesQuery.data || [];

  return (
    <div>
      <h2>Project Detail: {id}</h2>
      {testCases.length === 0 ? (
        <EmptyState message="No test cases yet." />
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Priority</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {testCases.map((item: { id: string; title: string; priority: string; status: string }) => (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{item.priority}</td>
                <td>{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
