import type { JobStatus } from "../api/client";
import JobRow from "./JobRow";

interface Props {
  jobs: JobStatus[];
  onTrigger: (key: string) => void;
}

export default function JobTable({ jobs, onTrigger }: Props) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-10"></th>
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Remarks</th>
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Last Sync Status</th>
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Previous Sync Date</th>
            <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider"></th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job, i) => (
            <JobRow key={job.key} index={i + 1} job={job} onTrigger={onTrigger} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
