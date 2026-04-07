"""
Metadata for every ModelInputs field: section, display label, unit, description.

This drives the Inputs sheet layout and provides the reverse lookup
(display label -> field name) for importing from Sheets.
"""
from __future__ import annotations

# (field_name, section, label, unit, description)
FIELD_META: list[tuple[str, str, str, str, str]] = [
    # ── Starting State ────────────────────────────────────────────
    ("cash_in_bank",        "Starting State", "Cash in Bank",               "$",    "Cash in the bank at time t=0"),
    ("assets",              "Starting State", "Assets",                     "$",    ""),
    ("liabilities",         "Starting State", "Liabilities",                "$",    ""),
    ("customer_count",      "Starting State", "Initial Customers",          "",     "Customer count at time t=0"),
    ("total_addressable_market", "Starting State", "Total Addressable Market", "", "TAM"),
    ("upfront_investment_costs", "Starting State", "Upfront Investment Costs", "$", "Up-front capital needed to start"),
    ("debt",                "Starting State", "Debt",                       "$",    "Sum of liabilities / outstanding debt"),
    ("interest_rate",       "Starting State", "Debt Interest Rate",         "%",    "Annual interest rate on the debt"),

    # ── Sales ─────────────────────────────────────────────────────
    ("cost_to_sell",        "Sales", "Cost to Sell",                        "%",    "Commission cost as % of Price"),
    ("time_to_sell",        "Sales", "Time to Sell",                        "days", "Days from lead to first purchase"),
    ("avg_deals_per_rep_per_month", "Sales", "Avg Deals per Rep / Month",  "",     ""),

    # ── Inbound ───────────────────────────────────────────────────
    ("use_inbound",         "Inbound", "Enable Inbound",                   "bool", ""),
    ("media_spend",         "Inbound", "Media Spend",                      "$/mo", "Monthly paid media budget"),
    ("cpm",                 "Inbound", "CPM",                              "$",    "Cost per 1000 impressions"),
    ("ctr",                 "Inbound", "CTR",                              "%",    "Click-through rate"),
    ("funnel_conversion_rate", "Inbound", "Funnel Conversion Rate",        "%",    "% click to lead"),
    ("time_to_market_inbound", "Inbound", "Time to Market — Inbound",     "days", "Days from ad to lead event"),
    ("lead_conversion_rate_inbound", "Inbound", "Lead to Customer — Inbound", "%", "% of inbound leads that buy"),

    # ── Outbound ──────────────────────────────────────────────────
    ("use_outbound",        "Outbound", "Enable Outbound",                 "bool", ""),
    ("outbound_salary",     "Outbound", "SDR Salary",                      "$/mo", "Monthly salary per SDR"),
    ("contacts_per_month",  "Outbound", "Contacts per Month",              "",     "Per SDR"),
    ("number_of_sdrs",      "Outbound", "Number of SDRs",                  "",     ""),
    ("outbound_conversion_rate", "Outbound", "Contact to Lead Rate",       "%",    "% of contacts that become leads"),
    ("time_to_market_outbound", "Outbound", "Time to Market — Outbound",   "days", "Days from first contact to discovery"),
    ("lead_conversion_rate_outbound", "Outbound", "Lead to Customer — Outbound", "%", ""),

    # ── Organic ───────────────────────────────────────────────────
    ("use_organic",         "Organic", "Enable Organic",                   "bool", ""),
    ("organic_views_per_month", "Organic", "Organic Views / Month",        "",     ""),
    ("organic_view_to_lead_rate", "Organic", "View to Lead Rate",          "%",    ""),
    ("lead_to_customer_rate_organic", "Organic", "Lead to Customer — Organic", "%", ""),
    ("time_to_market_organic", "Organic", "Time to Market — Organic",      "days", ""),
    ("organic_cost_per_month", "Organic", "Organic Cost",                   "$/mo", ""),

    # ── Product ───────────────────────────────────────────────────
    ("price_of_offer",      "Product", "Price of Offer",                   "$",    "Average total price over contract"),
    ("realization_rate",    "Product", "Realization Rate",                  "%",    "Cash collected / cash requested"),
    ("cost_to_fulfill",     "Product", "Cost to Fulfill",                  "%",    "Delivery cost as % of P"),
    ("time_to_collect",     "Product", "Time to Collect",                  "days", "Days to full payment collection"),
    ("refund_period",       "Product", "Refund Period",                    "days", ""),
    ("refund_rate",         "Product", "Refund Rate",                      "%",    ""),
    ("contract_length",     "Product", "Contract Length",                  "days", "Time between purchase and renewal"),

    # ── Renewals ──────────────────────────────────────────────────
    ("churn_rate",          "Renewals", "Churn Rate",                      "%",    "% who do NOT renew"),
    ("price_of_renewal",    "Renewals", "Price of Renewal",                "$",    ""),
    ("cost_to_sell_renewal", "Renewals", "Cost to Sell Renewal",           "%",    "% of renewal price"),
    ("cost_to_fulfill_renewal", "Renewals", "Cost to Fulfill Renewal",     "%",    "% of renewal price"),
    ("time_to_collect_renewal", "Renewals", "Time to Collect Renewal",     "days", ""),
    ("renewal_rate_of_renewals", "Renewals", "Renewal Rate of Renewals",   "%",    "Rate at which renewals renew again"),

    # ── Viral ─────────────────────────────────────────────────────
    ("use_viral",           "Viral", "Enable Viral",                       "bool", ""),
    ("invites_per_customer", "Viral", "Invites per Customer",              "",     "Referral requests per customer"),
    ("conversion_rate_per_invite", "Viral", "Invite Conversion Rate",      "%",    ""),
    ("viral_time",          "Viral", "Viral Time",                         "days", "Average time for referral to convert"),
    ("viral_start",         "Viral", "Viral Start",                        "days", "Day referral mechanism begins"),
    ("cost_to_sell_viral",  "Viral", "Cost to Sell Viral",                 "%",    "% of P"),
    ("cost_to_market_viral", "Viral", "Cost to Market Viral",              "%",    "Referral bonus as % of P"),

    # ── Administration ────────────────────────────────────────────
    ("transaction_fee",     "Administration", "Transaction Fee",           "%",    "Payment processor fee"),
    ("fixed_costs_per_month", "Administration", "Fixed Costs",             "$/mo", "Rent, salaries, tools, etc."),
    ("fixed_cost_increase_per_100_customers", "Administration", "FC Increase per 100 Customers", "$/mo", ""),

    # ── Valuation ─────────────────────────────────────────────────
    ("tax_rate",            "Valuation", "Tax Rate",                       "%",    ""),
    ("inflation_rate",      "Valuation", "Inflation Rate",                 "%",    ""),
    ("time_max",            "Valuation", "Simulation Period",              "days", "Total days to simulate"),
    ("number_of_shares",    "Valuation", "Number of Shares",              "",     ""),
    ("projection_period_dcf", "Valuation", "DCF Projection Period",       "days", ""),
    ("discount_rate",       "Valuation", "Discount Rate",                  "%",    "Required rate of return / WACC"),
    ("perpetual_growth_rate", "Valuation", "Perpetual Growth Rate",        "%",    "Long-term growth for terminal value"),
    ("enterprise_multiple_ebitda", "Valuation", "EBITDA Multiple",         "",     "EV = EBITDA x multiple"),
    ("projection_period_ebitda", "Valuation", "EBITDA Projection Period",  "days", ""),
]

# Row 1 = header, so field at index i is at row i+2
FIELD_TO_ROW: dict[str, int] = {
    entry[0]: i + 2 for i, entry in enumerate(FIELD_META)
}

ROW_TO_FIELD: dict[int, str] = {v: k for k, v in FIELD_TO_ROW.items()}

# Reverse lookup: lowercase label -> field name
LABEL_TO_FIELD: dict[str, str] = {
    entry[2].lower().strip(): entry[0] for entry in FIELD_META
}


def field_count() -> int:
    return len(FIELD_META)


def value_cell(field_name: str) -> str:
    """Return the Inputs sheet cell reference for a field's value (column C)."""
    row = FIELD_TO_ROW[field_name]
    return f"Inputs!$C${row}"
