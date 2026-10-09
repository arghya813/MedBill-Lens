import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { FlaskConical, Info, Menu, Scale, X } from "lucide-react";
import { useAppMeta } from "@/state/AppMeta";
import { usePreferences } from "@/state/Preferences";
import { DisclaimerFooter } from "@/components/DisclaimerFooter";
import { Notice } from "@/components/Notice";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/review", label: "Check a bill", end: false },
  { to: "/benchmarks", label: "Benchmarks", end: false },
  { to: "/demo", label: "Demo", end: false },
  { to: "/about", label: "About", end: false },
  { to: "/profile", label: "Profile", end: false },
];

export function Layout() {
  const { health, disclaimer, unreachable } = useAppMeta();
  const { preferences } = usePreferences();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname, hash } = useLocation();

  // Navigating away from a long page should land at the top of the new one, not
  // halfway down. Explicit hashes are left alone so anchor links still work.
  useEffect(() => {
    setMenuOpen(false);
    if (hash) return;
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [pathname, hash]);

  return (
    <div
      className={`flex min-h-screen flex-col${
        preferences.density === "compact" ? " text-[15px] leading-relaxed" : ""
      }`}
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-ink-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5" onClick={() => setMenuOpen(false)}>
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
              <Scale className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="leading-tight">
              <span className="block text-base font-semibold tracking-tight text-ink-900">
                MedBill Lens
              </span>
              <span className="block text-xs text-ink-500">Hospital bill clarity</span>
            </span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `nav-underline rounded-lg px-3 py-2 text-sm font-medium transition-colors
                   duration-150 ${
                     isActive
                       ? "bg-brand-50 text-brand-800"
                       : "text-ink-600 hover:bg-ink-100 hover:text-ink-900"
                   }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {preferences.display_name ? (
              <span
                className="hidden max-w-[12rem] truncate rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800 sm:inline-flex"
                title={`Signed in locally as ${preferences.display_name}`}
              >
                {preferences.display_name}
              </span>
            ) : null}
            {health ? (
              <span
                className="hidden rounded-full bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-600 sm:inline-flex"
                title={
                  health.ai_provider_is_real
                    ? `AI provider: ${health.ai_provider}`
                    : `Running the built-in demo engine (${health.ai_provider}). No AI key configured.`
                }
              >
                {health.ai_provider_is_real ? health.ai_provider : "Demo engine"}
              </span>
            ) : null}
            <button
              type="button"
              className="btn-ghost px-2 md:hidden"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {menuOpen ? (
          <nav
            className="anim-slide-left border-t border-ink-200 bg-white px-4 py-2 md:hidden"
            aria-label="Mobile"
          >
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2.5 text-sm font-medium ${
                    isActive ? "bg-brand-50 text-brand-800" : "text-ink-700 hover:bg-ink-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
      </header>

      {unreachable ? (
        <div className="mx-auto w-full max-w-6xl px-4 pt-4 sm:px-6">
          <Notice tone="warning" title="We can't reach the MedBill Lens API">
            Start the backend with <code className="font-mono">uvicorn app.main:app --reload</code>{" "}
            on port 8000, then reload this page. Benchmark browsing and uploads will stay
            unavailable until then.
          </Notice>
        </div>
      ) : null}

      <main id="main" className="flex-1">
        {/* Keyed on the path so each page fades in instead of swapping abruptly. */}
        <div key={pathname} className="anim-fade">
          <Outlet />
        </div>
      </main>

      <DisclaimerFooter disclaimer={disclaimer} />

      {health?.demo_mode ? (
        <div className="border-t border-ink-200 bg-ink-100/70">
          <div className="mx-auto flex max-w-6xl items-start gap-2 px-4 py-2.5 text-xs text-ink-600 sm:px-6">
            <FlaskConical className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-500" aria-hidden="true" />
            <p>
              Demo mode is on. Benchmark records and sample bills are synthetic and must not be
              used for real-world decisions.
            </p>
          </div>
        </div>
      ) : null}

      <div className="border-t border-ink-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-ink-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            MedBill Lens provides information for your own review. It does not provide medical,
            legal or financial advice.
          </p>
          <Link to="/about" className="inline-flex items-center gap-1 hover:text-ink-800">
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
            Methodology and limits
          </Link>
        </div>
      </div>
    </div>
  );
}
