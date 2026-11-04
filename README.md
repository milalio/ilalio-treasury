# The Ilalio Treasury

A trimmed, public view of the household budget, refreshed every morning from Copilot Money.

- `index.html` — the site (reads `data.json`).
- `build_data.py` — turns raw Copilot answers in `raw/` into `data.json`. Raw files are never committed.
- `data.json` — the published numbers: budgets and spending by category, monthly income and spending,
  a net worth trend and recurring totals. No accounts, card numbers, addresses, transactions, merchants or notes.

Published with GitHub Pages from the `main` branch, root folder.
