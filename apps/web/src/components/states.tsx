import React from "react";

export function LoadingState() {
  return <p>Loading...</p>;
}

export function EmptyState({ message }: { message: string }) {
  return <p>{message}</p>;
}

export function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div>
      <p style={{ color: "crimson" }}>{error}</p>
      <button onClick={onRetry}>Retry</button>
    </div>
  );
}
