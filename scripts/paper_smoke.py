#!/usr/bin/env python3
"""Alpaca paper round-trip smoke test.

Validates live connectivity to the Alpaca **paper** API with the keys in `.env`:
connect → read account → place a tiny market order → read it back → clean up
(flatten if filled, cancel if still open). Paper trading is simulated; no real
money or securities are involved.

Usage:
    python scripts/paper_smoke.py [--symbol AAPL] [--qty 1]
"""
import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--qty", type=float, default=1)
    args = ap.parse_args()

    from utils.alpaca_util import AlpacaAPI

    api = AlpacaAPI(paper=True)
    print(f"== Alpaca paper round-trip smoke ({api.base_url}) ==")

    acct = api.get_account()
    status = acct.get("status") or acct.get("account_status")
    print(f"account: status={status} buying_power={acct.get('buying_power')} "
          f"cash={acct.get('cash')} equity={acct.get('equity')}")
    if not acct:
        print("FAIL: could not read account")
        return 1

    print(f"placing market BUY {args.qty} {args.symbol} ...")
    order = api.create_order(symbol=args.symbol, qty=args.qty, side="buy",
                             type="market", time_in_force="day")
    oid = order.get("id") or order.get("order_id")
    print(f"order accepted: id={oid} status={order.get('status')}")
    if not oid:
        print("FAIL: order not accepted")
        return 1

    # read it back (poll briefly for a terminal/known state)
    final = order
    for _ in range(5):
        time.sleep(1)
        final = api.get_order(oid)
        if final.get("status") in ("filled", "accepted", "new", "pending_new", "canceled"):
            break
    ostatus = final.get("status")
    print(f"readback: id={oid} status={ostatus} filled_qty={final.get('filled_qty')} "
          f"filled_avg_price={final.get('filled_avg_price')}")

    # cleanup
    if ostatus == "filled":
        print(f"flattening position {args.symbol} ...")
        api.close_position(args.symbol)
        print("flattened (paper).")
    else:
        print(f"market likely closed; canceling open order {oid} ...")
        try:
            api.cancel_order(oid)
            print("canceled.")
        except Exception as e:  # noqa: BLE001
            print(f"cancel note: {e}")

    print("PASS: paper round-trip completed (connect → order → readback → cleanup).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
