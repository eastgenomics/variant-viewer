import { useState, useEffect } from "react";
import { updateWorkflow } from "../lib/api";
import type { WorkflowStatus } from "../lib/api";

const TRANSITIONS: Record<string, WorkflowStatus[]> = {
  pending:   ["reviewing", "archived"],
  reviewing: ["reported", "archived"],
  reported:  ["archived"],
  archived:  [],
};

export default function WorkflowControl({
  sampleId,
  currentStatus,
}: {
  sampleId: number;
  currentStatus: string;
}) {
  const [status, setStatus] = useState(currentStatus);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync local status when parent prop changes (e.g. after external refresh)
  useEffect(() => { setStatus(currentStatus); }, [currentStatus]);

  const transitions = TRANSITIONS[status] ?? [];

  async function handleTransition(newStatus: WorkflowStatus) {
    setLoading(true);
    setError(null);
    try {
      const userId = import.meta.env.VITE_USER_ID ?? "analyst";
      await updateWorkflow(sampleId, newStatus, userId);
      setStatus(newStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-red-600">{error}</span>}
      {transitions.map((next) => (
        <button
          key={next}
          className="btn btn-secondary text-xs"
          disabled={loading}
          onClick={() => handleTransition(next)}
        >
          {`→ ${next}`}
        </button>
      ))}
    </div>
  );
}
