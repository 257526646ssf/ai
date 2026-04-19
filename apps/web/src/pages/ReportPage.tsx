import { useQuery } from "@tanstack/react-query";
import React from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorState, LoadingState } from "../components/states";

export function ReportPage() {
  const { reportId } = useParams();

  const reportQuery = useQuery({
    queryKey: ["report", reportId],
    queryFn: async () => (await api.get(`/executions/${reportId}/report`)).data,
    enabled: !!reportId,
  });

  if (reportQuery.isLoading) return <LoadingState />;
  if (reportQuery.error) return <ErrorState error="Failed to load report" onRetry={() => reportQuery.refetch()} />;

  return (
    <div>
      <h2>Report</h2>
      <pre>{JSON.stringify(reportQuery.data, null, 2)}</pre>
    </div>
  );
}
