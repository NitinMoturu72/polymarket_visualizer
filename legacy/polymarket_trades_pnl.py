import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from polymarket_us import PolymarketUS

XLSX_FILE = "polymarket_trades_pnl.xlsx"
SECRETS_FILE = "../Secret.txt"


def load_secrets():
    """Load API credentials from secrets.txt."""

    secrets = {}

    with open(SECRETS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                secrets[key.strip()] = value.strip()

    return secrets


secrets = load_secrets()

client = PolymarketUS(
    key_id=secrets["POLYMARKET_KEY_ID"],
    secret_key=secrets["POLYMARKET_SECRET_KEY"],
)


def format_time(timestamp):
    """Convert API timestamp to local readable time."""

    if not timestamp:
        return ""

    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %I:%M:%S %p")
    except Exception:
        return timestamp


def dec(value, default="0"):
    """Safely parse an Amount-style value into a Decimal."""

    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def amt(amount_obj):
    """Pull the decimal value out of an {"value": "...", "currency": "USD"} dict."""

    if not amount_obj:
        return Decimal("0")
    return dec(amount_obj.get("value"))


TOTAL_COMMISSION = {"value": Decimal("0")}


def fetch_all_activities(client):
    """Page through every TRADE and POSITION_RESOLUTION activity."""

    activities = []
    cursor = ""

    while True:
        params = {
            "limit": 100,
            "types": ["ACTIVITY_TYPE_TRADE", "ACTIVITY_TYPE_POSITION_RESOLUTION"],
        }

        if cursor:
            params["cursor"] = cursor

        response = client.portfolio.activities(params)
        batch = response.get("activities", [])
        activities.extend(batch)

        if response.get("eof", True) or not response.get("nextCursor"):
            break

        cursor = response["nextCursor"]

    return activities


def my_side_of_trade(trade):
    """Return the order/execution belonging to this account for a Trade."""

    if trade.get("isAggressor"):
        execution = trade.get("aggressorExecution") or {}
    else:
        execution = trade.get("passiveExecution") or {}

    order = execution.get("order") or {}
    return order, execution


def effective_price(price_value, outcome_side):
    """
    Polymarket prices a market's order book on the YES/long side. If this
    fill was on the NO/short side, the price actually paid for that side
    is the complement (1 - price).
    """

    price = dec(price_value)

    if outcome_side == "OUTCOME_SIDE_NO":
        return Decimal("1") - price

    return price


class Position:
    """
    Running average-cost tracker for one (market, outcome, outcomeSide)
    instrument, spanning from when it's first opened (flat -> nonzero)
    to when it's fully closed back to flat.
    """

    def __init__(self):
        self.qty = Decimal("0")
        self.cost_basis = Decimal("0")
        self.opened_at = None
        self.market = ""
        self.outcome = ""
        self.side_label = ""

    @property
    def avg_price(self):
        if self.qty == 0:
            return Decimal("0")
        return self.cost_basis / self.qty


def build_rows(activities):
    """
    Walk activities in chronological order, maintaining an average-cost
    position per (marketSlug, outcome, outcomeSide). Emit ONE row per
    completed round trip (entry price -> exit price), not one row per
    fill - an opening buy by itself realizes nothing, so it's folded
    into whichever close/resolution/cashout event eventually ends it.

    - A BUY/opening trade adds to the position; no row is emitted yet.
    - A SELL/closing trade (including a partial "cashout") realizes
      (proceeds - matched average cost - commission) on the portion
      closed, and is emitted as a row pairing that average entry price
      with this exit price.
    - A POSITION_RESOLUTION (holding to settlement) uses Polymarket's
      own authoritative realized-P&L delta (afterPosition.realized -
      beforePosition.realized), paired with the entry price the API
      reports for that position, then resets local tracking to zero.
    - Anything still open at the end gets a single "Still Open" row
      (unrealized, uncolored) so nothing silently disappears.
    """

    activities = sorted(activities, key=lambda a: _activity_time(a))

    positions = {}
    rows = []

    for activity in activities:
        activity_type = activity.get("type", "")

        if activity_type == "ACTIVITY_TYPE_TRADE":
            row = process_trade(activity, positions)
        elif activity_type == "ACTIVITY_TYPE_POSITION_RESOLUTION":
            row = process_resolution(activity, positions)
        else:
            continue

        if row:
            rows.append(row)

    for position in positions.values():
        if position.qty != 0:
            rows.append({
                "opened": position.opened_at,
                "closed": None,
                "status": "Still Open",
                "market": position.market,
                "outcome": position.outcome,
                "side": position.side_label,
                "qty": abs(position.qty),
                "entry_price": position.avg_price,
                "exit_price": None,
                "commission": Decimal("0"),
                "realized_pnl": Decimal("0"),
                "note": "Position still open as of this report - not yet realized",
            })

    return rows


def _activity_time(activity):
    trade = activity.get("trade") or {}
    resolution = activity.get("positionResolution") or {}
    return trade.get("createTime") or resolution.get("updateTime") or ""


def process_trade(activity, positions):
    trade = activity.get("trade") or {}
    order, execution = my_side_of_trade(trade)

    if not order:
        return None

    market_slug = trade.get("marketSlug", "")
    metadata = order.get("marketMetadata") or {}
    outcome = metadata.get("outcome", "")
    outcome_side = order.get("outcomeSide", "")
    side_label = "YES" if outcome_side == "OUTCOME_SIDE_YES" else ("NO" if outcome_side == "OUTCOME_SIDE_NO" else outcome_side)
    action = order.get("action", "")
    qty = dec(trade.get("qtyDecimal") or trade.get("qty"))
    price = effective_price((trade.get("price") or {}).get("value"), outcome_side)
    commission = amt(execution.get("commissionNotionalCollected"))
    date = trade.get("createTime", "")

    TOTAL_COMMISSION["value"] += commission

    key = (market_slug, outcome, outcome_side)
    position = positions.setdefault(key, Position())
    position.market = metadata.get("title") or market_slug
    position.outcome = outcome
    position.side_label = side_label

    combo_note = "Combo trade - legs not individually tracked" if trade.get("comboLegDetails") else ""

    if action == "ORDER_ACTION_BUY":
        if position.qty == 0:
            position.opened_at = date

        position.qty += qty
        position.cost_basis += (price * qty) + commission

        if combo_note:
            # A combo open can't be reliably paired with a later close,
            # so surface it as its own standalone row instead of silently
            # folding it into cost basis.
            return {
                "opened": date,
                "closed": None,
                "status": "Open (Combo)",
                "market": position.market,
                "outcome": outcome,
                "side": side_label,
                "qty": qty,
                "entry_price": price,
                "exit_price": None,
                "commission": commission,
                "realized_pnl": Decimal("0"),
                "note": combo_note,
            }

        return None

    elif action == "ORDER_ACTION_SELL":
        if position.qty <= 0:
            return {
                "opened": None,
                "closed": date,
                "status": "Unmatched Sell",
                "market": position.market,
                "outcome": outcome,
                "side": side_label,
                "qty": qty,
                "entry_price": None,
                "exit_price": price,
                "commission": commission,
                "realized_pnl": Decimal("0"),
                "note": "No tracked open position for this instrument (history may predate tracking) - P&L not computed",
            }

        qty_closed = min(qty, position.qty)
        note = combo_note

        if qty_closed < qty:
            note = (note + " | " if note else "") + "Sold more than tracked open qty; P&L only reflects the matched portion"

        entry_price = position.avg_price
        cost_removed = entry_price * qty_closed
        proceeds = price * qty_closed
        realized_pnl = proceeds - cost_removed - commission

        opened_at = position.opened_at

        position.qty -= qty_closed
        position.cost_basis -= cost_removed

        status = "Closed" if position.qty == 0 else "Partially Closed"

        if position.qty == 0:
            position.opened_at = None

        return {
            "opened": opened_at,
            "closed": date,
            "status": status,
            "market": position.market,
            "outcome": outcome,
            "side": side_label,
            "qty": qty_closed,
            "entry_price": entry_price,
            "exit_price": price,
            "commission": commission,
            "realized_pnl": realized_pnl,
            "note": note,
        }

    return {
        "opened": None,
        "closed": date,
        "status": "Unrecognized",
        "market": position.market,
        "outcome": outcome,
        "side": side_label,
        "qty": qty,
        "entry_price": None,
        "exit_price": price,
        "commission": commission,
        "realized_pnl": Decimal("0"),
        "note": f"Unrecognized order action '{action}' - not included in P&L",
    }


def process_resolution(activity, positions):
    resolution = activity.get("positionResolution") or {}
    before = resolution.get("beforePosition") or {}
    after = resolution.get("afterPosition") or {}

    market_slug = resolution.get("marketSlug", "")
    metadata = before.get("marketMetadata") or after.get("marketMetadata") or {}
    outcome = metadata.get("outcome", "")
    date = resolution.get("updateTime", "")

    realized_delta = amt(after.get("realized")) - amt(before.get("realized"))

    qty_before = dec(before.get("qtyAvailableDecimal") or before.get("netPositionDecimal"))
    qty_before_abs = abs(qty_before)

    # A per-share settlement price can't be reliably reconstructed from the
    # fields the API exposes here (rounding/short-side sign conventions
    # push it slightly outside the valid $0-$1 range in practice), so it's
    # intentionally left blank rather than show a number that might be
    # wrong. The Realized P&L column below is directly API-reported and
    # trustworthy regardless.
    settle_price = None

    before_avg_px = before.get("avgPx")
    entry_price = amt(before_avg_px) if before_avg_px else None

    note = ""
    tolerance = Decimal("0.05")
    opened_at = None

    # Figure out which of our locally-tracked YES/NO lots this resolution
    # is settling (the resolution's own side label doesn't map cleanly to
    # our order-level outcomeSide), by matching tracked qty magnitude.
    matched_key = None
    for side in ("OUTCOME_SIDE_YES", "OUTCOME_SIDE_NO"):
        key = (market_slug, outcome, side)
        tracked = positions.get(key)
        if tracked and abs(abs(tracked.qty) - qty_before_abs) <= tolerance:
            matched_key = key
            break

    if matched_key:
        opened_at = positions[matched_key].opened_at
        if entry_price is None:
            entry_price = positions[matched_key].avg_price
        positions[matched_key] = Position()
    else:
        note = "Could not match a locally-tracked open lot to this resolution; realized P&L is still the API-reported value, but entry price/date may be incomplete"
        # Clear any stale lots for this outcome regardless, so later
        # trades on the same instrument don't inherit bad state.
        for side in ("OUTCOME_SIDE_YES", "OUTCOME_SIDE_NO"):
            key = (market_slug, outcome, side)
            if key in positions:
                positions[key] = Position()

    return {
        "opened": opened_at,
        "closed": date,
        "status": "Resolved",
        "market": metadata.get("title") or market_slug,
        "outcome": outcome,
        "side": "",
        "qty": qty_before_abs,
        "entry_price": entry_price,
        "exit_price": settle_price,
        "commission": Decimal("0"),
        "realized_pnl": realized_delta,
        "note": note,
    }


def outer_border(ws, min_row, max_row, min_col, max_col, style="thick"):
    """Draw a box border around the outside of a rectangular cell range."""

    thick = Side(style=style)

    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            top = thick if r == min_row else None
            bottom = thick if r == max_row else None
            left = thick if c == min_col else None
            right = thick if c == max_col else None

            if top or bottom or left or right:
                ws.cell(row=r, column=c).border = Border(top=top, bottom=bottom, left=left, right=right)


def add_summary_box(ws, label_row, value_row, min_col, max_col, label, value, fill_color, font_color):
    # Fill, border, and write values BEFORE merging - cells inside a merged
    # range become MergedCell placeholders that don't reliably accept new
    # styling afterward, so styling has to land on each real Cell first.
    fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

    for r in (label_row, value_row):
        for c in range(min_col, max_col + 1):
            ws.cell(row=r, column=c).fill = fill

    outer_border(ws, label_row, value_row, min_col, max_col)

    label_cell = ws.cell(row=label_row, column=min_col, value=label)
    label_cell.font = Font(bold=True, size=11)
    label_cell.alignment = Alignment(horizontal="center")

    value_cell = ws.cell(row=value_row, column=min_col, value=float(value))
    value_cell.number_format = "$#,##0.00"
    value_cell.font = Font(bold=True, size=16, color=font_color)
    value_cell.alignment = Alignment(horizontal="center")

    ws.merge_cells(start_row=label_row, start_column=min_col, end_row=label_row, end_column=max_col)
    ws.merge_cells(start_row=value_row, start_column=min_col, end_row=value_row, end_column=max_col)


def write_xlsx(rows):
    """Write all rows to a colored .xlsx, newest-closed first, with a
    boxed Total Profit / Total Loss / Net summary above the table."""

    rows = sorted(rows, key=lambda r: r["closed"] or r["opened"] or "", reverse=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Trade P&L"

    headers = [
        "Opened",
        "Closed",
        "Status",
        "Market",
        "Outcome",
        "Side",
        "Qty",
        "Entry Price",
        "Entry Cost",
        "Exit Price",
        "Exit Cost",
        "Commission",
        "Realized P&L",
        "Note",
    ]

    num_cols = len(headers)

    # ---------------------------------------------------------
    # Summary box: Total Profit | Total Loss | Net, rows 1-3
    # ---------------------------------------------------------

    total_profit = sum((r["realized_pnl"] for r in rows if r["realized_pnl"] > 0), Decimal("0"))
    total_loss = sum((r["realized_pnl"] for r in rows if r["realized_pnl"] < 0), Decimal("0"))
    net_pnl = total_profit + total_loss

    title_cell = ws.cell(row=1, column=1, value="Polymarket Trade P&L Summary")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
    title_cell.font = Font(bold=True, size=14)
    title_cell.alignment = Alignment(horizontal="center")

    box_width = num_cols // 3
    box1_start, box1_end = 1, box_width
    box2_start, box2_end = box_width + 1, box_width * 2
    box3_start, box3_end = box_width * 2 + 1, num_cols

    add_summary_box(ws, 2, 3, box1_start, box1_end, "Total Profit", total_profit, "C6EFCE", "006100")
    add_summary_box(ws, 2, 3, box2_start, box2_end, "Total Loss", total_loss, "FFC7CE", "9C0006")
    add_summary_box(
        ws, 2, 3, box3_start, box3_end, "Net P&L", net_pnl,
        "C6EFCE" if net_pnl >= 0 else "FFC7CE",
        "006100" if net_pnl >= 0 else "9C0006",
    )

    header_row = 5
    ws.cell(row=header_row, column=1)  # ensure row exists before freeze/append below

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    ws.freeze_panes = f"A{header_row + 1}"

    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    green_font = Font(color="006100")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    red_font = Font(color="9C0006")

    pnl_col = headers.index("Realized P&L") + 1
    entry_price_col = headers.index("Entry Price") + 1
    entry_cost_col = headers.index("Entry Cost") + 1
    exit_price_col = headers.index("Exit Price") + 1
    exit_cost_col = headers.index("Exit Cost") + 1
    commission_col = headers.index("Commission") + 1

    data_row = header_row + 1

    for row in rows:
        qty = row["qty"]
        entry_price = row["entry_price"]
        exit_price = row["exit_price"]
        entry_cost = qty * entry_price if entry_price is not None else None
        exit_cost = qty * exit_price if exit_price is not None else None

        values = {
            1: format_time(row["opened"]) if row["opened"] else "",
            2: format_time(row["closed"]) if row["closed"] else "",
            3: row["status"],
            4: row["market"],
            5: row["outcome"],
            6: row["side"],
            7: float(qty),
            entry_price_col: float(entry_price) if entry_price is not None else None,
            entry_cost_col: float(entry_cost) if entry_cost is not None else None,
            exit_price_col: float(exit_price) if exit_price is not None else None,
            exit_cost_col: float(exit_cost) if exit_cost is not None else None,
            commission_col: float(row["commission"]),
            pnl_col: float(row["realized_pnl"]),
            headers.index("Note") + 1: row["note"],
        }

        for col in range(1, num_cols + 1):
            ws.cell(row=data_row, column=col, value=values.get(col))

        pnl_cell = ws.cell(row=data_row, column=pnl_col)
        pnl_cell.number_format = "$#,##0.00"

        if row["realized_pnl"] > 0:
            pnl_cell.fill = green_fill
            pnl_cell.font = green_font
        elif row["realized_pnl"] < 0:
            pnl_cell.fill = red_fill
            pnl_cell.font = red_font

        ws.cell(row=data_row, column=entry_price_col).number_format = "$0.0000"
        ws.cell(row=data_row, column=exit_price_col).number_format = "$0.0000"
        ws.cell(row=data_row, column=entry_cost_col).number_format = "$#,##0.00"
        ws.cell(row=data_row, column=exit_cost_col).number_format = "$#,##0.00"
        ws.cell(row=data_row, column=commission_col).number_format = "$#,##0.00"

        data_row += 1

    widths = [20, 20, 16, 32, 14, 6, 10, 11, 11, 11, 11, 11, 14, 55]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    wb.save(XLSX_FILE)


try:
    activities = fetch_all_activities(client)
    rows = build_rows(activities)
    write_xlsx(rows)

    # ---------------------------------------------------------
    # Calculate totals
    # ---------------------------------------------------------

    still_open = [r for r in rows if r["status"] == "Still Open"]
    completed = [r for r in rows if r["status"] != "Still Open"]

    total_pnl = sum((r["realized_pnl"] for r in rows), Decimal("0"))
    wins = [r for r in completed if r["realized_pnl"] > 0]
    losses = [r for r in completed if r["realized_pnl"] < 0]

    print()
    print("========================================")
    print(" Polymarket Trade P&L Report Updated")
    print("========================================")
    print(f"Completed trades:         {len(completed)}")
    print(f"  Wins:                    {len(wins)}")
    print(f"  Losses:                  {len(losses)}")
    print(f"Still open:                {len(still_open)}")
    print(f"Total realized P&L:        ${total_pnl:,.2f}")
    print(f"Total commission paid:     ${TOTAL_COMMISSION['value']:,.2f}")
    print()
    print(f"XLSX: {os.path.abspath(XLSX_FILE)}")
    print()

finally:
    client.close()
