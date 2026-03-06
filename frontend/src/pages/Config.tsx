import { useEffect, useState } from "react";
import api from "../utils/api";

type Config = {
  woo_base_url: string;
  woo_key: string;
  woo_secret: string;
  wp_base_url: string;
  wp_username: string;
  wp_app_password: string;
  drive_folder_id: string;
  attr_color_name: string;
  attr_size_name: string;
  dry_run_default: boolean;
};

const Config = () => {
  const [form, setForm] = useState<Config>({
    woo_base_url: "",
    woo_key: "",
    woo_secret: "",
    wp_base_url: "",
    wp_username: "",
    wp_app_password: "",
    drive_folder_id: "",
    attr_color_name: "Color",
    attr_size_name: "Talla",
    dry_run_default: false,
  });
  const [status, setStatus] = useState<string>("");

  useEffect(() => {
    api.get("/config").then((res) => setForm(res.data));
  }, []);

  const save = async () => {
    await api.post("/config", form);
    setStatus("Guardado");
  };

  const test = async (path: string) => {
    setStatus("Probando...");
    try {
      const res = await api.post(path);
      setStatus(res.data.ok ? "OK" : "Error");
    } catch (e) {
      setStatus("Error");
    }
  };

  return (
    <div className="space-y-4 config-page">
      <h2 className="text-xl font-semibold">Config</h2>
      <div className="grid grid-cols-2 gap-3">
        {(
          Object.entries(form) as [keyof Config, Config[keyof Config]][]
        ).map(([k, v]) =>
          typeof v === "boolean" ? (
            <label key={k} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={v}
                onChange={(e) => setForm({ ...form, [k]: e.target.checked })}
              />
              <span>{k}</span>
            </label>
          ) : (
            <label key={k} className="flex flex-col text-sm text-slate-700">
              {k}
              <input
                className="border rounded px-2 py-1"
                value={v || ""}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </label>
          )
        )}
      </div>
      <div className="flex gap-2">
        <button
          className="px-3 py-1 bg-blue-600 text-white rounded config-button-text"
          onClick={save}
        >
          Guardar
        </button>
        <button
          className="px-3 py-1 bg-slate-200 rounded config-button-text"
          onClick={() => test("/test/woo")}
        >
          Test Woo
        </button>
        <button
          className="px-3 py-1 bg-slate-200 rounded config-button-text"
          onClick={() => test("/test/wp")}
        >
          Test WP
        </button>
        <button
          className="px-3 py-1 bg-slate-200 rounded config-button-text"
          onClick={() => test("/test/drive")}
        >
          Test Drive
        </button>
      </div>
      {status && <p className="text-sm text-slate-600">{status}</p>}
    </div>
  );
};

export default Config;
