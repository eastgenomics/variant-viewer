import { formatYearOfBirth } from "@/lib/display-utils";

interface PatientDetail {
  id: number;
  name: string | null;
  lab_number: string;
  nhs_number: string | null;
  dob: string | null;
}

export default function PatientHeader({
  patient,
}: {
  patient: PatientDetail;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 mb-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">
            {patient.lab_number}
          </h1>
          <div className="flex gap-4 mt-1 text-sm text-gray-500">
            {patient.dob ? (
              <span>
                YOB: {formatYearOfBirth(patient.dob)}
              </span>
            ) : (
              <span>—</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
