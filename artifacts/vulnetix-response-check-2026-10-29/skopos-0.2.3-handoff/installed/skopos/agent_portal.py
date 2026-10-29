"""Login-screen teardown for the floating agent.

The floating assistant itself is a self-contained overlay (see
:mod:`skopos.agent_widget`) that is only injected on authenticated pages. This
tiny companion script runs on *every* page (including the login gate) and tears
the widget down whenever the login marker is present — so the assistant is never
visible before authentication, even if a previous authenticated session left the
overlay or legacy Streamlit chat nodes in the DOM of the same browser tab.
"""

from __future__ import annotations


def _portal_script() -> str:
    return """
(function () {
  var root, doc;
  try { root = window.parent || window; doc = root.document; } catch (e) { return; }
  if (!doc) return;

  function teardownLegacy() {
    ['skopos-agent-root', 'skopos-agent-fab-overlay'].forEach(function (id) {
      var el = doc.getElementById(id);
      if (el) el.remove();
    });
    doc.querySelectorAll(
      '.skopos-agent-portal, .stats-agent-root, .stats-agent-panel, '
      + '[data-skopos-open="1"], button.skopos-agent-fab'
    ).forEach(function (node) { node.remove(); });
    root.__skoposAgentApplyCfg = null;
    root.__skoposAgentState = null;
  }

  // Auth gate: strip the assistant on the login screen.
  if (doc.querySelector('.skopos-login-page-marker')) {
    teardownLegacy();
    if (root.__skoposAgentTeardown) root.__skoposAgentTeardown();
  }
})();
"""


def build_agent_portal_js() -> str:
    """Legacy markdown hook — prefer inject_agent_portal()."""
    return f'<script id="skopos-agent-portal">{_portal_script()}</script>'


def inject_agent_portal() -> None:
    """Run the login-teardown script in the parent document.

    Streamlit is imported here rather than at module scope: `_portal_script` and
    `build_agent_portal_js` are pure string builders, and the factory's own contract
    test for this overlay could not import them at all without the whole Streamlit
    dependency — which the factory does not install, so that test was permanently red.
    """
    import streamlit.components.v1 as components

    components.html(f"<script>{_portal_script()}</script>", height=0, width=0)
