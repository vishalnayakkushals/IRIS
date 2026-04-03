import type { JobStatus } from "../api/client";
import StatusBadge from "./StatusBadge";

interface Props {
  index: number;
  job: JobStatus;
  onTrigger: (key: string) => void;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

const ACTIVE = new Set(["running", "queued"]);

export default function JobRow({ index, job, onTrigger }: Props) {
  const isActive = ACTIVE.has(job.status);

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
      <td className="px-6 py-4 text-sm text-gray-500 w-10">{index}</td>

      <td className="px-6 py-4 font-medium text-gray-800 text-sm">{job.name}</td>

      <td className="px-6 py-4 text-sm">
        <span className={job.status === "failed" ? "text-red-600" : "text-green-600"}>
          {job.remarks || "—"}
        </span>
      </td>

      <td className="px-6 py-4">
        <StatusBadge status={job.status} />
      </td>

      <td className="px-6 py-4 text-sm text-gray-500">{fmtDate(job.last_run_at)}</td>

      <td className="px-6 py-4">
        {isActive ? (
          <button
            disabled
            className="px-4 py-2 rounded text-xs font-semibold bg-green-500 text-white cursor-not-allowed opacity-80"
          >
            In progress
          </button>
        ) : (
          <button
            onClick={() => onTrigger(job.key)}
            className="px-4 py-2 rounded text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            Sync Now
          </button>
        )}
      </td>
    </tr>
  );
}
