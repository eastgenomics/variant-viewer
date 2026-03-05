"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Props {
  id: number;
  name: string;
  workflowStatus: string;
}

export default function DeleteSampleButton({ id, name, workflowStatus }: Props) {
  const router = useRouter();
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isHighRisk = workflowStatus === "reported" || workflowStatus === "archived";

  const confirmMessage = isHighRisk
    ? `This sample is ${workflowStatus}. Deleting it will permanently remove all variants and classifications.`
    : `Delete ${name} and all its variants and classifications?`;

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(`/api/samples?id=${id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error ?? "Delete failed");
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setDeleting(false);
    }
  }

  if (showConfirm) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded text-sm">
        <span className="text-red-700 text-xs">{confirmMessage}</span>
        <button
          className="btn btn-danger text-xs"
          onClick={handleDelete}
          disabled={deleting}
        >
          {deleting ? "Deleting…" : "Yes, delete"}
        </button>
        <button
          className="btn btn-secondary text-xs"
          onClick={() => { setShowConfirm(false); setError(null); }}
          disabled={deleting}
        >
          Cancel
        </button>
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        className="btn btn-danger text-xs"
        onClick={() => setShowConfirm(true)}
      >
        Delete sample
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
