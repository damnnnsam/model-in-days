from __future__ import annotations

import streamlit as st

from engine.inputs import ModelInputs
from engine.url_state import decode_model


def _load_from_url() -> ModelInputs | None:
    """Try to load model state from URL query parameter."""
    params = st.query_params
    if "m" in params:
        try:
            return decode_model(params["m"])
        except Exception:
            pass
    return None


def render_sidebar() -> ModelInputs:
    """Render all input sections in the sidebar and return a populated ModelInputs."""
    st.sidebar.title("Model Inputs")

    url_model = _load_from_url()
    inp = url_model if url_model is not None else ModelInputs()

    # ── Starting State ──────────────────────────────────────────────
    with st.sidebar.expander("Starting State", expanded=False):
        st.caption("Starting state of your company at time t=0.")
        inp.cash_in_bank = st.number_input(
            "Cash in Bank ($)", value=inp.cash_in_bank, step=1000.0, key="cash_in_bank",
            help="Cash in the bank at time t=0.",
        )
        inp.assets = st.number_input(
            "Assets ($)", value=inp.assets, step=1000.0, key="assets",
        )
        inp.liabilities = st.number_input(
            "Liabilities ($)", value=inp.liabilities, step=1000.0, key="liabilities",
        )
        inp.customer_count = int(st.number_input(
            "Initial Customers (c₀)", value=inp.customer_count, step=1, key="customer_count",
            help="Customer count at time t=0.",
        ))
        inp.total_addressable_market = int(st.number_input(
            "Total Addressable Market (TAM)", value=inp.total_addressable_market, step=1000, key="tam",
        ))
        inp.upfront_investment_costs = st.number_input(
            "Upfront Investment Costs ($)", value=inp.upfront_investment_costs, step=1000.0, key="upfront",
            help="Up-front capital needed to start. Includes building the mechanism and sales funnel.",
        )
        inp.debt = st.number_input(
            "Debt ($)", value=inp.debt, step=1000.0, key="debt",
            help="Sum of liabilities / outstanding debt.",
        )
        inp.interest_rate = st.number_input(
            "Debt Interest Rate (%)", value=inp.interest_rate, step=0.5, key="interest_rate",
            help="Annual interest rate on the debt.",
        )

    # ── Sales ───────────────────────────────────────────────────────
    with st.sidebar.expander("Sales", expanded=False):
        inp.cost_to_sell = st.number_input(
            "Cost to Sell — c_s (% of P)", value=inp.cost_to_sell, step=1.0, key="cost_to_sell",
            help="Commission cost to turn a lead into a closed account, as % of Price.",
        )
        inp.time_to_sell = int(st.number_input(
            "Time to Sell — t_s (days)", value=inp.time_to_sell, step=1, key="time_to_sell",
            help="Days between lead creation and first purchase (sales cycle).",
        ))
        inp.avg_deals_per_rep_per_month = st.number_input(
            "Avg Deals per Sales Rep / Month", value=inp.avg_deals_per_rep_per_month, step=0.5, key="deals_per_rep",
        )

    # ── Marketing Channels ──────────────────────────────────────────
    with st.sidebar.expander("Marketing Channels", expanded=True):
        st.subheader("Inbound")
        inp.use_inbound = st.checkbox("Enable Inbound", value=inp.use_inbound, key="use_inbound")
        if inp.use_inbound:
            inp.media_spend = st.number_input(
                "Media Spend ($/month)", value=inp.media_spend, step=1000.0, key="media_spend",
                help="Monthly paid media budget.",
            )
            inp.cpm = st.number_input(
                "CPM — Cost per 1000 Impressions ($)", value=inp.cpm, step=1.0, key="cpm",
                help="Cost to show your ad 1,000 times.",
            )
            inp.ctr = st.number_input(
                "CTR — Click-Through Rate (%)", value=inp.ctr, step=0.1, key="ctr",
                help="Percentage of impressions that result in a click.",
            )
            inp.funnel_conversion_rate = st.number_input(
                "Funnel Conversion Rate (% click→lead)", value=inp.funnel_conversion_rate, step=0.5, key="funnel_conv",
                help="Percentage of clicks that become a lead (e.g. complete a quiz).",
            )
            inp.time_to_market_inbound = int(st.number_input(
                "Time to Market — Inbound (days)", value=inp.time_to_market_inbound, step=1, key="ttm_inbound",
                help="Days from first ad impression to lead event.",
            ))
            inp.lead_conversion_rate_inbound = st.number_input(
                "Lead→Customer Rate — Inbound (%)", value=inp.lead_conversion_rate_inbound, step=1.0, key="lcr_inbound",
                help="Percentage of inbound leads that become paying customers.",
            )

        st.divider()
        st.subheader("Outbound")
        inp.use_outbound = st.checkbox("Enable Outbound", value=inp.use_outbound, key="use_outbound")
        if inp.use_outbound:
            inp.outbound_salary = st.number_input(
                "SDR Salary ($/month)", value=inp.outbound_salary, step=500.0, key="ob_salary",
                help="Average monthly salary/commission per SDR.",
            )
            inp.contacts_per_month = int(st.number_input(
                "Contacts per Month (per SDR)", value=inp.contacts_per_month, step=100, key="contacts",
                help="Emails, calls, LinkedIn messages per SDR per month.",
            ))
            inp.number_of_sdrs = int(st.number_input(
                "Number of SDRs", value=inp.number_of_sdrs, step=1, key="sdrs",
            ))
            inp.outbound_conversion_rate = st.number_input(
                "Contact→Lead Rate (%)", value=inp.outbound_conversion_rate, step=0.5, key="ob_conv",
                help="Percentage of contacts that become leads.",
            )
            inp.time_to_market_outbound = int(st.number_input(
                "Time to Market — Outbound (days)", value=inp.time_to_market_outbound, step=1, key="ttm_outbound",
                help="Days from first contact to discovery call.",
            ))
            inp.lead_conversion_rate_outbound = st.number_input(
                "Lead→Customer Rate — Outbound (%)", value=inp.lead_conversion_rate_outbound, step=1.0, key="lcr_outbound",
            )

        st.divider()
        st.subheader("Organic")
        inp.use_organic = st.checkbox("Enable Organic", value=inp.use_organic, key="use_organic")
        if inp.use_organic:
            inp.organic_views_per_month = int(st.number_input(
                "Organic Views / Month", value=inp.organic_views_per_month, step=1000, key="org_views",
            ))
            inp.organic_view_to_lead_rate = st.number_input(
                "View→Lead Rate (%)", value=inp.organic_view_to_lead_rate, step=0.1, key="org_conv",
            )
            inp.lead_to_customer_rate_organic = st.number_input(
                "Lead→Customer Rate — Organic (%)", value=inp.lead_to_customer_rate_organic, step=1.0, key="lcr_organic",
            )
            inp.time_to_market_organic = int(st.number_input(
                "Time to Market — Organic (days)", value=inp.time_to_market_organic, step=1, key="ttm_organic",
            ))
            inp.organic_cost_per_month = st.number_input(
                "Organic Cost ($/month)", value=inp.organic_cost_per_month, step=500.0, key="org_cost",
            )

    # ── Product ─────────────────────────────────────────────────────
    with st.sidebar.expander("Product", expanded=False):
        inp.price_of_offer = st.number_input(
            "Price of Offer — P ($)", value=inp.price_of_offer, step=100.0, key="price",
            help="Average total price over the contract period.",
        )
        inp.realization_rate = st.number_input(
            "Realization Rate — RR (%)", value=inp.realization_rate, step=1.0, key="rr",
            help="Cash collected / cash requested. Accounts for payment defaults.",
        )
        inp.cost_to_fulfill = st.number_input(
            "Cost to Fulfill — c_f (% of P)", value=inp.cost_to_fulfill, step=1.0, key="c_f",
            help="Cost to deliver the product/service, as % of P.",
        )
        inp.time_to_collect = int(st.number_input(
            "Time to Collect — t_c (days)", value=inp.time_to_collect, step=30, key="t_c",
            help="Days between first purchase and full payment collection.",
        ))
        inp.refund_period = int(st.number_input(
            "Refund Period (days)", value=inp.refund_period, step=10, key="refund_period",
        ))
        inp.refund_rate = st.number_input(
            "Refund Rate (%)", value=inp.refund_rate, step=0.5, key="refund_rate",
        )
        inp.contract_length = int(st.number_input(
            "Contract Length (days)", value=inp.contract_length, step=30, key="contract_length",
            help="Time between first purchase and expected renewal.",
        ))

    # ── Renewals ────────────────────────────────────────────────────
    with st.sidebar.expander("Renewals", expanded=False):
        inp.churn_rate = st.number_input(
            "Churn Rate (%)", value=inp.churn_rate, step=5.0, key="churn",
            help="Percentage of customers who do NOT renew after contract ends.",
        )
        if inp.churn_rate < 100:
            inp.price_of_renewal = st.number_input(
                "Price of Renewal ($)", value=inp.price_of_renewal, step=500.0, key="p_renewal",
            )
            inp.cost_to_sell_renewal = st.number_input(
                "Cost to Sell Renewal (% of renewal price)", value=inp.cost_to_sell_renewal, step=1.0, key="c_s_ren",
            )
            inp.cost_to_fulfill_renewal = st.number_input(
                "Cost to Fulfill Renewal (% of renewal price)", value=inp.cost_to_fulfill_renewal, step=1.0, key="c_f_ren",
            )
            inp.time_to_collect_renewal = int(st.number_input(
                "Time to Collect Renewal (days)", value=inp.time_to_collect_renewal, step=10, key="t_c_ren",
            ))
            inp.renewal_rate_of_renewals = st.number_input(
                "Renewal Rate of Renewals (%)", value=inp.renewal_rate_of_renewals, step=5.0, key="ren_of_ren",
                help="Rate at which already-renewed customers renew again.",
            )

    # ── Viral Component ─────────────────────────────────────────────
    with st.sidebar.expander("Viral Component", expanded=False):
        inp.use_viral = st.checkbox("Enable Viral", value=inp.use_viral, key="use_viral")
        if inp.use_viral:
            inp.invites_per_customer = st.number_input(
                "Invites per Customer", value=inp.invites_per_customer, step=1.0, key="invites",
                help="Average referral requests per customer during active time.",
            )
            inp.conversion_rate_per_invite = st.number_input(
                "Invite Conversion Rate (%)", value=inp.conversion_rate_per_invite, step=1.0, key="viral_conv",
            )
            inp.viral_time = int(st.number_input(
                "Viral Time (days)", value=inp.viral_time, step=5, key="viral_time",
                help="Average time for a referral to convert.",
            ))
            inp.viral_start = int(st.number_input(
                "Viral Start (day)", value=inp.viral_start, step=30, key="viral_start",
                help="Day at which referral mechanism begins.",
            ))
            inp.cost_to_sell_viral = st.number_input(
                "Cost to Sell Viral (% of P)", value=inp.cost_to_sell_viral, step=1.0, key="c_s_viral",
            )
            inp.cost_to_market_viral = st.number_input(
                "Cost to Market Viral (% of P)", value=inp.cost_to_market_viral, step=1.0, key="c_m_viral",
                help="Referral bonus / cost per successful referral, as % of P.",
            )

    # ── Administration ──────────────────────────────────────────────
    with st.sidebar.expander("Administration", expanded=False):
        inp.transaction_fee = st.number_input(
            "Transaction Fee (%)", value=inp.transaction_fee, step=0.1, key="tf",
            help="Payment processor fee (typically 2.9%).",
        )
        inp.fixed_costs_per_month = st.number_input(
            "Fixed Costs ($/month)", value=inp.fixed_costs_per_month, step=1000.0, key="fc",
            help="Rent, salaries, engineering, tools, etc.",
        )
        inp.fixed_cost_increase_per_100_customers = st.number_input(
            "FC Increase per 100 Customers ($/month)", value=inp.fixed_cost_increase_per_100_customers, step=500.0, key="fc_scale",
            help="Additional fixed cost per 100 active customers.",
        )

    # ── Valuation ───────────────────────────────────────────────────
    with st.sidebar.expander("Valuation Parameters", expanded=False):
        inp.tax_rate = st.number_input(
            "Tax Rate (%)", value=inp.tax_rate, step=1.0, key="tax",
        )
        inp.inflation_rate = st.number_input(
            "Inflation Rate (%)", value=inp.inflation_rate, step=0.5, key="inflation",
        )
        inp.time_max = int(st.number_input(
            "Simulation Period (days)", value=inp.time_max, step=100, key="time_max",
            help="Total number of days to simulate.",
        ))
        inp.number_of_shares = int(st.number_input(
            "Number of Shares", value=inp.number_of_shares, step=100_000, key="shares",
        ))

        st.subheader("DCF Method")
        inp.projection_period_dcf = int(st.number_input(
            "DCF Projection Period (days)", value=inp.projection_period_dcf, step=365, key="proj_dcf",
            help="Period over which FCF is discounted.",
        ))
        inp.discount_rate = st.number_input(
            "Discount Rate (%)", value=inp.discount_rate, step=0.5, key="r_disc",
            help="Required rate of return / WACC.",
        )
        inp.perpetual_growth_rate = st.number_input(
            "Perpetual Growth Rate (%)", value=inp.perpetual_growth_rate, step=0.5, key="r_growth",
            help="Long-term steady-state growth rate for terminal value.",
        )

        st.subheader("EBITDA Multiple")
        inp.enterprise_multiple_ebitda = st.number_input(
            "EBITDA Multiple", value=inp.enterprise_multiple_ebitda, step=1.0, key="ebitda_mult",
            help="Enterprise value = EBITDA × this multiple.",
        )
        inp.projection_period_ebitda = int(st.number_input(
            "EBITDA Projection Period (days)", value=inp.projection_period_ebitda, step=365, key="proj_ebitda",
        ))

    return inp


def render_model_inputs(defaults: ModelInputs | None = None, prefix: str = "mi",
                        show_title: bool = False) -> ModelInputs:
    """
    Render all model input sections in the sidebar with configurable key prefix.

    This is the canonical input renderer — use this everywhere instead of
    reimplementing input widgets. Supports pre-populated defaults for editing
    saved models.
    """
    inp = ModelInputs(**defaults.__dict__) if defaults is not None else ModelInputs()

    if show_title:
        st.sidebar.markdown("### Model Inputs")

    # ── Starting State ─────────────────────────────────────────────
    with st.sidebar.expander("Starting State", expanded=False):
        inp.cash_in_bank = st.number_input(
            "Cash in Bank ($)", value=inp.cash_in_bank, step=1000.0, key=f"{prefix}_cash",
            help="Cash in the bank at time t=0.",
        )
        inp.assets = st.number_input(
            "Assets ($)", value=inp.assets, step=1000.0, key=f"{prefix}_assets",
            help="Non-cash assets owned by the business at t=0 (equipment, IP, inventory).",
        )
        inp.liabilities = st.number_input(
            "Liabilities ($)", value=inp.liabilities, step=1000.0, key=f"{prefix}_liabilities",
            help="Outstanding obligations at t=0 (excluding debt, which is below).",
        )
        inp.customer_count = int(st.number_input(
            "Initial Customers (c₀)", value=inp.customer_count, step=1, key=f"{prefix}_custs",
            help="Number of paying customers the business already has at t=0.",
        ))
        inp.total_addressable_market = int(st.number_input(
            "Total Addressable Market (TAM)", value=inp.total_addressable_market, step=1000, key=f"{prefix}_tam",
            help="Hard ceiling on total active customers. Simulation cannot exceed this.",
        ))
        inp.upfront_investment_costs = st.number_input(
            "Upfront Investment Costs ($)", value=inp.upfront_investment_costs, step=1000.0, key=f"{prefix}_upfront_inv",
            help="One-time capital needed at t=0 to start (build the funnel, set up infrastructure).",
        )
        inp.debt = st.number_input(
            "Debt ($)", value=inp.debt, step=1000.0, key=f"{prefix}_debt",
            help="Outstanding debt principal that accrues interest.",
        )
        inp.interest_rate = st.number_input(
            "Debt Interest Rate (%)", value=inp.interest_rate, step=0.5, key=f"{prefix}_ir",
            help="Annual interest rate on the debt above.",
        )

    # ── Sales ──────────────────────────────────────────────────────
    with st.sidebar.expander("Sales", expanded=False):
        inp.cost_to_sell = st.number_input(
            "Cost to Sell — c_s (% of P)", value=inp.cost_to_sell, step=1.0, key=f"{prefix}_cs",
            help="Sales commission to close one customer, as % of price (P).",
        )
        inp.time_to_sell = int(st.number_input(
            "Time to Sell — t_s (days)", value=inp.time_to_sell, step=1, key=f"{prefix}_tts",
            help="Days from lead creation to first purchase (sales cycle length).",
        ))
        inp.avg_deals_per_rep_per_month = st.number_input(
            "Avg Deals per Rep / Month", value=inp.avg_deals_per_rep_per_month, step=0.5, key=f"{prefix}_dprm",
            help="Average closed deals per sales rep per month (capacity).",
        )

    # ── Marketing Channels ─────────────────────────────────────────
    with st.sidebar.expander("Marketing Channels", expanded=True):
        st.subheader("Inbound")
        inp.use_inbound = st.checkbox("Enable Inbound", value=inp.use_inbound, key=f"{prefix}_use_in",
            help="Paid ads channel (Meta, Google, etc.).")
        if inp.use_inbound:
            inp.start_day_inbound = int(st.number_input(
                "Start Day", value=inp.start_day_inbound, step=30, key=f"{prefix}_sd_in",
                help="Day to activate this channel (0 = from start).",
            ))
            inp.media_spend = st.number_input(
                "Media Spend ($/month)", value=inp.media_spend, step=1000.0, key=f"{prefix}_ms",
                help="Monthly paid media budget.",
            )
            inp.cpm = st.number_input(
                "CPM ($)", value=inp.cpm, step=1.0, key=f"{prefix}_cpm",
                help="Cost per 1,000 impressions.",
            )
            inp.ctr = st.number_input(
                "CTR (%)", value=inp.ctr, step=0.1, key=f"{prefix}_ctr",
                help="Click-through rate: % of impressions that result in a click.",
            )
            inp.funnel_conversion_rate = st.number_input(
                "Funnel Conv (% click→lead)", value=inp.funnel_conversion_rate, step=0.5, key=f"{prefix}_fcr",
                help="% of clicks that become a lead (e.g. complete a form/quiz).",
            )
            inp.time_to_market_inbound = int(st.number_input(
                "Time to Market (days)", value=inp.time_to_market_inbound, step=1, key=f"{prefix}_ttm_in",
                help="Days from first impression to lead event.",
            ))
            inp.lead_conversion_rate_inbound = st.number_input(
                "Lead→Customer (%)", value=inp.lead_conversion_rate_inbound, step=1.0, key=f"{prefix}_lcr_in",
                help="% of inbound leads that become paying customers.",
            )

        st.divider()
        st.subheader("Outbound")
        inp.use_outbound = st.checkbox("Enable Outbound", value=inp.use_outbound, key=f"{prefix}_use_ob",
            help="Cold outreach channel (SDRs, cold email, LinkedIn).")
        if inp.use_outbound:
            inp.start_day_outbound = int(st.number_input(
                "Start Day", value=inp.start_day_outbound, step=30, key=f"{prefix}_sd_ob",
                help="Day to activate this channel (0 = from start).",
            ))
            inp.outbound_salary = st.number_input(
                "SDR Salary ($/month)", value=inp.outbound_salary, step=500.0, key=f"{prefix}_sal",
                help="Average monthly cost per SDR (salary + commission).",
            )
            inp.contacts_per_month = int(st.number_input(
                "Contacts per Month (per SDR)", value=inp.contacts_per_month, step=100, key=f"{prefix}_contacts",
                help="Number of cold contacts (emails/calls/messages) per SDR per month.",
            ))
            inp.number_of_sdrs = int(st.number_input(
                "Number of SDRs", value=inp.number_of_sdrs, step=1, key=f"{prefix}_sdrs",
                help="Total number of sales development reps.",
            ))
            inp.outbound_conversion_rate = st.number_input(
                "Contact→Lead (%)", value=inp.outbound_conversion_rate, step=0.5, key=f"{prefix}_ocr",
                help="% of cold contacts that respond and become a qualified lead.",
            )
            inp.time_to_market_outbound = int(st.number_input(
                "Time to Market (days)", value=inp.time_to_market_outbound, step=1, key=f"{prefix}_ttm_ob",
                help="Days from first contact to discovery call / qualified lead.",
            ))
            inp.lead_conversion_rate_outbound = st.number_input(
                "Lead→Customer (%)", value=inp.lead_conversion_rate_outbound, step=1.0, key=f"{prefix}_lcr_ob",
                help="% of outbound leads that become paying customers.",
            )

        st.divider()
        st.subheader("Organic")
        inp.use_organic = st.checkbox("Enable Organic", value=inp.use_organic, key=f"{prefix}_use_org",
            help="Content/SEO channel (compounding asset).")
        if inp.use_organic:
            inp.start_day_organic = int(st.number_input(
                "Start Day", value=inp.start_day_organic, step=30, key=f"{prefix}_sd_org",
                help="Day to activate this channel (0 = from start).",
            ))
            inp.organic_views_per_month = int(st.number_input(
                "Organic Views / Month", value=inp.organic_views_per_month, step=1000, key=f"{prefix}_org_views",
                help="Total organic content views per month.",
            ))
            inp.organic_view_to_lead_rate = st.number_input(
                "View→Lead (%)", value=inp.organic_view_to_lead_rate, step=0.1, key=f"{prefix}_org_conv",
                help="% of organic views that become a lead.",
            )
            inp.lead_to_customer_rate_organic = st.number_input(
                "Lead→Customer (%)", value=inp.lead_to_customer_rate_organic, step=1.0, key=f"{prefix}_lcr_org",
                help="% of organic leads that become paying customers.",
            )
            inp.time_to_market_organic = int(st.number_input(
                "Time to Market (days)", value=inp.time_to_market_organic, step=1, key=f"{prefix}_ttm_org",
                help="Days from view to lead event.",
            ))
            inp.organic_cost_per_month = st.number_input(
                "Organic Cost ($/month)", value=inp.organic_cost_per_month, step=500.0, key=f"{prefix}_org_cost",
                help="Monthly cost to produce organic content (writers, tools, etc.).",
            )

    # ── Product ────────────────────────────────────────────────────
    with st.sidebar.expander("Product", expanded=False):
        inp.price_of_offer = st.number_input(
            "Price of Offer — P ($)", value=inp.price_of_offer, step=100.0, key=f"{prefix}_price",
            help="Average total price of the offer over the contract period.",
        )
        inp.realization_rate = st.number_input(
            "Realization Rate (%)", value=inp.realization_rate, step=1.0, key=f"{prefix}_rr",
            help="% of price actually collected (after defaults, chargebacks, partial payments).",
        )
        inp.cost_to_fulfill = st.number_input(
            "Cost to Fulfill (% of P)", value=inp.cost_to_fulfill, step=1.0, key=f"{prefix}_cf",
            help="Cost to deliver the product/service, as % of price.",
        )
        inp.time_to_collect = int(st.number_input(
            "Time to Collect (days)", value=inp.time_to_collect, step=30, key=f"{prefix}_ttc",
            help="Days over which payment is collected (spread evenly). Critical for cash flow.",
        ))
        inp.refund_period = int(st.number_input(
            "Refund Period (days)", value=inp.refund_period, step=10, key=f"{prefix}_refp",
            help="Window during which customers can refund.",
        ))
        inp.refund_rate = st.number_input(
            "Refund Rate (%)", value=inp.refund_rate, step=0.5, key=f"{prefix}_refr",
            help="% of customers who refund within the refund period.",
        )
        inp.contract_length = int(st.number_input(
            "Contract Length (days)", value=inp.contract_length, step=30, key=f"{prefix}_cl",
            help="Time between first purchase and renewal decision.",
        ))

    # ── Renewals ───────────────────────────────────────────────────
    with st.sidebar.expander("Renewals", expanded=False):
        inp.churn_rate = st.number_input(
            "Churn Rate (%)", value=inp.churn_rate, step=5.0, key=f"{prefix}_churn",
            help="% of customers who do NOT renew at end of contract.",
        )
        if inp.churn_rate < 100:
            inp.price_of_renewal = st.number_input(
                "Price of Renewal ($)", value=inp.price_of_renewal, step=500.0, key=f"{prefix}_pren",
                help="Price charged at renewal (often higher than initial price).",
            )
            inp.cost_to_sell_renewal = st.number_input(
                "Cost to Sell Renewal (%)", value=inp.cost_to_sell_renewal, step=1.0, key=f"{prefix}_cs_ren",
                help="Sales commission to renew a customer, as % of renewal price.",
            )
            inp.cost_to_fulfill_renewal = st.number_input(
                "Cost to Fulfill Renewal (%)", value=inp.cost_to_fulfill_renewal, step=1.0, key=f"{prefix}_cf_ren",
                help="Cost to deliver the renewal, as % of renewal price.",
            )
            inp.time_to_collect_renewal = int(st.number_input(
                "Time to Collect Renewal (days)", value=inp.time_to_collect_renewal, step=10, key=f"{prefix}_ttc_ren",
                help="Days over which renewal payment is collected.",
            ))
            inp.renewal_rate_of_renewals = st.number_input(
                "Renewal of Renewals (%)", value=inp.renewal_rate_of_renewals, step=5.0, key=f"{prefix}_ror",
                help="Rate at which already-renewed customers renew again (perpetual retention).",
            )

    # ── Viral Component ────────────────────────────────────────────
    with st.sidebar.expander("Viral Component", expanded=False):
        inp.use_viral = st.checkbox("Enable Viral", value=inp.use_viral, key=f"{prefix}_use_viral",
            help="Referrals / network effects channel.")
        if inp.use_viral:
            inp.invites_per_customer = st.number_input(
                "Invites per Customer", value=inp.invites_per_customer, step=1.0, key=f"{prefix}_invites",
                help="Average number of referrals each active customer generates.",
            )
            inp.conversion_rate_per_invite = st.number_input(
                "Invite Conv (%)", value=inp.conversion_rate_per_invite, step=1.0, key=f"{prefix}_viral_conv",
                help="% of invites that convert to a customer. K-value = invites × conv. K>1 = exponential growth.",
            )
            inp.viral_time = int(st.number_input(
                "Viral Time (days)", value=inp.viral_time, step=5, key=f"{prefix}_viral_time",
                help="Average time for a referral to convert into a customer.",
            ))
            inp.viral_start = int(st.number_input(
                "Viral Start (day)", value=inp.viral_start, step=30, key=f"{prefix}_viral_start",
                help="Day at which the referral mechanism activates.",
            ))
            inp.cost_to_sell_viral = st.number_input(
                "Cost to Sell Viral (%)", value=inp.cost_to_sell_viral, step=1.0, key=f"{prefix}_cs_viral",
                help="Sales commission for viral conversions, as % of price.",
            )
            inp.cost_to_market_viral = st.number_input(
                "Cost to Market Viral (%)", value=inp.cost_to_market_viral, step=1.0, key=f"{prefix}_cm_viral",
                help="Referral bonus / cost per successful referral, as % of price.",
            )

    # ── Administration ─────────────────────────────────────────────
    with st.sidebar.expander("Administration", expanded=False):
        inp.transaction_fee = st.number_input(
            "Transaction Fee (%)", value=inp.transaction_fee, step=0.1, key=f"{prefix}_tf",
            help="Payment processor fee (typically 2.9% for Stripe).",
        )
        inp.fixed_costs_per_month = st.number_input(
            "Fixed Costs ($/month)", value=inp.fixed_costs_per_month, step=1000.0, key=f"{prefix}_fc",
            help="Rent, salaries (non-SDR), engineering, tools, etc.",
        )
        inp.fixed_cost_increase_per_100_customers = st.number_input(
            "FC Increase per 100 Customers ($/month)", value=inp.fixed_cost_increase_per_100_customers, step=500.0, key=f"{prefix}_fc_scale",
            help="Additional fixed cost per 100 active customers (support, infra scaling).",
        )

    # ── Valuation ──────────────────────────────────────────────────
    with st.sidebar.expander("Valuation Parameters", expanded=False):
        inp.tax_rate = st.number_input(
            "Tax Rate (%)", value=inp.tax_rate, step=1.0, key=f"{prefix}_tax",
            help="Effective corporate tax rate on positive EBIT.",
        )
        inp.discount_rate = st.number_input(
            "Discount Rate (%)", value=inp.discount_rate, step=0.5, key=f"{prefix}_dr",
            help="Required rate of return / WACC for DCF.",
        )
        inp.perpetual_growth_rate = st.number_input(
            "Perpetual Growth (%)", value=inp.perpetual_growth_rate, step=0.5, key=f"{prefix}_pgr",
            help="Long-term steady-state growth rate for terminal value (Gordon Growth Model).",
        )
        inp.time_max = int(st.number_input(
            "Simulation Period (days)", value=inp.time_max, step=100, key=f"{prefix}_tmax",
            help="Total number of days to simulate.",
        ))
        inp.number_of_shares = int(st.number_input(
            "Number of Shares", value=inp.number_of_shares, step=100_000, key=f"{prefix}_shares",
            help="Total fully-diluted share count for share price calculation.",
        ))
        inp.enterprise_multiple_ebitda = st.number_input(
            "EBITDA Multiple", value=inp.enterprise_multiple_ebitda, step=1.0, key=f"{prefix}_ebitda_mult",
            help="EV/EBITDA multiple for the alternative valuation method.",
        )

    return inp
