from decimal import Decimal
from .utils import dec, amt

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

    commission_tracker = {"value": Decimal("0")}

    for activity in activities:
        activity_type = activity.get("type", "")

        if activity_type == "ACTIVITY_TYPE_TRADE":
            row = process_trade(activity, positions, commission_tracker)
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

    return rows, commission_tracker["value"]


def _activity_time(activity):
    trade = activity.get("trade") or {}
    resolution = activity.get("positionResolution") or {}
    return trade.get("createTime") or resolution.get("updateTime") or ""


def process_trade(activity, positions, commission_tracker):
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

    commission_tracker["value"] += commission

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