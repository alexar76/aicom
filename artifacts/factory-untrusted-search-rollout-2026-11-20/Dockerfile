# Factory app: the running image (aicom-security:aicom-app-1-audit19-f2ddfa13 = sha256:8c2f6e0a…) with five files of
# aicom 829d6841a: web search results are screened and fenced before the analyst's prompt, and later agents get the
# analyst's report without the raw snippets. agents/architect.py is the running image's own file with the one-line
# change (it differs from the repository only in import order). Nothing else changes.
FROM aicom-security:aicom-app-1-audit19-f2ddfa13
COPY --chown=0:0 --chmod=644 files/agents/analyst.py files/agents/pm.py files/agents/architect.py files/agents/marketing.py /app/agents/
COPY --chown=0:0 --chmod=644 files/core/untrusted_text.py /app/core/untrusted_text.py
LABEL aicom.factory.overlay="untrusted-search-20261120" skopos.source.commit="829d6841a9ff19ac2b0e82fdb4fbfdc93644833f"
