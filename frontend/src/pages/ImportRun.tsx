import { useRef, useState } from "react";
import api from "../utils/api";

type Summary = { rows?: number; parents?: number; error?: string };

const ImportRun = () => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [summary, setSummary] = useState<Summary>({});
  const [progress, setProgress] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [errorDetail, setErrorDetail] = useState<string>("");
  const [isDragActive, setIsDragActive] = useState(false);

  const upload = async (incomingFile?: File) => {
    const file = incomingFile || inputRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatus("Subiendo y analizando...");
    setProgress("");
    setErrorDetail("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await api.post("/import", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setSummary(res.data);
      setStatus(res.data.error ? "Import con errores" : "Import listo");
    } catch (e) {
      const err =
        (e as any)?.response?.data?.detail ||
        (e as any)?.response?.data?.error ||
        (e as any)?.message ||
        "Fallo la importacion";
      setStatus(err);
      const detail = (e as any)?.response
        ? JSON.stringify((e as any).response.data, null, 2)
        : String(e);
      setErrorDetail(detail);
      console.error("Import error", detail);
    } finally {
      setUploading(false);
      setIsDragActive(false);
    }
  };

  const onFileChange = () => {
    const file = inputRef.current?.files?.[0];
    if (file) {
      setFileName(file.name);
      setStatus(`Archivo seleccionado: ${file.name}`);
      // auto-start upload for mejor UX
      void upload(file);
    } else {
      setFileName("");
      setStatus("");
    }
  };

  const startSync = async () => {
    setStatus("Ejecutando sync...");
    const res = await api.post("/sync");
    const id = res.data.run_id;
    listen(id);
  };

  const listen = (id: number) => {
    const ev = new EventSource(api.defaults.baseURL + `/sync/${id}/events`);
    ev.onmessage = (e) => {
      setProgress(e.data);
    };
    ev.onerror = () => ev.close();
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-sm uppercase tracking-[0.2em] text-blue-500 font-semibold">
          Paso 1
        </p>
        <h2 className="text-2xl font-semibold text-white drop-shadow-sm dark:text-white text-slate-900">
          Importa tu Excel
        </h2>
        <p className="text-sm text-slate-700 dark:text-white font-semibold">
          Columnas requeridas: SKU, NOMBRE, FOTO. PRECIO y STOCK son opcionales.
        </p>
      </header>

      <div
        className="rounded-2xl border bg-surface-2 shadow-sm p-6 space-y-4 backdrop-blur"
        style={{ borderColor: "var(--header-border)" }}
      >
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          <label htmlFor="excel-file" className="flex-1 cursor-pointer">
            <div
              className={`drop-zone w-full rounded-xl border border-dashed ${
                isDragActive ? "drop-zone-active scale-[1.02]" : ""
              } transition p-4 text-center relative overflow-hidden`}
              onDragOver={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setIsDragActive(true);
              }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                const file = e.dataTransfer?.files?.[0];
                if (file) {
                  setFileName(file.name);
                  setStatus(`Archivo seleccionado: ${file.name}`);
                  void upload(file);
                }
                setIsDragActive(false);
              }}
              onDragLeave={() => setIsDragActive(false)}
            >
              <p className="text-sm text-slate-600">
                Arrastra tu Excel o haz clic para elegir
              </p>
              <p className="text-xs text-slate-500 mt-1">
                .xlsx o .xls - Max 10 MB
              </p>
              {isDragActive && (
                <div className="falling-file" aria-hidden>
                  <div className="file-ghost">FILE</div>
                </div>
              )}
            </div>
            <input
              id="excel-file"
              ref={inputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={onFileChange}
            />
          </label>
          <button
            onClick={() => upload()}
            disabled={uploading}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white font-medium shadow hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
          >
            {uploading ? "Analizando..." : "Subir y analizar"}
          </button>
        </div>

        {status && (
          <div className="flex items-center gap-2 text-sm text-slate-700">
            {uploading && (
              <span className="w-4 h-4 rounded-full border-2 border-blue-600 border-t-transparent animate-spin inline-block" />
            )}
            <span>{status}</span>
          </div>
        )}
        {errorDetail && (
          <pre className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded p-3 whitespace-pre-wrap">
            {errorDetail}
          </pre>
        )}
        {fileName && !uploading && (
          <div className="text-xs text-slate-500">
            Listo para subir: {fileName}
          </div>
        )}

        {summary && (summary.rows || summary.error) && (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div className="summary-card rounded-lg bg-blue-50 border border-blue-100 p-3 text-blue-900">
              <p className="text-xs uppercase tracking-wide">Filas</p>
              <p className="text-xl font-semibold">{summary.rows ?? "-"}</p>
            </div>
            <div className="summary-card rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-emerald-900">
              <p className="text-xs uppercase tracking-wide">Padres</p>
              <p className="text-xl font-semibold">{summary.parents ?? "-"}</p>
            </div>
            <div className="summary-card rounded-lg bg-amber-50 border border-amber-100 p-3 text-amber-900">
              <p className="text-xs uppercase tracking-wide">Estado</p>
              <p className="text-sm">{summary.error ? summary.error : "OK"}</p>
            </div>
          </div>
        )}
      </div>

      <div
        className="rounded-2xl border bg-surface-2 shadow-sm p-6 backdrop-blur space-y-3"
        style={{ borderColor: "var(--header-border)" }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-emerald-500 font-semibold">
              Paso 2
            </p>
            <h3 className="text-lg font-semibold text-slate-900">
              Ejecutar Sync (opcional)
            </h3>
            <p className="text-slate-600 text-sm">
              Si solo quieres importar, puedes omitir este paso.
            </p>
          </div>
          <button
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white font-medium shadow hover:bg-emerald-700"
            onClick={startSync}
          >
            Iniciar Sync
          </button>
        </div>
        {progress && (
          <pre className="bg-slate-900 text-slate-50 p-3 rounded text-xs whitespace-pre-wrap">
            {progress}
          </pre>
        )}
      </div>
    </div>
  );
};

export default ImportRun;
