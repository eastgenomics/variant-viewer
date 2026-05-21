import { useState } from "react";
import { deleteSample } from "../lib/api";

export default function DeleteSampleButton({
  id,
  name,
  workflowStatus,
  onDelete,
}: {
  id: number;
  name: string;
  workflowStatus: string;
  onDelete?: (id: number) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const isHighRisk =
    workflowStatus === "reported" || workflowStatus === "archived";

  if (confirming) {
    return (
      <span className="flex gap-1 items-center">
        {isHighRisk && (
          <span className="text-xs text-amber-600 mr-1">
            ⚠ This specimen has been {workflowStatus}.
          </span>
        )}
        {!isHighRisk && (
          <span className="text-xs text-gray-700 mr-1">Delete <strong>{name}</strong>?</span>
        )}
        <button
          className="btn btn-danger text-xs py-0.5 px-2"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setDeleteError(null);
            try {
              await deleteSample(id);
              onDelete?.(id);
              setConfirming(false);
            } catch (e) {
              setDeleteError(e instanceof Error ? e.message : "Delete failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Deleting…" : "Yes, delete"}
        </button>
        <button
          className="btn btn-secondary text-xs py-0.5 px-2"
          onClick={() => { setConfirming(false); setDeleteError(null); }}
        >
          Cancel
        </button>
        {deleteError && (
          <span className="text-xs text-red-600 ml-1">{deleteError}</span>
        )}
      </span>
    );
  }
  return (
    <button
      className="text-red-500 hover:text-red-700 text-xs"
      onClick={() => setConfirming(true)}
    >
      Delete
    </button>
  );
}
