"""Sidebar navigation chrome — active page detection (GA-style)."""


def build_nav_chrome_js() -> str:
    return """
<script id="skopos-nav-chrome">
(function () {
  if (window.__skoposNavReady) return;
  window.__skoposNavReady = true;

  function normPath(p) {
    if (!p) return "/";
    var u = p.split("?")[0].split("#")[0];
    if (!u.startsWith("/")) u = "/" + u;
    return u.replace(/\\/+$/, "") || "/";
  }

  function markActiveNav() {
    var path = normPath(window.location.pathname);
    document.querySelectorAll(
      'section[data-testid="stSidebar"] [data-testid="stPageLink"] a'
    ).forEach(function (a) {
      var href = normPath(a.getAttribute("href") || "");
      var active =
        path === href ||
        (href !== "/" && path.endsWith(href)) ||
        (path === "/" && (href === "/" || href.indexOf("dashboard") >= 0));
      a.classList.toggle("skopos-nav-active", active);
    });
  }

  markActiveNav();
  new MutationObserver(markActiveNav).observe(document.body, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("popstate", markActiveNav);
})();
</script>
"""
