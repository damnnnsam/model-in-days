from dataclasses import dataclass, field


@dataclass
class ModelInputs:
    # ── Starting State ──────────────────────────────────────────────
    cash_in_bank: float = 0.0
    assets: float = 0.0
    liabilities: float = 0.0
    customer_count: int = 0
    total_addressable_market: int = 100_000
    upfront_investment_costs: float = 0.0
    debt: float = 0.0
    interest_rate: float = 6.0  # annual % on debt

    # ── Sales ───────────────────────────────────────────────────────
    cost_to_sell: float = 15.0  # % of P
    time_to_sell: int = 20  # days
    avg_deals_per_rep_per_month: float = 1.0

    # ── Channel toggles ────────────────────────────────────────────
    use_inbound: bool = True
    use_outbound: bool = False
    use_organic: bool = False
    use_viral: bool = False

    # ── Channel Start Days ─────────────────────────────────────────
    start_day_inbound: int = 0
    start_day_outbound: int = 0
    start_day_organic: int = 0

    # ── Inbound Marketing ───────────────────────────────────────────
    media_spend: float = 50_000.0  # $/month
    cpm: float = 55.0
    ctr: float = 1.0  # %
    funnel_conversion_rate: float = 2.0  # % click→lead
    time_to_market_inbound: int = 1  # days
    lead_conversion_rate_inbound: float = 8.0  # % lead→customer

    # ── Outbound Marketing ──────────────────────────────────────────
    outbound_salary: float = 3_000.0  # $/month per SDR
    contacts_per_month: int = 2_000  # per SDR
    number_of_sdrs: int = 40
    outbound_conversion_rate: float = 2.0  # % contact→lead
    time_to_market_outbound: int = 11  # days
    lead_conversion_rate_outbound: float = 8.0  # % lead→customer

    # ── Organic ─────────────────────────────────────────────────────
    organic_views_per_month: int = 0
    organic_view_to_lead_rate: float = 0.0  # %
    lead_to_customer_rate_organic: float = 0.0  # %
    time_to_market_organic: int = 30  # days
    organic_cost_per_month: float = 0.0

    # ── Product ─────────────────────────────────────────────────────
    price_of_offer: float = 5_000.0  # P
    realization_rate: float = 93.0  # %
    cost_to_fulfill: float = 10.0  # % of P
    time_to_collect: int = 300  # days
    refund_period: int = 60  # days
    refund_rate: float = 2.0  # %
    contract_length: int = 365  # days (time_to_renew)

    # ── Renewals ────────────────────────────────────────────────────
    churn_rate: float = 50.0  # %
    price_of_renewal: float = 7_000.0
    cost_to_sell_renewal: float = 10.0  # % of renewal price
    cost_to_fulfill_renewal: float = 10.0  # % of renewal price
    time_to_collect_renewal: int = 30  # days
    renewal_rate_of_renewals: float = 50.0  # %

    # ── Viral Component ─────────────────────────────────────────────
    invites_per_customer: float = 0.0
    conversion_rate_per_invite: float = 5.0  # %
    viral_time: int = 20  # days
    viral_start: int = 0  # day viral effect begins
    cost_to_sell_viral: float = 15.0  # % of P
    cost_to_market_viral: float = 10.0  # % of P

    # ── Administration ──────────────────────────────────────────────
    transaction_fee: float = 2.9  # %
    fixed_costs_per_month: float = 10_000.0
    fixed_cost_increase_per_100_customers: float = 0.0

    # ── Valuation ───────────────────────────────────────────────────
    tax_rate: float = 22.0  # %
    inflation_rate: float = 2.0  # %
    time_max: int = 2500  # days to simulate
    number_of_shares: int = 1_000_000

    # DCF
    projection_period_dcf: int = 1825  # days (5 years)
    discount_rate: float = 9.0  # %
    perpetual_growth_rate: float = 2.0  # %

    # EBITDA multiple
    enterprise_multiple_ebitda: float = 14.0
    projection_period_ebitda: int = 1825  # days
