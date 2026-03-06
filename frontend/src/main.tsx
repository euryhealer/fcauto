import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import App from "./pages/App";
import Config from "./pages/Config";
import ImportRun from "./pages/ImportRun";
import Logs from "./pages/Logs";
import Catalog from "./pages/Catalog";
import "./styles.css";

const Layout = () => (
  <ThemeShell>
    <header
      className="border-b sticky top-0 z-10"
      style={{ background: "var(--header-bg)", borderColor: "var(--header-border)" }}
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div
          className="font-semibold text-lg"
          style={{ color: "var(--brand)" }}
        >
          Woo Sync
        </div>
        <nav className="flex items-center gap-4 text-sm">
          {[
            ["/", "Inicio"],
            ["/config", "Config"],
            ["/import", "Import & Run"],
            ["/logs", "Logs"],
            ["/catalog", "Catalog"],
          ].map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                isActive
                  ? "text-blue-700 dark:text-white font-semibold"
                  : "text-slate-700 dark:text-white font-semibold"
              }
            >
              {label}
            </NavLink>
          ))}
          <ThemeToggle />
        </nav>
      </div>
    </header>
    <main className="max-w-6xl mx-auto px-4 py-6">
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/config" element={<Config />} />
        <Route path="/import" element={<ImportRun />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/catalog" element={<Catalog />} />
      </Routes>
    </main>
  </ThemeShell>
);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  </React.StrictMode>
);

// Simple theme provider using data-theme + localStorage
function ThemeShell({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("theme") as "light" | "dark") || "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <div className="min-h-screen bg-surface text-foreground transition-colors">
      {children}
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("theme") as "light" | "dark") || "light";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <button
      onClick={() => setTheme(theme === "light" ? "dark" : "light")}
      className="relative w-12 h-6 rounded-full border border-slate-300 bg-slate-100/90 dark:border-slate-700 dark:bg-slate-700/70 transition-colors flex items-center"
      aria-label="Toggle theme"
    >
      <span
        className={`absolute h-5 w-5 rounded-full shadow-sm transition-all ${
          theme === "light"
            ? "left-0.5 bg-slate-200"
            : "left-6 bg-amber-400/80"
        }`}
        style={{ top: "50%", transform: "translateY(-50%)" }}
      />
    </button>
  );
}
