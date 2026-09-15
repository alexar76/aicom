# SKOPOS v0.1.1

Analytics correctness + performance release. Full period windows are exact (no newest-N sample collapse); dashboard KPIs/charts aggregate in SQL.

## Fixed
- **24h vs 7d charts identical** under high traffic — period filter + full-window load (no 200k newest-row trap)
- **Duplicate «Unique IPs» column** crashing the country summary table (`st.dataframe` / PyArrow)
- Period filter honors selected window for geo / uniqueness charts
- Running… status pill no longer covers the Filters card border

## Changed / perf
- KPIs, country, timeline, heatmap, tops computed via **SQL aggregates** over the full period (same counts, far less Python materialization)
- Bulk analytics load drops global `ORDER BY`; journal keeps ordered LIMIT
- Prefer `ts_utc` range + partial index `(server_name, ts_utc) WHERE log_source LIKE 'file:%'`
- Vectorized hide-service filter; chart path skips fat `referer` / bulk `user_agent` columns

## Install

```bash
pip install -U skopos-fleet==0.1.1
# or
docker pull ghcr.io/alexar76/skopos:v0.1.1
```

Live demo: https://skopos.modelmarket.dev  
Docs: https://alexar76.github.io/skopos/
