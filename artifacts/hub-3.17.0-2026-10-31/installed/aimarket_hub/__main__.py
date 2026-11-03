"""Entry point for ``python -m aimarket_hub``."""
from aimarket_hub.cli import main

# The exit status is the command's answer (`doctor` is 1 unless the assay passes); a bare
# `main()` threw it away and `python -m aimarket_hub` always exited 0.
raise SystemExit(main())
