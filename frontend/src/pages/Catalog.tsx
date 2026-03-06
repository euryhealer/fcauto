import { useEffect, useRef, useState } from "react";
import api from "../utils/api";

type Parent = {
  parent_sku: string;
  base_name?: string;
  brand?: string;
  woo_product_id?: number;
  sync_status?: string;
  last_error?: string;
  variations_count?: number;
  product_kind?: string;
};

type Variation = {
  variation_sku: string;
  parent_sku: string;
  brand?: string;
  color_code?: string;
  size_code?: string;
  name_full?: string;
  price?: string;
  additional_price?: string;
  woo_variation_id?: number;
  image_file_name?: string;
  image_preview_url?: string;
  sync_status?: string;
  last_error?: string;
};

const getVariationSubgroupKey = (variationSku: string) => {
  const sku = (variationSku || "").trim();
  const upper = sku.toUpperCase();

  // ADIH25 special rule: subgroup by color token (BLK, BLU, RED),
  // keeping all sizes under the same subgroup.
  const mAdih25 = upper.match(/^ADIH25-([^/]+)\/.+$/);
  if (mAdih25) return mAdih25[1];

  // JJ350-2.0-P special rule: subgroup by color (not size).
  const mJj350 = upper.match(/^(JJ350-2\.0-P)\/[^/-]+(?:-(.+))?$/);
  if (mJj350) {
    const colorToken = (mJj350[2] || "WHITE").trim();
    return `${mJj350[1]}-${colorToken}`;
  }

  // VENUM special rule:
  // subgroup = VENUM-<4|5 digits>-<3 digits>
  const mVenum = upper.match(/^(VENUM-\d{4,5}-\d{3})(?:[/-].*)?$/);
  if (mVenum) return mVenum[1];

  // EU-VENUM equivalent subgroup shape when present.
  const mEuVenum = upper.match(/^(EU-VENUM-\d{3,4}-\d{3})(?:[/-].*)?$/);
  if (mEuVenum) return mEuVenum[1];

  // EU-VENUM black special case: EU-VENUM-0003/<TALLA>
  const mEuVenumBlack = upper.match(/^(EU-VENUM-\d{3,4})\/[^/]+$/);
  if (mEuVenumBlack) return `${mEuVenumBlack[1]}-NEGRO`;

  const cut = sku.lastIndexOf("-");
  if (cut <= 0) return sku;
  const tail = sku.slice(cut + 1);
  if (/^[A-Za-z0-9]+$/.test(tail)) {
    return sku.slice(0, cut);
  }
  return sku;
};

const Catalog = () => {
  const [singleParents, setSingleParents] = useState<Parent[]>([]);
  const [variableParents, setVariableParents] = useState<Parent[]>([]);
  const [groups, setGroups] = useState<string[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string>("All");
  const [selectedBrand, setSelectedBrand] = useState<string>("All");
  const [activeTab, setActiveTab] = useState<"variable product" | "single product">(
    "variable product"
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedKind, setSelectedKind] = useState<"single product" | "variable product" | null>(null);
  const [variations, setVariations] = useState<Variation[]>([]);
  const [refreshingVariations, setRefreshingVariations] = useState(false);
  const [copiedParent, setCopiedParent] = useState(false);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [refreshingSubgroup, setRefreshingSubgroup] = useState<Record<string, boolean>>({});
  const [clearing, setClearing] = useState(false);
  const [query, setQuery] = useState("");
  const [variationPreviews, setVariationPreviews] = useState<Record<string, string>>({});
  const [copiedSubgroup, setCopiedSubgroup] = useState<string>("");
  const parentListRef = useRef<HTMLDivElement | null>(null);

  const loadParentsByKind = async (
    kind: "single product" | "variable product",
    group: string
  ) => {
    const params = group === "All" ? {} : { params: { group } };
    const res = await api.get("/catalog/parents", params);
    const filtered = (res.data as Parent[]).filter((p) => p.product_kind === kind);
    if (kind === "single product") {
      setSingleParents(filtered);
      return;
    }
    setVariableParents(filtered);
  };

  useEffect(() => {
    api.get("/catalog/groups").then((res) => setGroups(res.data.groups || []));
    void loadParentsByKind("single product", "All");
    void loadParentsByKind("variable product", "All");
  }, []);

  useEffect(() => {
    void loadParentsByKind("single product", selectedGroup);
    void loadParentsByKind("variable product", selectedGroup);
    setSelected(null);
    setSelectedKind(null);
    setVariations([]);
  }, [selectedGroup]);

  useEffect(() => {
    const all = [...singleParents, ...variableParents];
    const uniq = Array.from(
      new Set(
        all
          .map((p) => (p.brand || "").trim())
          .filter((b) => !!b)
      )
    ).sort((a, b) => a.localeCompare(b));
    setBrands(uniq);
  }, [singleParents, variableParents]);

  useEffect(() => {
    return () => {
      Object.values(variationPreviews).forEach((url) => URL.revokeObjectURL(url));
    };
  }, [variationPreviews]);

  const loadVar = async (sku: string, kind: "single product" | "variable product") => {
    setSelected(sku);
    setSelectedKind(kind);
    const activeGroup = selectedGroup;
    const params =
      activeGroup === "All" ? {} : { params: { group: activeGroup } };
    const safeSku = encodeURIComponent(sku);
    const res = await api.get(`/catalog/parents/${safeSku}/variations`, params);
    setVariations(res.data);
  };

  const clearAll = async () => {
    if (!confirm("Borrar todo el catalogo importado?")) return;
    setClearing(true);
    await api.delete("/catalog/clear");
    setSingleParents([]);
    setVariableParents([]);
    setVariations([]);
    setSelected(null);
    setSelectedKind(null);
    setClearing(false);
  };

  const refreshVariations = async () => {
    if (!selected || !selectedKind) return;
    setRefreshingVariations(true);
    try {
      await loadVar(selected, selectedKind);
      setPreviewNonce(Date.now());
    } finally {
      setRefreshingVariations(false);
    }
  };

  const copySelectedParent = async () => {
    if (!selected) return;
    try {
      await navigator.clipboard.writeText(selected);
      setCopiedParent(true);
      setTimeout(() => setCopiedParent(false), 1200);
    } catch {
      // ignore clipboard errors in this view
    }
  };

  const refreshSubgroup = async (subgroupKey: string) => {
    if (!selected || !selectedKind) return;
    setRefreshingSubgroup((prev) => ({ ...prev, [subgroupKey]: true }));
    try {
      await loadVar(selected, selectedKind);
      setPreviewNonce(Date.now());
    } finally {
      setRefreshingSubgroup((prev) => ({ ...prev, [subgroupKey]: false }));
    }
  };



  const copySubgroupFileName = async (subgroupKey: string) => {
    const fileBaseName = subgroupFileBaseNames[subgroupKey] || "";
    if (!fileBaseName) {
      setSubgroupStatus((prev) => ({
        ...prev,
        [subgroupKey]: "Subgrupo sin filename",
      }));
      return;
    }
    try {
      await navigator.clipboard.writeText(fileBaseName);
      setCopiedSubgroup(subgroupKey);
      setTimeout(() => {
        setCopiedSubgroup((prev) => (prev === subgroupKey ? "" : prev));
      }, 1200);
    } catch {
      // Ignore clipboard errors silently in this view.
    }
  };

  const q = query.trim().toLowerCase();
  const matches = (...values: Array<string | number | undefined>) =>
    !q ||
    values
      .filter((v) => v !== undefined && v !== null)
      .some((v) => String(v).toLowerCase().includes(q));

  const filteredSingleParents = singleParents.filter((p) =>
    (selectedBrand === "All" || (p.brand || "").trim() === selectedBrand) &&
    matches(p.parent_sku, p.base_name, p.brand, p.sync_status, p.last_error)
  );
  const filteredVariableParents = variableParents.filter((p) =>
    (selectedBrand === "All" || (p.brand || "").trim() === selectedBrand) &&
    matches(p.parent_sku, p.base_name, p.brand, p.sync_status, p.last_error)
  );
  const activeParents =
    activeTab === "variable product"
      ? filteredVariableParents
      : filteredSingleParents;
  const activeKind: "single product" | "variable product" =
    activeTab === "variable product" ? "variable product" : "single product";

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;

      const target = e.target as HTMLElement | null;
      const tag = (target?.tagName || "").toUpperCase();
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (!activeParents.length) return;

      const currentIdx = activeParents.findIndex((p) => p.parent_sku === selected);
      const nextIdx =
        e.key === "ArrowDown"
          ? Math.min(currentIdx < 0 ? 0 : currentIdx + 1, activeParents.length - 1)
          : Math.max(currentIdx < 0 ? 0 : currentIdx - 1, 0);

      const next = activeParents[nextIdx];
      if (!next || next.parent_sku === selected) return;
      e.preventDefault();
      void loadVar(next.parent_sku, activeKind);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeParents, selected, activeKind]);

  useEffect(() => {
    if (!selected || !parentListRef.current) return;
    const selectedKey = encodeURIComponent(selected);
    const el = parentListRef.current.querySelector(
      `[data-parent-key="${selectedKey}"]`
    ) as HTMLElement | null;
    if (!el) return;
    el.scrollIntoView({ block: "nearest" });
  }, [selected, activeParents, activeTab]);

  const filteredVariations = variations.filter((v) =>
    matches(
      v.variation_sku,
      v.parent_sku,
      v.color_code,
      v.size_code,
      v.name_full,
      v.sync_status,
      v.last_error
    )
  );

  const variationGroups = filteredVariations.reduce(
    (acc, v) => {
      const key = getVariationSubgroupKey(v.variation_sku);
      if (!acc[key]) acc[key] = [];
      acc[key].push(v);
      return acc;
    },
    {} as Record<string, Variation[]>
  );

  const apiRoot = (api.defaults.baseURL || "").replace(/\/api\/?$/, "");
  const toApiAssetUrl = (pathOrUrl?: string) => {
    const raw = (pathOrUrl || "").trim();
    if (!raw) return "";
    if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
    if (raw.startsWith("/")) return `${apiRoot}${raw}`;
    return raw;
  };
  const withCacheBust = (url?: string) => {
    const raw = (url || "").trim();
    if (!raw) return "";
    const sep = raw.includes("?") ? "&" : "?";
    return `${raw}${sep}v=${previewNonce}`;
  };
  const buildBrandAssetUrl = (brand?: string, fileName?: string) => {
    const b = (brand || "").trim();
    const f = (fileName || "").trim();
    if (!b || !f) return "";
    const safeFile = f.replace(/\\/g, "/").split("?")[0].split("/").pop() || f;
    if (!safeFile) return "";
    return `${apiRoot}/uploads/assets/img/${encodeURIComponent(
      b
    )}/${encodeURIComponent(safeFile)}`;
  };
  const subgroupServerPreviews = Object.entries(variationGroups).reduce(
    (acc, [subgroupKey, groupVars]) => {
      const previewFromApi =
        groupVars.find((v) => !!v.image_preview_url)?.image_preview_url || "";
      const first = groupVars[0];
      const previewFallback = buildBrandAssetUrl(first?.brand, first?.image_file_name);
      const preview = previewFromApi || previewFallback;
      acc[subgroupKey] = preview;
      return acc;
    },
    {} as Record<string, string>
  );
  const subgroupFileNames = Object.entries(variationGroups).reduce(
    (acc, [subgroupKey, groupVars]) => {
      const fileName = groupVars.find((v) => !!v.image_file_name)?.image_file_name || "";
      acc[subgroupKey] = fileName;
      return acc;
    },
    {} as Record<string, string>
  );
  const subgroupFileBaseNames = Object.entries(subgroupFileNames).reduce(
    (acc, [subgroupKey, fileName]) => {
      const cleaned = (fileName || "").trim().replace(/\\/g, "/");
      const onlyName = cleaned.split("?")[0].split("/").pop() || cleaned;
      acc[subgroupKey] = onlyName.replace(/\.[^.]+$/, "");
      return acc;
    },
    {} as Record<string, string>
  );
  const linkedPreviewUrl = (fileName: string) => {
    if (fileName && fileName.startsWith("local://")) {
      const raw = fileName.slice("local://".length);
      const safe = raw.split("/").pop() || raw;
      return `${apiRoot}/uploads/subgroups/${encodeURIComponent(safe)}`;
    }
    return "";
  };

  return (
    <div className="space-y-4 text-foreground">
      <h2 className="text-xl font-semibold">Catalog</h2>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-sm">Group</label>
          <select
            value={selectedGroup}
            onChange={(e) => setSelectedGroup(e.target.value)}
            className="rounded border px-2 py-1 bg-surface-2"
            style={{ borderColor: "var(--header-border)" }}
          >
            <option value="All">All</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm">Brand</label>
          <select
            value={selectedBrand}
            onChange={(e) => setSelectedBrand(e.target.value)}
            className="rounded border px-2 py-1 bg-surface-2"
            style={{ borderColor: "var(--header-border)" }}
          >
            <option value="All">All</option>
            {brands.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 flex-1 min-w-[280px]">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por SKU, nombre, color, talla o estado"
            className="w-full rounded border px-3 py-2 bg-surface-2"
            style={{ borderColor: "var(--header-border)" }}
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="px-3 py-2 rounded border bg-surface-2"
              style={{ borderColor: "var(--header-border)" }}
            >
              Limpiar
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">
          Single: {filteredSingleParents.length}/{singleParents.length} | Variable: {filteredVariableParents.length}/{variableParents.length} | Variaciones: {" "}
          {filteredVariations.length}/{variations.length || 0}
        </p>
        <button
          onClick={clearAll}
          disabled={clearing}
          className="px-3 py-1 rounded-lg bg-rose-600 text-white text-sm hover:bg-rose-700 disabled:bg-slate-300"
        >
          {clearing ? "Borrando..." : "Borrar todo"}
        </button>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div
          ref={parentListRef}
          className="catalog-panel rounded h-[620px] overflow-y-auto"
        >
          <div
            className="sticky top-0 z-10 px-3 py-2 border-b bg-surface-2"
            style={{ borderColor: "var(--header-border)" }}
          >
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab("variable product")}
                className={`px-3 py-1 rounded text-sm ${
                  activeTab === "variable product"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-200 text-slate-800"
                }`}
              >
                Variable Products ({filteredVariableParents.length})
              </button>
              <button
                onClick={() => setActiveTab("single product")}
                className={`px-3 py-1 rounded text-sm ${
                  activeTab === "single product"
                    ? "bg-blue-600 text-white"
                    : "bg-slate-200 text-slate-800"
                }`}
              >
                Single Products ({filteredSingleParents.length})
              </button>
            </div>
          </div>
          {activeParents.map((p) => {
            const active = selected === p.parent_sku;
            return (
              <button
                key={p.parent_sku}
                data-parent-key={encodeURIComponent(p.parent_sku)}
                onClick={() =>
                  loadVar(
                    p.parent_sku,
                    (p.product_kind as "single product" | "variable product") ||
                      "variable product"
                  )
                }
                className={`catalog-row w-full text-left px-3 py-2 border-b ${
                  active ? "border-l-4 border-blue-500" : ""
                }`}
                style={{
                  borderColor: "var(--header-border)",
                  backgroundColor: active
                    ? "rgba(59, 130, 246, 0.16)"
                    : "transparent",
                }}
              >
                <div className="font-semibold">{p.base_name || p.parent_sku}</div>
                <div className="text-xs text-slate-600">
                  SKU: {p.parent_sku} | Woo: {p.woo_product_id || "-"} |{" "}
                  Marca: {p.brand || "-"} | {p.sync_status} | {p.product_kind || "-"}
                </div>
              </button>
            );
          })}
        </div>
        <div className="catalog-panel rounded h-[620px] overflow-y-auto">
          <div className="sticky top-0 z-10 px-3 py-2 border-b bg-surface-2" style={{ borderColor: "var(--header-border)" }}>
            <div className="font-semibold">Variations</div>
          </div>
          {selected ? (
            <div>
              <div
                className="px-3 py-2 border-b"
                style={{ borderColor: "var(--header-border)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold">Variantes de {selected}</div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => void copySelectedParent()}
                      className="px-3 py-1 rounded bg-slate-200 text-slate-800 text-xs"
                    >
                      {copiedParent ? "Copiado" : "Copiar"}
                    </button>
                    <button
                      onClick={() => void refreshVariations()}
                      disabled={refreshingVariations}
                      className="px-3 py-1 rounded bg-slate-200 text-slate-800 text-xs disabled:bg-slate-300"
                    >
                      {refreshingVariations ? "Refreshing..." : "Refresh"}
                    </button>
                  </div>
                </div>
              </div>
              <div className="p-3 space-y-3">
                {Object.entries(variationGroups).map(([subgroupKey, groupVars], gIdx) => (
                  <div
                    key={subgroupKey}
                    className="rounded-lg border overflow-hidden"
                    style={{
                      borderColor: "var(--header-border)",
                      background: "var(--surface-2)",
                    }}
                  >
                  <div
                    className="px-3 py-2 text-xs font-semibold flex items-center justify-between gap-2"
                    style={{ background: "rgba(59, 130, 246, 0.16)" }}
                  >
                    <div className="min-w-0">
                      Subgrupo {gIdx + 1}: {subgroupKey}
                      {subgroupFileBaseNames[subgroupKey] ? (
                        <span className="ml-2 font-normal">
                          | File: {subgroupFileBaseNames[subgroupKey]}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => void refreshSubgroup(subgroupKey)}
                        disabled={!!refreshingSubgroup[subgroupKey]}
                        className="px-2 py-1 rounded bg-slate-200 text-slate-800 text-[11px] disabled:bg-slate-300"
                      >
                        {refreshingSubgroup[subgroupKey] ? "Refreshing..." : "Refresh"}
                      </button>
                      <button
                        onClick={() => void copySubgroupFileName(subgroupKey)}
                        className="px-2 py-1 rounded bg-slate-200 text-slate-800 text-[11px]"
                      >
                        {copiedSubgroup === subgroupKey ? "Copiado" : "Copiar"}
                      </button>
                    </div>
                  </div>
                  <div className="px-3 py-2 border-t" style={{ borderColor: "var(--header-border)" }}>
                    <div className="space-y-2">
                      {(toApiAssetUrl(subgroupServerPreviews[subgroupKey])) && (
                        <img
                          src={
                            withCacheBust(
                                toApiAssetUrl(subgroupServerPreviews[subgroupKey])
                            )
                          }
                          alt={`Preview ${subgroupKey}`}
                          className="w-24 h-24 rounded border object-cover"
                          style={{ borderColor: "var(--header-border)" }}
                        />
                      )}
                    </div>
                  </div>
                  {groupVars.map((v, idx) => (
                    <div
                      key={v.variation_sku}
                      className="px-3 py-2 border-t"
                      style={{ borderColor: "var(--header-border)" }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-xs font-semibold">Variante {idx + 1}</div>
                          <div className="font-semibold">{v.variation_sku}</div>
                          <div className="text-xs text-slate-600">
                            Color: {v.color_code} | Talla: {v.size_code} | Marca: {v.brand || "-"} | Precio: {v.price || "-"} | Precio oferta: {v.additional_price || "-"} | Woo: {" "}
                            {v.woo_variation_id || "-"}
                          </div>
                          <div className="text-xs text-slate-600">
                            File: {(v.image_file_name || "").trim() || "-"}
                          </div>
                          {v.last_error && (
                            <div className="text-xs text-red-600">{v.last_error}</div>
                          )}
                        </div>
                        {(variationPreviews[v.variation_sku] ||
                          toApiAssetUrl(v.image_preview_url) ||
                          buildBrandAssetUrl(v.brand, v.image_file_name)) && (
                          <img
                            src={
                              withCacheBust(
                                variationPreviews[v.variation_sku] ||
                                toApiAssetUrl(v.image_preview_url) ||
                                  buildBrandAssetUrl(v.brand, v.image_file_name)
                              )
                            }
                            alt={`Preview ${v.variation_sku}`}
                            className="w-24 h-24 rounded border object-cover shrink-0"
                            style={{ borderColor: "var(--header-border)" }}
                          />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-3 text-slate-600">
              Selecciona un padre para ver variaciones
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Catalog;

