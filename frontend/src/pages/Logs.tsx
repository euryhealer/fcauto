import { useEffect, useState } from "react";
import api from "../utils/api";

type Log = { id: number; ts: string; level: string; sku?: string; message: string };

const Logs = () => {
  const [runId, setRunId] = useState<number>(1);
  const [logs, setLogs] = useState<Log[]>([]);

  useEffect(() => {
    load();
  }, [runId]);

  const load = async () => {
    const res = await api.get(`/sync/${runId}/logs`);
    setLogs(res.data);
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Logs</h2>
      <div className="flex gap-2 items-center">
        <label className="text-sm">run_id</label>
        <input
          value={runId}
          onChange={(e) => setRunId(Number(e.target.value))}
          className="border rounded px-2 py-1 w-24"
        />
        <button className="px-3 py-1 bg-slate-200 rounded" onClick={load}>
          Refrescar
        </button>
      </div>
      <div className="bg-white border rounded divide-y">
        {logs.map((l) => (
          <div key={l.id} className="p-2 text-sm flex gap-3">
            <span className="font-mono text-xs text-slate-500">{l.ts}</span>
            <span
              className={
                l.level === "ERROR"
                  ? "text-red-600"
                  : l.level === "WARN"
                  ? "text-amber-600"
                  : "text-slate-700"
              }
            >
              {l.level}
            </span>
            <span className="text-slate-600">{l.sku}</span>
            <span>{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Logs;
