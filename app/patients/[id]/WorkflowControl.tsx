"use client";

import { useState } from "react";

const TRANSITIONS: Record<string, string[]> = {
  pending: ["reviewing"],
  reviewing: ["reported", "pending"],
  reported: ["archived", "reviewing"],
  archived: ["reviewing"],
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

  const transitions = TRANSITIONS[status] ?? [];

  async function updateStatus(newStatus: string) {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/workflow", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_id: sampleId, status: newStatus }),
      });
      if (!resp.ok) {
        const body = await resp.json();
        throw new Error(body.error ?? "Update failed");
      }
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
          onClick={() => updateStatus(next)}
        >
          {loading ? "…" : `→ ${next}`}
        </button>
      ))}
    </div>
  );
}
