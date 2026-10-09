This is a visualization tool for your Polymarket portfolio.

## Legacy Utilities

The `legacy/` directory contains standalone scripts for exporting historical
portfolio data from the Polymarket API. These utilities are separate from the
current visualization application.

### Requirements

- Python 3.10+
- A Polymarket API client that provides `polymarket_us.PolymarketUS`
- `openpyxl` for the trade P&L export

Install the Python package used by the trade export with:

```bash
pip install openpyxl
```

Create `Secret.txt` in the repository root. It must contain the credentials
used by both scripts:

```text
POLYMARKET_KEY_ID=your-key-id
POLYMARKET_SECRET_KEY=your-secret-key
```

Keep this file private. 

### Run the Trade P&L Export

Run the script from the `legacy/` directory so its relative paths resolve
correctly:

```bash
cd legacy
python polymarket_trades_pnl.py
```

The script retrieves trade and position-resolution activities, calculates
realized P&L using average-cost tracking, includes still-open positions, and
writes the formatted report to:

```text
legacy/polymarket_trades_pnl.xlsx
```

The workbook includes profit, loss, net P&L, commissions, entry and exit
prices, position status, and notes for unmatched or unresolved activity.

### Run the Withdrawal Export

From the `legacy/` directory, run:

```bash
python polymarket_withdrawals.py
```

The script retrieves account withdrawal activities, merges them with the
existing `legacy/polymarket_withdrawals.csv` by transaction ID, sorts entries
newest first, and rewrites the CSV. It also prints total, completed, and
pending withdrawal amounts.

These scripts call the Polymarket API and may update existing output files.
Run them only when fresh API data is needed.

