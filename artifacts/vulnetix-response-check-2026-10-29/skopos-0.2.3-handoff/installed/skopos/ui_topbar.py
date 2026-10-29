"""Fixed top application bar — docs & quick links in the header zone."""

from __future__ import annotations

import html

import streamlit as st

from skopos.i18n import t
from skopos.themes import get_active_theme

# Compact header row (Running… + left-aligned nav).
_BAR_H = "2.125rem"
_TOP_GAP = "16px"


def _app_base() -> str:
    """Streamlit subpath when served behind nginx at /app/."""
    try:
        base = st.get_option("server.baseUrlPath") or ""
    except Exception:
        import os

        base = os.environ.get("STREAMLIT_SERVER_BASE_URL_PATH", "")
    base = str(base).strip().strip("/")
    return f"/{base}" if base else ""


def _page_href(script_path: str) -> str:
    """Best-effort Streamlit multipage URL slug."""
    base = _app_base()
    name = script_path.replace("\\", "/").split("/")[-1]
    if name == "dashboard.py":
        return f"{base}/" if base else "/"
    if name.endswith(".py"):
        slug = name.replace(".py", "").split("_", 1)[-1]
        return f"{base}/{slug}" if base else f"/{slug}"
    slug = name
    return f"{base}/{slug}" if base else f"/{slug}"


def build_topbar_css(theme) -> str:
    th = theme
    cosmic = theme.id == "midnight"
    link_bg = "rgba(18,12,22,0.72)" if cosmic else f"color-mix(in srgb, {th.card_bg} 82%, transparent)"
    link_border = "rgba(255,160,80,0.22)" if cosmic else th.border
    link_shadow = "0 4px 18px rgba(0,0,0,0.35)" if cosmic else "0 2px 10px rgba(0,0,0,0.08)"
    link_hover_shadow = "0 8px 28px rgba(255,140,42,0.22)" if cosmic else "0 6px 20px rgba(0,0,0,0.12)"
    return f"""
<style id="skopos-topbar">
  :root {{
    --skopos-header-height: {_BAR_H};
    --sidebar-width: var(--skopos-sidebar-expanded-width, 17rem);
  }}
  section[data-testid="stSidebar"] {{
    z-index: 999993 !important;
  }}
  /* No Streamlit header strip — transparent shell only */
  header[data-testid="stHeader"] {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    overflow: hidden !important;
  }}
  [data-testid="stDecoration"] {{
    display: none !important;
  }}
  /* Never force the Streamlit toolbar over the login gate — it steals clicks
     and shows "Running (_cached_posture…)" on top of the password form. */
  .stApp:has(.skopos-login-page-marker) [data-testid="stToolbar"],
  .stApp:has(.skopos-login-page-marker) [data-testid="stStatusWidget"],
  .stApp:has(.skopos-login-page-marker) [data-testid="stConnectionStatus"] {{
    display: none !important;
    pointer-events: none !important;
  }}
  .stApp:not(:has(.skopos-login-page-marker)) [data-testid="stToolbar"] {{
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    position: fixed !important;
    top: {_TOP_GAP} !important;
    right: 1rem !important;
    left: auto !important;
    height: auto !important;
    width: auto !important;
    max-width: 14rem !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    z-index: 999992 !important;
    pointer-events: auto !important;
  }}
  [data-testid="stToolbarActions"],
  [data-testid="stToolbarAppName"],
  [data-testid="stMainMenu"],
  #MainMenu {{
    display: none !important;
  }}
  /* Sit the Running… pill a bit lower so it never covers the bottom border of
     the Period/Filters card when Streamlit parks the status under that block. */
  [data-testid="stStatusWidget"],
  [data-testid="stConnectionStatus"] {{
    background: {link_bg} !important;
    color: {th.text} !important;
    border: 1px solid {link_border} !important;
    border-radius: 999px !important;
    padding: 0.12rem 0.45rem !important;
    font-size: 0.72rem !important;
    line-height: 1.2 !important;
    backdrop-filter: blur(14px) saturate(1.1) !important;
    -webkit-backdrop-filter: blur(14px) saturate(1.1) !important;
    box-shadow: {link_shadow} !important;
    max-width: 100% !important;
    margin-top: 0.85rem !important;
    transform: translateY(6px) !important;
  }}
  /* Extra air under bordered toolbars (Period + Filters) so the loader clears the frame. */
  section.main [data-testid="stVerticalBlockBorderWrapper"] {{
    margin-bottom: 0.85rem !important;
    padding-bottom: 0.15rem !important;
  }}
  [data-testid="stStatusWidget"] label,
  [data-testid="stStatusWidget"] span,
  [data-testid="stStatusWidget"] p,
  [data-testid="stStatusWidget"] div,
  [data-testid="stConnectionStatus"] label,
  [data-testid="stConnectionStatus"] span {{
    color: {th.text} !important;
  }}
  [data-testid="stStatusWidget"] button,
  [data-testid="stConnectionStatus"] button {{
    background: transparent !important;
    color: {th.text_muted} !important;
    border-color: {link_border} !important;
  }}
  .skopos-topbar {{
    position: fixed;
    top: {_TOP_GAP};
    left: var(--sidebar-width, 17rem);
    right: calc(4.75rem + env(safe-area-inset-right, 0px));
    min-height: var(--skopos-header-height);
    z-index: 999991;
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
    box-sizing: border-box;
    padding: 0 0.5rem;
    pointer-events: none;
    background: transparent;
    overflow: visible;
  }}
  .skopos-topbar-nav {{
    display: flex;
    flex: 1 1 auto;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    align-content: center;
    justify-content: flex-start;
    gap: 0.35rem;
    min-width: 0;
    max-width: 100%;
    pointer-events: auto;
  }}
  .skopos-topbar-link {{
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    gap: 0.28rem;
    padding: 0.32rem 0.72rem;
    border-radius: 999px;
    font-family: 'Outfit', system-ui, sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-decoration: none !important;
    color: {th.text} !important;
    border: 1px solid {link_border};
    background: {link_bg};
    backdrop-filter: blur(14px) saturate(1.1);
    -webkit-backdrop-filter: blur(14px) saturate(1.1);
    box-shadow: {link_shadow};
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease, box-shadow 0.22s ease, transform 0.15s ease;
    white-space: nowrap;
    min-width: 0;
    max-width: 100%;
  }}
  .skopos-topbar-link:hover {{
    color: {th.accent} !important;
    border-color: color-mix(in srgb, {th.accent} 55%, transparent);
    background: color-mix(in srgb, {th.accent} 14%, {link_bg});
    box-shadow: {link_hover_shadow};
    transform: translateY(-1px);
  }}
  .skopos-topbar-link.is-active {{
    color: {th.accent} !important;
    border-color: color-mix(in srgb, {th.accent} 65%, transparent);
    background: color-mix(in srgb, {th.accent} 18%, {link_bg});
    box-shadow: 0 0 24px color-mix(in srgb, {th.accent} 35%, transparent), {link_shadow};
  }}
  .skopos-topbar-link .material-symbols-outlined {{
    font-size: 0.95rem;
    line-height: 1;
    flex: 0 0 auto;
  }}
  .skopos-topbar-link .label {{
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 10rem;
  }}
  [data-testid="stAppViewContainer"] > section.main {{
    padding-top: calc({_TOP_GAP} + var(--skopos-header-height) + {_TOP_GAP}) !important;
  }}
  @media (max-width: 1100px) {{
    .skopos-topbar {{
      right: calc(3.75rem + env(safe-area-inset-right, 0px));
    }}
    .skopos-topbar-link .label {{ display: none !important; }}
    .skopos-topbar-link {{
      padding: 0.38rem 0.48rem;
      min-width: 2.15rem;
    }}
  }}
  @media (max-width: 768px) {{
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapseButton"] {{
      display: none !important;
    }}
    .skopos-topbar {{
      left: 0;
      right: calc(3.25rem + env(safe-area-inset-right, 0px));
      padding: 0 0.35rem 0 0.35rem;
      gap: 0.35rem;
    }}
    [data-testid="stToolbar"] {{
      right: 0.35rem !important;
      max-width: 6.5rem !important;
    }}
    .skopos-topbar-link {{
      padding: 0.38rem 0.45rem;
      min-width: 2.05rem;
    }}
    .skopos-mobile-menu-btn {{
      display: inline-flex !important;
    }}
  }}
  .skopos-mobile-menu-btn {{
    display: none;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    width: 2.35rem;
    height: 2.35rem;
    margin-right: 0.15rem;
    padding: 0;
    border-radius: 999px;
    border: 1px solid {link_border};
    background: {link_bg};
    color: {th.text};
    box-shadow: {link_shadow};
    backdrop-filter: blur(14px) saturate(1.1);
    -webkit-backdrop-filter: blur(14px) saturate(1.1);
    cursor: pointer;
    pointer-events: auto;
    transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease, box-shadow 0.22s ease, transform 0.15s ease;
  }}
  .skopos-mobile-menu-btn:hover {{
    color: {th.accent};
    border-color: color-mix(in srgb, {th.accent} 55%, transparent);
    background: color-mix(in srgb, {th.accent} 14%, {link_bg});
    box-shadow: {link_hover_shadow};
    transform: translateY(-1px);
  }}
  .skopos-mobile-menu-btn.is-open {{
    color: {th.accent};
    border-color: color-mix(in srgb, {th.accent} 65%, transparent);
    background: color-mix(in srgb, {th.accent} 18%, {link_bg});
  }}
  .skopos-mobile-menu-btn .material-symbols-outlined {{
    font-size: 1.2rem;
    line-height: 1;
  }}
  @media (max-width: 768px) {{
    /* Always a full drawer on mobile — never the collapsed icon rail.
       Geometry uses the PLAIN selector only (specificity 0,1,1). The desktop
       collapsed/expanded html classes are deliberately NOT qualified here: if
       they were, the closed transform would tie the open rule's specificity
       (both 0,2,2) and, since `skopos-sidebar-expanded` is always present, the
       drawer would flicker open/closed depending on stylesheet source order.
       Keeping the closed state at 0,1,1 lets the open rule (0,2,2) win cleanly. */
    /* Geometry lives on the SECTION only. Previously it was also applied to the
       inner `> div`, which had two nasty effects in some themes (esp. premium):
       (1) a SECOND position:fixed layer with the sidebar's opaque background sat
       ON TOP of the nav and covered it — the drawer looked empty; and
       (2) transforms on both nested elements COMPOUNDED (~-210% instead of -105%).
       The content div now stays in normal flow and simply fills the fixed section. */
    section[data-testid="stSidebar"] {{
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      height: 100vh !important;
      height: 100dvh !important;
      width: min(85vw, 17rem) !important;
      min-width: min(85vw, 17rem) !important;
      max-width: min(85vw, 17rem) !important;
      z-index: 999993 !important;
      box-shadow: 4px 0 32px rgba(0, 0, 0, 0.35) !important;
      transform: translateX(-105%) !important;
      /* NO transform transition on the drawer. Streamlit re-renders the sidebar
         node continuously (esp. under the premium chrome's observers), which
         perpetually RESTARTS a transform transition — getComputedStyle then keeps
         returning the mid-flight (near-closed) value and the open rule never
         visually wins, so the drawer opens EMPTY / off-screen. Snapping open/closed
         (no transition) makes the open state apply instantly and reliably; the
         backdrop fade below still gives a sense of motion. */
      transition: none !important;
      pointer-events: none !important;
      visibility: hidden !important;
      padding-left: 0 !important;
      padding-right: 0 !important;
      overflow-y: auto !important;
    }}
    /* Inner content container: normal flow, no own fixed/transform layer. */
    section[data-testid="stSidebar"] > div {{
      position: static !important;
      transform: none !important;
      width: 100% !important;
      min-width: 0 !important;
      max-width: none !important;
      height: auto !important;
    }}
    html.skopos-mobile-sidebar-open section[data-testid="stSidebar"] {{
      transform: translateX(0) !important;
      pointer-events: auto !important;
      visibility: visible !important;
    }}
    /* Expand labels inside the drawer even if collapsed class stuck. */
    html.skopos-mobile-sidebar-open section[data-testid="stSidebar"] [data-testid="stPageLink"] p,
    html.skopos-mobile-sidebar-open section[data-testid="stSidebar"] [data-testid="stPageLink"] a > span {{
      display: inline !important;
    }}
    html.skopos-mobile-sidebar-open body {{
      overflow: hidden !important;
    }}
    .skopos-mobile-sidebar-backdrop {{
      display: none;
      position: fixed;
      inset: 0;
      z-index: 999992;
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(2px);
      -webkit-backdrop-filter: blur(2px);
      pointer-events: auto;
    }}
    html.skopos-mobile-sidebar-open .skopos-mobile-sidebar-backdrop {{
      display: block;
    }}
  }}
</style>
"""


_TOPBAR_JS_BODY = """
(function () {
  var root, doc;
  try { root = window.parent || window; doc = root.document; } catch (e) { return; }
  if (!doc || !doc.body) return;

  function isMobile() {
    if (root.matchMedia("(max-width: 768px)").matches) return true;
    // Burger only renders on mobile CSS — if it is visible, treat as mobile.
    var btn = doc.querySelector(".skopos-mobile-menu-btn");
    if (!btn) return false;
    try { return root.getComputedStyle(btn).display !== "none"; } catch (e) { return false; }
  }
  function normPath(p) {
    if (!p) return "/";
    var u = p.split("?")[0].split("#")[0];
    if (!u.startsWith("/")) u = "/" + u;
    return u.replace(/\\/+$/, "") || "/";
  }
  function findSidebarToggle() {
    return (
      doc.querySelector('[data-testid="collapsedControl"] button') ||
      doc.querySelector('[data-testid="collapsedControl"]') ||
      doc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
      doc.querySelector('[data-testid="stSidebarCollapseButton"]')
    );
  }
  function sidebarIsOpen() {
    return doc.documentElement.classList.contains("skopos-mobile-sidebar-open");
  }
  function ensureBackdrop() {
    var backdrop = doc.querySelector(".skopos-mobile-sidebar-backdrop");
    if (!backdrop) {
      backdrop = doc.createElement("div");
      backdrop.className = "skopos-mobile-sidebar-backdrop";
      backdrop.setAttribute("aria-hidden", "true");
      backdrop.addEventListener("click", function () {
        setMobileSidebarOpen(false);
      });
      doc.body.appendChild(backdrop);
    }
    return backdrop;
  }
  function syncMobileMenuState() {
    var html = doc.documentElement;
    var open = sidebarIsOpen();
    if (isMobile()) {
      html.classList.remove("skopos-sidebar-collapsed");
      ensureBackdrop();
    } else {
      html.classList.remove("skopos-mobile-sidebar-open");
      doc.body.style.overflow = "";
      open = false;
    }
    doc.querySelectorAll(".skopos-mobile-menu-btn").forEach(function (btn) {
      // Idempotent writes only. `icon.textContent =` replaces a child text node
      // and fires a childList mutation every time — writing it unconditionally
      // here (this runs inside the body MutationObserver) is a self-triggering
      // feedback loop that pegs the main thread. Write only on a real change.
      btn.classList.toggle("is-open", open);
      var expanded = open ? "true" : "false";
      if (btn.getAttribute("aria-expanded") !== expanded) {
        btn.setAttribute("aria-expanded", expanded);
      }
      var openLabel = btn.getAttribute("data-open-label") || "Open menu";
      var closeLabel = btn.getAttribute("data-close-label") || "Close menu";
      var wantLabel = open ? closeLabel : openLabel;
      if (btn.getAttribute("aria-label") !== wantLabel) {
        btn.setAttribute("aria-label", wantLabel);
      }
      var icon = btn.querySelector(".material-symbols-outlined");
      var wantIcon = open ? "close" : "menu";
      if (icon && icon.textContent !== wantIcon) icon.textContent = wantIcon;
    });
  }
  function setMobileSidebarOpen(open) {
    var html = doc.documentElement;
    html.classList.toggle("skopos-mobile-sidebar-open", !!open);
    if (open) {
      html.classList.remove("skopos-sidebar-collapsed");
      html.classList.add("skopos-sidebar-expanded");
    }
    doc.body.style.overflow = open ? "hidden" : "";
    syncMobileMenuState();
  }
  function toggleMobileSidebar() {
    // Always toggle the CSS drawer when the burger is in play.
    if (isMobile()) {
      setMobileSidebarOpen(!sidebarIsOpen());
      return;
    }
    var btn = findSidebarToggle();
    if (btn) btn.click();
    setTimeout(syncMobileMenuState, 80);
  }
  // Public API for inline onclick fallback (survives Streamlit re-renders).
  root.toggleSkoposMobileMenu = function (ev) {
    if (ev) { try { ev.preventDefault(); ev.stopPropagation(); } catch (e) {} }
    toggleMobileSidebar();
    return false;
  };

  function syncSidebarInset() {
    var sb = doc.querySelector('section[data-testid="stSidebar"]');
    var html = doc.documentElement;
    if (!sb) return;
    if (isMobile()) {
      html.style.setProperty("--sidebar-width", "0px");
      html.classList.remove("skopos-sidebar-collapsed");
      syncMobileMenuState();
      return;
    }
    var w = sb.getBoundingClientRect().width;
    if (w > 32) {
      html.style.setProperty("--sidebar-width", w + "px");
      return;
    }
    if (html.classList.contains("skopos-sidebar-collapsed")) {
      html.style.setProperty(
        "--sidebar-width",
        root.getComputedStyle(html).getPropertyValue("--skopos-sidebar-collapsed-width") || "4rem"
      );
    }
  }
  function topbarNavigate(targetPath, e) {
    var norm = normPath(targetPath);
    var slug = norm.split("/").pop();
    var sidebarLinks = doc.querySelectorAll(
      'section[data-testid="stSidebar"] [data-testid="stPageLink"] a'
    );
    for (var i = 0; i < sidebarLinks.length; i += 1) {
      var href = normPath(sidebarLinks[i].getAttribute("href") || "");
      var hrefSlug = href.split("/").pop();
      if (
        href === norm ||
        (norm !== "/" && href.endsWith(norm)) ||
        (slug && hrefSlug && slug === hrefSlug)
      ) {
        if (e) e.preventDefault();
        sidebarLinks[i].click();
        if (isMobile()) {
          setTimeout(function () { setMobileSidebarOpen(false); }, 120);
        }
        return true;
      }
    }
    return false;
  }
  // Agent widget + other overlays navigate the same way as the topbar.
  root.skoposNavigate = function (pageKey, tabKey) {
    try {
      if (tabKey) root.sessionStorage.setItem("skoposDesiredTab", String(tabKey));
    } catch (err) {}
    var key = String(pageKey || "").toLowerCase();
    var underApp = false;
    try { underApp = (root.location.pathname || "").indexOf("/app") === 0; } catch (e0) {}
    if (key === "analytics" || key === "dashboard") {
      return topbarNavigate(underApp ? "/app/" : "/", null);
    }
    var slugByPage = {
      security: "Security",
      observability: "Observability",
      fleet: "Fleet",
      settings: "Settings",
      history: "Scan_History",
      scan_history: "Scan_History",
      docs: "Documentation",
      documentation: "Documentation",
      quick_start: "Quick_Start",
      wizard: "Quick_Start"
    };
    var slug = slugByPage[key];
    if (!slug) return false;
    var target = underApp ? ("/app/" + slug) : ("/" + slug);
    return topbarNavigate(target, null);
  };
  function wireTopbarLinks() {
    doc.querySelectorAll(".skopos-topbar-link").forEach(function (a) {
      if (a.dataset.skoposWired === "1") return;
      a.dataset.skoposWired = "1";
      a.addEventListener("click", function (e) {
        topbarNavigate(a.getAttribute("href") || "", e);
      });
    });
  }
  var __observer = null;
  var __scheduled = false;
  function dedupeTopbars() {
    // Detach the observer while WE mutate the DOM (dedupe/backdrop/labels),
    // then re-attach — so our own writes never re-trigger the observer. Combined
    // with the idempotent writes above, this makes a feedback loop impossible.
    if (__observer) __observer.disconnect();
    try {
      var bars = doc.querySelectorAll(".skopos-topbar");
      for (var i = 0; i < bars.length - 1; i += 1) {
        bars[i].remove();
      }
      syncSidebarInset();
      wireTopbarLinks();
      syncMobileMenuState();
    } finally {
      if (__observer) __observer.observe(doc.body, { childList: true, subtree: true });
    }
  }
  function scheduleDedupe() {
    // Coalesce bursts of Streamlit DOM churn into one pass per frame.
    if (__scheduled) return;
    __scheduled = true;
    var raf = root.requestAnimationFrame || function (f) { return root.setTimeout(f, 16); };
    raf(function () { __scheduled = false; dedupeTopbars(); });
  }

  // Event delegation — survives Streamlit replacing the burger DOM node.
  if (!root.__skoposTopbarClickBound) {
    root.__skoposTopbarClickBound = true;
    doc.addEventListener(
      "click",
      function (e) {
        var t = e.target;
        if (!t || !t.closest) return;
        var btn = t.closest(".skopos-mobile-menu-btn");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        toggleMobileSidebar();
      },
      true
    );
  }

  if (!root.__skoposTopbarReady) {
    root.__skoposTopbarReady = true;
    __observer = new MutationObserver(scheduleDedupe);
    __observer.observe(doc.body, { childList: true, subtree: true });
    root.addEventListener("resize", function () {
      if (!isMobile()) {
        doc.documentElement.classList.remove("skopos-mobile-sidebar-open");
        doc.body.style.overflow = "";
      }
      syncSidebarInset();
      syncMobileMenuState();
    });
  }
  dedupeTopbars();
})();
"""


def build_topbar_js() -> str:
    return f'<script id="skopos-topbar-dedupe">{_TOPBAR_JS_BODY}</script>'


def inject_topbar_js() -> None:
    """Run topbar wiring in the parent document (Streamlit iframe-safe)."""
    import streamlit.components.v1 as components

    components.html(f"<script>{_TOPBAR_JS_BODY}</script>", height=0, width=0)


def render_topbar(*, locale: str, active: str | None = None) -> None:
    """Render fixed header links (docs, quick start, settings)."""
    links = (
        ("documentation", "pages/4_Documentation.py", "app.documentation", "menu_book"),
        ("quick_start", "pages/0_Quick_Start.py", "app.quick_start", "rocket_launch"),
        ("settings", "pages/2_Settings.py", "app.topbar_settings", "settings"),
    )
    open_menu = html.escape(t("app.open_menu", locale))
    close_menu = html.escape(t("app.close_menu", locale))
    parts = [
        '<div class="skopos-topbar" role="navigation" aria-label="SKOPOS">',
        '<button type="button" class="skopos-mobile-menu-btn" aria-expanded="false" '
        f'aria-label="{open_menu}" data-open-label="{open_menu}" data-close-label="{close_menu}" '
        'onclick="return (window.toggleSkoposMobileMenu||function(){var h=document.documentElement;h.classList.toggle(\'skopos-mobile-sidebar-open\');h.classList.remove(\'skopos-sidebar-collapsed\');return false;})(event)">'
        '<span class="material-symbols-outlined" aria-hidden="true">menu</span>'
        "</button>",
        '<nav class="skopos-topbar-nav">',
    ]
    for slug, path, key, icon in links:
        href = _page_href(path)
        label = html.escape(t(key, locale))
        active_cls = " is-active" if active == slug else ""
        parts.append(
            f'<a class="skopos-topbar-link{active_cls}" href="{html.escape(href, quote=True)}" '
            f'title="{label}" aria-label="{label}">'
            f'<span class="material-symbols-outlined" aria-hidden="true">{icon}</span>'
            f'<span class="label">{label}</span></a>'
        )
    parts.append("</nav></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    inject_topbar_js()
