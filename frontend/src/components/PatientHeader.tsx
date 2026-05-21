import type { PatientDetailResponse } from "../lib/api";

export default function PatientHeader({
  patient,
}: {
  patient: Pick<PatientDetailResponse, "id" | "lab_number">;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">
            {patient.lab_number}
          </h1>
        </div>
      </div>
    </div>
  );
}
