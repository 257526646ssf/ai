import { useQuery } from "@tanstack/react-query";
import React from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorState, LoadingState } from "../components/states";

export function ExecutionPage() {
  const { execId } = useParams();

  const resultQuery = useQuery({
    queryKey: ["execution", execId],
    queryFn: async () => (await api.get(`/executions/${execId}/results`)).data,
    enabled: !!execId,
    refetchInterval: 3000,
  });

  if (resultQuery.isLoading) return <LoadingState />;
  if (resultQuery.error) return <ErrorState error="Failed to load execution" onRetry={() => resultQuery.refetch()} />;

  return (
    <div>
      <h2>Execution Monitor</h2>
      <pre>{JSON.stringify(resultQuery.data, null, 2)}</pre>
    </div>
  );
}
