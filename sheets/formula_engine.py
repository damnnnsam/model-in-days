"""
Formula engine: translates the Python simulation into Google Sheets formulas.

Every function returns formula *strings* (starting with '=').
The Daily sheet has one row per simulated day (row 2 = day 0, row 2501 = day 2499).
Formulas reference named ranges on the Inputs sheet for readability.
"""
from __future__ import annotations


# ── Column layout for the Daily sheet ──────────────────────────────────
# Column letters mapped to their meaning.
# Update DAILY_COLUMNS if you add/remove/reorder columns.

DAILY_COLUMNS = {
    "A": "day",
    "B": "leads_inbound",
    "C": "leads_outbound",
    "D": "leads_organic",
    "E": "new_cust_inbound",
    "F": "new_cust_outbound",
    "G": "new_cust_organic",
    "H": "new_cust_viral",
    "I": "new_cust_total_raw",
    "J": "new_cust_total",       # post-TAM cap
    "K": "revenue_new",
    "L": "cash_collected_new",
    "M": "cost_sales_new",
    "N": "cost_fulfill_new",
    "O": "renewal_events",
    "P": "renewed",
    "Q": "revenue_renewal",
    "R": "cash_collected_renewal",
    "S": "cost_sales_renewal",
    "T": "cost_fulfill_renewal",
    "U": "refunded",
    "V": "cost_refunds",
    "W": "churned",
    "X": "active_customers",
    "Y": "cumulative_customers",
    "Z": "cost_marketing",
    "AA": "cost_sales_viral",
    "AB": "cost_fixed",
    "AC": "cost_transaction",
    "AD": "cost_interest",
    "AE": "cost_total",
    "AF": "gross_profit",
    "AG": "ebitda",
    "AH": "net_income",
    "AI": "fcf",
    "AJ": "cumulative_fcf",
    "AK": "cash_balance",
}

DAILY_HEADERS = list(DAILY_COLUMNS.values())


# ── Derived sheet rows ────────────────────────────────────────────────
# These intermediate calculations sit between Inputs and Daily.
# Row 1 = header, data starts row 2.

DERIVED_ROWS = [
    # (name, formula, description)
    ("leads_per_day_inbound",
     '=IF(use_inbound, IF(cpm>0, (media_spend/cpm)*1000/30*(ctr/100)*(funnel_conversion_rate/100), 0), 0)',
     "Daily inbound leads"),
    ("leads_per_day_outbound",
     '=IF(use_outbound, (number_of_sdrs*contacts_per_month)/30*(outbound_conversion_rate/100), 0)',
     "Daily outbound leads"),
    ("leads_per_day_organic",
     '=IF(use_organic, (organic_views_per_month/30)*(organic_view_to_lead_rate/100), 0)',
     "Daily organic leads"),
    ("delay_inbound",
     '=time_to_market_inbound + time_to_sell',
     "Total delay: impression to customer (inbound)"),
    ("delay_outbound",
     '=time_to_market_outbound + time_to_sell',
     "Total delay: contact to customer (outbound)"),
    ("delay_organic",
     '=time_to_market_organic + time_to_sell',
     "Total delay: view to customer (organic)"),
    ("viral_delay",
     '=viral_time + time_to_sell',
     "Viral referral delay"),
    ("P_times_RR",
     '=price_of_offer * realization_rate / 100',
     "Effective price after realization"),
    ("daily_media_cost",
     '=IF(use_inbound, media_spend/30, 0)',
     "Daily media spend"),
    ("daily_outbound_cost",
     '=IF(use_outbound, number_of_sdrs * outbound_salary / 30, 0)',
     "Daily SDR cost"),
    ("daily_organic_cost",
     '=IF(use_organic, organic_cost_per_month/30, 0)',
     "Daily organic cost"),
    ("daily_fixed_cost",
     '=fixed_costs_per_month / 30',
     "Daily base fixed cost"),
    ("daily_interest",
     '=debt * (interest_rate/100) / 365',
     "Daily interest cost"),
]


# ── Helper: row reference ─────────────────────────────────────────────

def _ref(col: str, row: int, absolute_col: bool = False, absolute_row: bool = False) -> str:
    """Build a cell reference like $A$2, A2, $A2, A$2."""
    c = f"${col}" if absolute_col else col
    r = f"${row}" if absolute_row else str(row)
    return f"{c}{r}"


def _indirect(col: str, row_expr: str) -> str:
    """INDIRECT reference for dynamic row offset: INDIRECT("K" & expr)."""
    return f'INDIRECT("{col}" & ({row_expr}))'


def _lookback_sum(col: str, window_named_range: str, min_row: int = 2) -> str:
    """
    SUM of column over a lookback window of variable size.
    Equivalent to SUM(col[row - window + 1 : row + 1]).
    """
    return (
        f'SUM(INDIRECT("{col}" & MAX({min_row}, ROW()-{window_named_range}+1) '
        f'& ":{col}" & ROW()))'
    )


# ── Daily sheet formulas ──────────────────────────────────────────────

def daily_formula_row(row: int) -> list[str]:
    """
    Return a list of formula strings for one row of the Daily sheet.

    Row 2 = day 0 (first data row after header).
    The list has one entry per column matching DAILY_HEADERS order.
    """
    day = row - 2  # 0-indexed day number
    is_first = row == 2
    prev_row = row - 1

    formulas = []

    # ── A: day ──
    formulas.append(str(day))

    # ── B: leads_inbound ──
    formulas.append("=leads_per_day_inbound")

    # ── C: leads_outbound ──
    formulas.append("=leads_per_day_outbound")

    # ── D: leads_organic ──
    formulas.append("=leads_per_day_organic")

    # ── E: new_cust_inbound ──
    # Customers arrive after delay_inbound days
    formulas.append(
        f'=IF(AND(use_inbound, A{row} >= delay_inbound), '
        f'leads_per_day_inbound * lead_conversion_rate_inbound/100, 0)'
    )

    # ── F: new_cust_outbound ──
    formulas.append(
        f'=IF(AND(use_outbound, A{row} >= delay_outbound), '
        f'leads_per_day_outbound * lead_conversion_rate_outbound/100, 0)'
    )

    # ── G: new_cust_organic ──
    formulas.append(
        f'=IF(AND(use_organic, A{row} >= delay_organic), '
        f'leads_per_day_organic * lead_to_customer_rate_organic/100, 0)'
    )

    # ── H: new_cust_viral ──
    # active_customers[d - viral_delay] * (invites / contract_length) * viral_conv_rate
    formulas.append(
        f'=IF(AND(use_viral, A{row} >= viral_start + viral_delay, ROW() - viral_delay >= 2), '
        f'INDIRECT("X" & (ROW() - viral_delay)) '
        f'* (invites_per_customer / MAX(contract_length, 1)) '
        f'* (conversion_rate_per_invite/100), 0)'
    )

    # ── I: new_cust_total_raw (pre-TAM) ──
    formulas.append(f'=E{row}+F{row}+G{row}+H{row}')

    # ── J: new_cust_total (post-TAM cap) ──
    if is_first:
        formulas.append(
            f'=IF(AND(total_addressable_market>0, I{row} > MAX(total_addressable_market - customer_count, 0)), '
            f'MAX(total_addressable_market - customer_count, 0), I{row})'
        )
    else:
        formulas.append(
            f'=IF(AND(total_addressable_market>0, I{row} > MAX(total_addressable_market - X{prev_row}, 0)), '
            f'MAX(total_addressable_market - X{prev_row}, 0), I{row})'
        )

    # ── K: revenue_new ──
    formulas.append(f'=J{row} * P_times_RR')

    # ── L: cash_collected_new ──
    # Inverted forward-scatter: each day's revenue is spread over time_to_collect days.
    # From row r's perspective: sum revenue_new over the last time_to_collect rows, divided by time_to_collect.
    formulas.append(
        f'=IF(time_to_collect > 0, '
        f'{_lookback_sum("K", "time_to_collect")} / time_to_collect, '
        f'K{row})'
    )

    # ── M: cost_sales_new ──
    formulas.append(f'=J{row} * price_of_offer * cost_to_sell/100')

    # ── N: cost_fulfill_new ──
    # Spread over contract_length: sum new_cust_total over lookback window, times unit fulfillment cost / contract_length
    formulas.append(
        f'=IF(contract_length > 0, '
        f'{_lookback_sum("J", "contract_length")} '
        f'* price_of_offer * (cost_to_fulfill/100) / contract_length, '
        f'J{row} * price_of_offer * (cost_to_fulfill/100))'
    )

    # ── O: renewal_events ──
    # New customers from contract_length ago renew: new_cust_total[d - CL] * (1-churn) * (1-refund)
    # Plus renewal-of-renewals: renewed[d - CL] * renewal_rate_of_renewals
    # Plus initial customers at exactly d == contract_length
    parts = []
    # New customer renewals
    parts.append(
        f'IF(AND(ROW() - contract_length >= 2, contract_length > 0), '
        f'INDIRECT("J" & (ROW() - contract_length)) * (1 - churn_rate/100) * (1 - refund_rate/100), 0)'
    )
    # Renewal-of-renewals
    parts.append(
        f'IF(AND(ROW() - contract_length >= 2, contract_length > 0), '
        f'INDIRECT("P" & (ROW() - contract_length)) * (renewal_rate_of_renewals/100), 0)'
    )
    # Initial customers contribute at d == contract_length
    parts.append(
        f'IF(AND(A{row} = contract_length, customer_count > 0, churn_rate < 100), '
        f'customer_count * (1 - churn_rate/100) * (1 - refund_rate/100), 0)'
    )
    formulas.append(f'={" + ".join(parts)}')

    # ── P: renewed ──
    formulas.append(f'=O{row}')

    # ── Q: revenue_renewal ──
    # Spread over time_to_collect_renewal, plus initial customer revenue at day 0
    init_rev_term = ""
    if is_first:
        # Initial customers book revenue at renewal price on day 0
        init_rev_term = f' + customer_count * price_of_renewal * realization_rate/100'
    formulas.append(
        f'=IF(time_to_collect_renewal > 0, '
        f'{_lookback_sum("P", "time_to_collect_renewal")} '
        f'* price_of_renewal * realization_rate/100 / time_to_collect_renewal, '
        f'P{row} * price_of_renewal * realization_rate/100)'
        f'{init_rev_term}'
    )

    # ── R: cash_collected_renewal ──
    # Same timing as revenue_renewal
    formulas.append(
        f'=IF(time_to_collect_renewal > 0, '
        f'{_lookback_sum("P", "time_to_collect_renewal")} '
        f'* price_of_renewal * realization_rate/100 / time_to_collect_renewal, '
        f'P{row} * price_of_renewal * realization_rate/100)'
        f'{init_rev_term}'
    )

    # ── S: cost_sales_renewal ──
    # Spread over time_to_collect_renewal
    formulas.append(
        f'=IF(time_to_collect_renewal > 0, '
        f'{_lookback_sum("P", "time_to_collect_renewal")} '
        f'* price_of_renewal * cost_to_sell_renewal/100 / time_to_collect_renewal, '
        f'P{row} * price_of_renewal * cost_to_sell_renewal/100)'
    )

    # ── T: cost_fulfill_renewal ──
    # Spread over contract_length
    init_fulfill_term = ""
    if is_first:
        # Initial customer fulfillment cost starts from day 0
        init_fulfill_term = (
            f' + IF(contract_length > 0, '
            f'customer_count * price_of_renewal * cost_to_fulfill_renewal/100 / contract_length, 0)'
        )
    formulas.append(
        f'=IF(contract_length > 0, '
        f'{_lookback_sum("P", "contract_length")} '
        f'* price_of_renewal * cost_to_fulfill_renewal/100 / contract_length, '
        f'P{row} * price_of_renewal * cost_to_fulfill_renewal/100)'
        f'{init_fulfill_term}'
    )

    # ── U: refunded ──
    # Refunds happen refund_period days after acquisition
    formulas.append(
        f'=IF(AND(refund_period > 0, ROW() - refund_period >= 2), '
        f'INDIRECT("J" & (ROW() - refund_period)) * refund_rate/100, 0)'
    )

    # ── V: cost_refunds ──
    formulas.append(f'=U{row} * P_times_RR')

    # ── W: churned ──
    # At contract expiry: cohort from contract_length ago, minus refunded portion, times churn
    # Plus renewal-of-renewal churn
    formulas.append(
        f'=IF(AND(contract_length > 0, ROW() - contract_length >= 2), '
        f'LET(cohort, INDIRECT("J" & (ROW()-contract_length)), '
        f'refunded_pct, refund_rate/100, '
        f'remaining, cohort * (1 - refunded_pct), '
        f'remaining * churn_rate/100) '
        f'+ IF(INDIRECT("P" & (ROW()-contract_length)) > 0, '
        f'INDIRECT("P" & (ROW()-contract_length)) * (1 - renewal_rate_of_renewals/100), 0), '
        f'0)'
    )

    # ── X: active_customers ──
    if is_first:
        formulas.append(f'=customer_count + J{row}')
    else:
        formulas.append(
            f'=MAX(IF(total_addressable_market > 0, '
            f'MIN(X{prev_row} + J{row} - U{row} - W{row}, total_addressable_market), '
            f'X{prev_row} + J{row} - U{row} - W{row}), 0)'
        )

    # ── Y: cumulative_customers ──
    formulas.append(f'=SUM($J$2:J{row}) + customer_count')

    # ── Z: cost_marketing ──
    formulas.append(
        f'=daily_media_cost + daily_outbound_cost + daily_organic_cost'
        f' + IF(use_viral, H{row} * price_of_offer * cost_to_market_viral/100, 0)'
    )

    # ── AA: cost_sales_viral ──
    formulas.append(
        f'=IF(use_viral, H{row} * price_of_offer * cost_to_sell_viral/100, 0)'
    )

    # ── AB: cost_fixed ──
    formulas.append(
        f'=daily_fixed_cost + (X{row}/100) * (fixed_cost_increase_per_100_customers/30)'
    )

    # ── AC: cost_transaction ──
    formulas.append(f'=(L{row} + R{row}) * transaction_fee/100')

    # ── AD: cost_interest ──
    formulas.append('=daily_interest')

    # ── AE: cost_total ──
    formulas.append(
        f'=Z{row} + M{row} + S{row} + AA{row} + N{row} + T{row} + AB{row} + AC{row} + AD{row} + V{row}'
    )

    # ── AF: gross_profit ──
    # gross_revenue (cash collected) - COGS (fulfillment + transaction)
    formulas.append(f'=(L{row}+R{row}) - (N{row}+T{row}+AC{row})')

    # ── AG: ebitda ──
    formulas.append(f'=AF{row} - (Z{row}+M{row}+S{row}+AA{row}+AB{row}+V{row})')

    # ── AH: net_income ──
    formulas.append(f'=AG{row} - IF(AG{row}>0, AG{row}*tax_rate/100, 0) - AD{row}')

    # ── AI: fcf ──
    formulas.append(f'=AH{row}')

    # ── AJ: cumulative_fcf ──
    formulas.append(f'=SUM($AI$2:AI{row})')

    # ── AK: cash_balance ──
    if is_first:
        formulas.append(f'=cash_in_bank - upfront_investment_costs + AI{row}')
    else:
        formulas.append(f'=AK{prev_row} + AI{row}')

    return formulas


def daily_all_formulas(time_max: int = 2500) -> list[list[str]]:
    """
    Return the full Daily sheet grid: [header_row, day0_row, day1_row, ...].
    Each inner list has len(DAILY_HEADERS) entries.
    """
    rows = [DAILY_HEADERS]
    for row in range(2, 2 + time_max):
        rows.append(daily_formula_row(row))
    return rows


# ── Derived sheet ─────────────────────────────────────────────────────

def derived_sheet_data() -> list[list[str]]:
    """
    Return the Derived sheet grid: [header, row2, row3, ...].
    Columns: Name | Value | Description
    """
    rows = [["Name", "Value", "Description"]]
    for name, formula, desc in DERIVED_ROWS:
        rows.append([name, formula, desc])
    return rows


# ── Monthly sheet ─────────────────────────────────────────────────────

MONTHLY_SUM_COLS = {
    "new_customers": "J",
    "revenue_new": "K",
    "revenue_renewal": "Q",
    "cash_collected_new": "L",
    "cash_collected_renewal": "R",
    "cost_marketing": "Z",
    "cost_sales_new": "M",
    "cost_sales_renewal": "S",
    "cost_sales_viral": "AA",
    "cost_fulfill_new": "N",
    "cost_fulfill_renewal": "T",
    "cost_fixed": "AB",
    "cost_transaction": "AC",
    "cost_interest": "AD",
    "cost_refunds": "V",
    "cost_total": "AE",
    "gross_profit": "AF",
    "ebitda": "AG",
    "net_income": "AH",
    "fcf": "AI",
}

MONTHLY_SNAPSHOT_COLS = {
    "active_customers": "X",
    "cumulative_customers": "Y",
    "cash_balance": "AK",
    "cumulative_fcf": "AJ",
}

MONTHLY_HEADERS = (
    ["month"] + list(MONTHLY_SUM_COLS.keys()) + list(MONTHLY_SNAPSHOT_COLS.keys())
    + ["revenue_total", "cash_collected_total", "cost_sales", "cost_fulfillment"]
)


def monthly_formula_row(month: int) -> list[str]:
    """
    Return formula list for one month row.
    month is 1-indexed. Daily sheet rows: start_row to end_row.
    """
    # Daily rows for this month (30-day periods)
    daily_start = 2 + (month - 1) * 30  # row number in Daily sheet
    daily_end = daily_start + 29

    formulas = [str(month)]

    # Sum columns
    for name, col in MONTHLY_SUM_COLS.items():
        formulas.append(f"=SUM(Daily!{col}{daily_start}:{col}{daily_end})")

    # Snapshot columns (end-of-month value)
    for name, col in MONTHLY_SNAPSHOT_COLS.items():
        formulas.append(f"=Daily!{col}{daily_end}")

    # Derived totals
    row = len(formulas)  # not used for cell refs, we reference by relative position
    # These reference the current row's values. Find the column index.
    rev_new_idx = list(MONTHLY_SUM_COLS.keys()).index("revenue_new") + 2  # +2 for month col (1) and 1-indexing
    rev_ren_idx = list(MONTHLY_SUM_COLS.keys()).index("revenue_renewal") + 2
    cc_new_idx = list(MONTHLY_SUM_COLS.keys()).index("cash_collected_new") + 2
    cc_ren_idx = list(MONTHLY_SUM_COLS.keys()).index("cash_collected_renewal") + 2
    cs_new_idx = list(MONTHLY_SUM_COLS.keys()).index("cost_sales_new") + 2
    cs_ren_idx = list(MONTHLY_SUM_COLS.keys()).index("cost_sales_renewal") + 2
    csv_idx = list(MONTHLY_SUM_COLS.keys()).index("cost_sales_viral") + 2
    cfn_idx = list(MONTHLY_SUM_COLS.keys()).index("cost_fulfill_new") + 2
    cfr_idx = list(MONTHLY_SUM_COLS.keys()).index("cost_fulfill_renewal") + 2

    # Use INDIRECT with ADDRESS to reference cells in the same row
    def _self_col(col_idx: int) -> str:
        return f'INDIRECT(ADDRESS(ROW(), {col_idx}))'

    formulas.append(f'={_self_col(rev_new_idx)} + {_self_col(rev_ren_idx)}')          # revenue_total
    formulas.append(f'={_self_col(cc_new_idx)} + {_self_col(cc_ren_idx)}')             # cash_collected_total
    formulas.append(f'={_self_col(cs_new_idx)} + {_self_col(cs_ren_idx)} + {_self_col(csv_idx)}')  # cost_sales
    formulas.append(f'={_self_col(cfn_idx)} + {_self_col(cfr_idx)}')                   # cost_fulfillment

    return formulas


def monthly_all_formulas(time_max: int = 2500) -> list[list[str]]:
    """Return the full Monthly sheet grid."""
    n_months = time_max // 30
    rows = [MONTHLY_HEADERS]
    for m in range(1, n_months + 1):
        rows.append(monthly_formula_row(m))
    return rows


# ── Valuation sheet ───────────────────────────────────────────────────

def valuation_sheet_data(time_max: int = 2500) -> list[list[str]]:
    """
    Return the Valuation sheet grid: [header, row2, row3, ...].
    Columns: Metric | Value | Description
    """
    # DCF projection end row in Daily sheet
    # projection_period_dcf is a named range, but we need it for INDIRECT ranges.
    # We'll use MIN(projection_period_dcf, time_max) capped at available rows.

    rows = [["Metric", "Value", "Description"]]

    # Daily discount factor: (1 + r)^(1/365)
    rows.append([
        "Daily Discount Factor",
        '=(1 + discount_rate/100) ^ (1/365)',
        "Used to discount each day's FCF",
    ])

    # PV of FCF over projection period
    # SUMPRODUCT of fcf * discount_factor for each day
    # discount_factor for day d = daily_discount ^ (-d)
    rows.append([
        "PV of FCF",
        (
            '=SUMPRODUCT('
            f'Daily!AI$2:INDIRECT("Daily!AI" & MIN(projection_period_dcf, {time_max}) + 1), '
            f'(1/(B2 ^ SEQUENCE(MIN(projection_period_dcf, {time_max}), 1, 0, 1))))'
        ),
        "Present value of FCF over projection period",
    ])

    # Terminal FCF: average of last 365 days of FCF in projection period
    rows.append([
        "Avg Daily Terminal FCF",
        (
            f'=AVERAGE(INDIRECT("Daily!AI" & MAX(2, MIN(projection_period_dcf, {time_max}) + 1 - 365) '
            f'& ":Daily!AI" & MIN(projection_period_dcf, {time_max}) + 1))'
        ),
        "Average daily FCF over last year of projection",
    ])

    rows.append([
        "Annual Terminal FCF",
        '=B4 * 365',
        "Annualized terminal FCF",
    ])

    rows.append([
        "Terminal Value",
        '=IF(discount_rate/100 > perpetual_growth_rate/100, '
        'B5 * (1 + perpetual_growth_rate/100) / (discount_rate/100 - perpetual_growth_rate/100), 0)',
        "Gordon Growth Model",
    ])

    rows.append([
        "PV of Terminal Value",
        f'=B6 / ((1 + discount_rate/100) ^ (MIN(projection_period_dcf, {time_max})/365))',
        "Terminal value discounted to day 0",
    ])

    rows.append([
        "Enterprise Value (DCF)",
        '=B3 + B7',
        "PV(FCF) + PV(Terminal)",
    ])

    # Cash at valuation point
    rows.append([
        "Cash at Valuation",
        f'=INDIRECT("Daily!AK" & MIN(projection_period_dcf, {time_max}) + 1)',
        "Cash balance at end of projection",
    ])

    rows.append([
        "Equity Value (DCF)",
        '=B8 - debt + MAX(B9, 0)',
        "EV - debt + cash",
    ])

    rows.append([
        "Share Price (DCF)",
        '=B10 / MAX(number_of_shares, 1)',
        "",
    ])

    # ── EBITDA Multiple ───────────────────────────────────────────
    rows.append(["", "", ""])  # spacer

    rows.append([
        "Trailing 12-Month EBITDA",
        (
            f'=SUM(INDIRECT("Daily!AG" & MAX(2, MIN(projection_period_ebitda, {time_max}) + 1 - 365) '
            f'& ":Daily!AG" & MIN(projection_period_ebitda, {time_max}) + 1))'
        ),
        "Sum of EBITDA over last 365 days of EBITDA projection",
    ])

    rows.append([
        "Enterprise Value (EBITDA)",
        '=B13 * enterprise_multiple_ebitda',
        "Trailing EBITDA x multiple",
    ])

    rows.append([
        "Cash at EBITDA Valuation",
        f'=INDIRECT("Daily!AK" & MIN(projection_period_ebitda, {time_max}) + 1)',
        "",
    ])

    rows.append([
        "Equity Value (EBITDA)",
        '=B14 - debt + MAX(B15, 0)',
        "EV - debt + cash",
    ])

    rows.append([
        "Share Price (EBITDA)",
        '=B16 / MAX(number_of_shares, 1)',
        "",
    ])

    return rows
