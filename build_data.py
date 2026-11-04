#!/usr/bin/env python3
"""Turn raw Copilot Money answers into the trimmed data.json the public site reads.

Inputs (one file each in raw/, as returned by the Copilot Money connector; a file may be
plain JSON, or a list of {"type": "text", "text": ...} blocks, and may carry trailing notes):

  raw/budget_month.json   get-categories-monthly-spent  from=<1st of this month> to=<last day of this month>
  raw/cat_12mo.json       get-categories-monthly-spent  from=<1st of month 11 months ago> to=<last day of this month> includeBudgets=false
  raw/income_12mo.json    get-monthly-income            from=<same 12-month range>
  raw/networth.json       get-networth-history          timeFrame=ONE_YEAR
  raw/recurrings.json     get-recurrings                state=ACTIVE

What is kept on purpose: budgets and spending by category, monthly income/spending,
a net worth trend, and recurring totals.
What is left out on purpose: accounts and balances, card numbers, loan names/addresses,
individual transactions, merchants, notes, and individual bill names.

Usage: python3 build_data.py [raw_dir] [out_file]
"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path


def load(path):
    text = Path(path).read_text()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = text
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and obj[0].get("type") == "text":
        obj = "".join(b.get("text", "") for b in obj)
    if isinstance(obj, str):
        starts = [i for i in (obj.find("{"), obj.find("[")) if i >= 0]
        if not starts:
            raise ValueError(f"{path}: no JSON found")
        s = min(starts)
        e = obj.rfind("}" if obj[s] == "{" else "]")
        obj = json.loads(obj[s : e + 1])
    return obj


def r2(x):
    return round(float(x or 0), 2)


def main(raw_dir="raw", out_file="data.json"):
    raw = Path(raw_dir)

    # ---- This month's budgets -------------------------------------------------
    b = load(raw / "budget_month.json")
    o = b.get("overallSummary", {})
    month = (o.get("monthlyTotals") or [{}])[-1].get("month") or date.today().strftime("%Y-%m")
    rows = []
    for c in b.get("categories", []):
        s = c.get("summary", {})
        rows.append({
            "name": c["name"],
            "parent": (c.get("parent") or {}).get("name"),
            "budget": r2(s.get("totalBudget")),
            "spent": r2(s.get("totalSpent")),
            "upcoming": r2(s.get("totalLeftToSpendInRecurrings")),
            "left": r2(s.get("totalVariance")),
        })
    groups = []
    for g in [r for r in rows if not r["parent"]]:
        kids = [{k: v for k, v in r.items() if k != "parent"} for r in rows if r["parent"] == g["name"]]
        groups.append({**{k: v for k, v in g.items() if k != "parent"}, "children": kids})
    budget = {
        "total": {
            "budget": r2(o.get("grandTotalBudget")),
            "spent": r2(o.get("grandTotalSpent")),
            "upcoming": r2(o.get("grandTotalLeftToSpendInRecurrings")),
            "left": r2(o.get("grandTotalVariance")),
        },
        "groups": groups,
    }

    # ---- Monthly income, spending and categories ------------------------------
    cat = load(raw / "cat_12mo.json")
    spent_by_month = {m["month"]: r2(m.get("totalSpent")) for m in cat.get("overallSummary", {}).get("monthlyTotals", [])}
    income = load(raw / "income_12mo.json")
    income_by_month = {m["month"]: r2(m.get("total")) for m in income}
    months_list = sorted(set(spent_by_month) | set(income_by_month))[-12:]
    months = [{"month": m, "income": income_by_month.get(m, 0.0), "spent": spent_by_month.get(m, 0.0)} for m in months_list]
    for m in months:
        m["net"] = r2(m["income"] - m["spent"])

    full = months[:-1]
    n = len(full) or 1
    avg = {k: r2(sum(m[k] for m in full) / n) for k in ("income", "spent", "net")}
    avg["months"] = len(full)
    year = months_list[-1][:4] if months_list else str(date.today().year)
    ytd_rows = [m for m in months if m["month"].startswith(year)]
    ytd = {"year": year, **{k: r2(sum(m[k] for m in ytd_rows)) for k in ("income", "spent", "net")}}

    cats = cat.get("categories", [])
    by_month = []
    for m in months_list:
        def spent_in(c):
            for md in c.get("monthlyData", []):
                if md.get("month") == m:
                    return r2(md.get("spent"))
            return 0.0
        gs = []
        for g in [c for c in cats if not c.get("parent")]:
            gv = spent_in(g)
            kids = [{"name": c["name"], "spent": spent_in(c)} for c in cats if (c.get("parent") or {}).get("name") == g["name"]]
            kids = [k for k in kids if k["spent"] != 0]
            if gv != 0 or kids:
                gs.append({"name": g["name"], "spent": gv, "children": kids})
        by_month.append({"month": m, "groups": gs})

    # ---- Net worth trend (weekly points) --------------------------------------
    nw = [p for p in load(raw / "networth.json") if p.get("assets") is not None and p.get("debt") is not None]
    pts = [{"date": str(p["date"])[:10], "net": r2(p["assets"] - p["debt"])} for p in nw]
    weekly = pts[::7]
    if pts and (not weekly or weekly[-1] is not pts[-1]):
        weekly.append(pts[-1])
    networth = {
        "points": weekly,
        "now": pts[-1]["net"] if pts else 0.0,
        "change30": r2(pts[-1]["net"] - pts[max(0, len(pts) - 31)]["net"]) if pts else 0.0,
        "change1y": r2(pts[-1]["net"] - pts[0]["net"]) if pts else 0.0,
    }

    # ---- Recurring totals only ------------------------------------------------
    per_year = {"WEEKLY": 52, "BIWEEKLY": 26, "MONTHLY": 12, "BIMONTHLY": 6, "QUARTERLY": 4, "QUADMONTHLY": 3, "SEMIANNUALLY": 2, "ANNUALLY": 1}
    rec = load(raw / "recurrings.json").get("recurrings", [])
    rec = [r for r in rec if r.get("state", "ACTIVE") == "ACTIVE"]
    monthly = sum(r.get("nextPaymentAmount") or 0 for r in rec if r.get("frequency") == "MONTHLY")
    other = sum((r.get("nextPaymentAmount") or 0) * per_year.get(r.get("frequency"), 1) for r in rec if r.get("frequency") != "MONTHLY")
    recurring = {"monthly": r2(monthly), "other": r2(other), "perYear": r2(monthly * 12 + other), "count": len(rec)}

    data = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "month": month,
        "budget": budget,
        "months": months,
        "avg": avg,
        "ytd": ytd,
        "categoriesByMonth": by_month,
        "networth": networth,
        "recurring": recurring,
    }
    Path(out_file).write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {out_file}: month {month}, {len(months)} months, {len(groups)} budget groups, {len(weekly)} net worth points")


if __name__ == "__main__":
    main(*sys.argv[1:])
