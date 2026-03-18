from __future__ import annotations

import streamlit as st

from engine.inputs import ModelInputs


def render_sidebar() -> ModelInputs:
    """Render all input sections in the sidebar and return a populated ModelInputs."""
    st.sidebar.title("Model Inputs")

    inp = ModelInputs()

    # ── Starting State ──────────────────────────────────────────────
    with st.sidebar.expander("Starting State", expanded=False):
        st.caption("Starting state of your company at time t=0.")
        inp.cash_in_bank = st.number_input(
            "Cash in Bank ($)", value=0.0, step=1000.0, key="cash_in_bank",
            help="Cash in the bank at time t=0.",
        )
        inp.assets = st.number_input(
            "Assets ($)", value=0.0, step=1000.0, key="assets",
        )
        inp.liabilities = st.number_input(
            "Liabilities ($)", value=0.0, step=1000.0, key="liabilities",
        )
        inp.customer_count = int(st.number_input(
            "Initial Customers (c₀)", value=0, step=1, key="customer_count",
            help="Customer count at time t=0.",
        ))
        inp.total_addressable_market = int(st.number_input(
            "Total Addressable Market (TAM)", value=100_000, step=1000, key="tam",
        ))
        inp.upfront_investment_costs = st.number_input(
            "Upfront Investment Costs ($)", value=0.0, step=1000.0, key="upfront",
            help="Up-front capital needed to start. Includes building the mechanism and sales funnel.",
        )
        inp.debt = st.number_input(
            "Debt ($)", value=0.0, step=1000.0, key="debt",
            help="Sum of liabilities / outstanding debt.",
        )
        inp.interest_rate = st.number_input(
            "Debt Interest Rate (%)", value=6.0, step=0.5, key="interest_rate",
            help="Annual interest rate on the debt.",
        )

    # ── Sales ───────────────────────────────────────────────────────
    with st.sidebar.expander("Sales", expanded=False):
        inp.cost_to_sell = st.number_input(
            "Cost to Sell — c_s (% of P)", value=15.0, step=1.0, key="cost_to_sell",
            help="Commission cost to turn a lead into a closed account, as % of Price.",
        )
        inp.time_to_sell = int(st.number_input(
            "Time to Sell — t_s (days)", value=20, step=1, key="time_to_sell",
            help="Days between lead creation and first purchase (sales cycle).",
        ))
        inp.avg_deals_per_rep_per_month = st.number_input(
            "Avg Deals per Sales Rep / Month", value=1.0, step=0.5, key="deals_per_rep",
        )

    # ── Marketing Channels ──────────────────────────────────────────
    with st.sidebar.expander("Marketing Channels", expanded=True):
        st.subheader("Inbound")
        inp.use_inbound = st.checkbox("Enable Inbound", value=True, key="use_inbound")
        if inp.use_inbound:
            inp.media_spend = st.number_input(
                "Media Spend ($/month)", value=50_000.0, step=1000.0, key="media_spend",
                help="Monthly paid media budget.",
            )
            inp.cpm = st.number_input(
                "CPM — Cost per 1000 Impressions ($)", value=55.0, step=1.0, key="cpm",
                help="Cost to show your ad 1,000 times.",
            )
            inp.ctr = st.number_input(
                "CTR — Click-Through Rate (%)", value=1.0, step=0.1, key="ctr",
                help="Percentage of impressions that result in a click.",
            )
            inp.funnel_conversion_rate = st.number_input(
                "Funnel Conversion Rate (% click→lead)", value=2.0, step=0.5, key="funnel_conv",
                help="Percentage of clicks that become a lead (e.g. complete a quiz).",
            )
            inp.time_to_market_inbound = int(st.number_input(
                "Time to Market — Inbound (days)", value=1, step=1, key="ttm_inbound",
                help="Days from first ad impression to lead event.",
            ))
            inp.lead_conversion_rate_inbound = st.number_input(
                "Lead→Customer Rate — Inbound (%)", value=8.0, step=1.0, key="lcr_inbound",
                help="Percentage of inbound leads that become paying customers.",
            )

        st.divider()
        st.subheader("Outbound")
        inp.use_outbound = st.checkbox("Enable Outbound", value=False, key="use_outbound")
        if inp.use_outbound:
            inp.outbound_salary = st.number_input(
                "SDR Salary ($/month)", value=3_000.0, step=500.0, key="ob_salary",
                help="Average monthly salary/commission per SDR.",
            )
            inp.contacts_per_month = int(st.number_input(
                "Contacts per Month (per SDR)", value=2_000, step=100, key="contacts",
                help="Emails, calls, LinkedIn messages per SDR per month.",
            ))
            inp.number_of_sdrs = int(st.number_input(
                "Number of SDRs", value=40, step=1, key="sdrs",
            ))
            inp.outbound_conversion_rate = st.number_input(
                "Contact→Lead Rate (%)", value=2.0, step=0.5, key="ob_conv",
                help="Percentage of contacts that become leads.",
            )
            inp.time_to_market_outbound = int(st.number_input(
                "Time to Market — Outbound (days)", value=11, step=1, key="ttm_outbound",
                help="Days from first contact to discovery call.",
            ))
            inp.lead_conversion_rate_outbound = st.number_input(
                "Lead→Customer Rate — Outbound (%)", value=8.0, step=1.0, key="lcr_outbound",
            )

        st.divider()
        st.subheader("Organic")
        inp.use_organic = st.checkbox("Enable Organic", value=False, key="use_organic")
        if inp.use_organic:
            inp.organic_views_per_month = int(st.number_input(
                "Organic Views / Month", value=0, step=1000, key="org_views",
            ))
            inp.organic_view_to_lead_rate = st.number_input(
                "View→Lead Rate (%)", value=0.0, step=0.1, key="org_conv",
            )
            inp.lead_to_customer_rate_organic = st.number_input(
                "Lead→Customer Rate — Organic (%)", value=0.0, step=1.0, key="lcr_organic",
            )
            inp.time_to_market_organic = int(st.number_input(
                "Time to Market — Organic (days)", value=30, step=1, key="ttm_organic",
            ))
            inp.organic_cost_per_month = st.number_input(
                "Organic Cost ($/month)", value=0.0, step=500.0, key="org_cost",
            )

    # ── Product ─────────────────────────────────────────────────────
    with st.sidebar.expander("Product", expanded=False):
        inp.price_of_offer = st.number_input(
            "Price of Offer — P ($)", value=5_000.0, step=100.0, key="price",
            help="Average total price over the contract period.",
        )
        inp.realization_rate = st.number_input(
            "Realization Rate — RR (%)", value=93.0, step=1.0, key="rr",
            help="Cash collected / cash requested. Accounts for payment defaults.",
        )
        inp.cost_to_fulfill = st.number_input(
            "Cost to Fulfill — c_f (% of P)", value=10.0, step=1.0, key="c_f",
            help="Cost to deliver the product/service, as % of P.",
        )
        inp.time_to_collect = int(st.number_input(
            "Time to Collect — t_c (days)", value=300, step=30, key="t_c",
            help="Days between first purchase and full payment collection.",
        ))
        inp.refund_period = int(st.number_input(
            "Refund Period (days)", value=60, step=10, key="refund_period",
        ))
        inp.refund_rate = st.number_input(
            "Refund Rate (%)", value=2.0, step=0.5, key="refund_rate",
        )
        inp.contract_length = int(st.number_input(
            "Contract Length (days)", value=365, step=30, key="contract_length",
            help="Time between first purchase and expected renewal.",
        ))

    # ── Renewals ────────────────────────────────────────────────────
    with st.sidebar.expander("Renewals", expanded=False):
        inp.churn_rate = st.number_input(
            "Churn Rate (%)", value=50.0, step=5.0, key="churn",
            help="Percentage of customers who do NOT renew after contract ends.",
        )
        if inp.churn_rate < 100:
            inp.price_of_renewal = st.number_input(
                "Price of Renewal ($)", value=7_000.0, step=500.0, key="p_renewal",
            )
            inp.cost_to_sell_renewal = st.number_input(
                "Cost to Sell Renewal (% of renewal price)", value=10.0, step=1.0, key="c_s_ren",
            )
            inp.cost_to_fulfill_renewal = st.number_input(
                "Cost to Fulfill Renewal (% of renewal price)", value=10.0, step=1.0, key="c_f_ren",
            )
            inp.time_to_collect_renewal = int(st.number_input(
                "Time to Collect Renewal (days)", value=30, step=10, key="t_c_ren",
            ))
            inp.renewal_rate_of_renewals = st.number_input(
                "Renewal Rate of Renewals (%)", value=50.0, step=5.0, key="ren_of_ren",
                help="Rate at which already-renewed customers renew again.",
            )

    # ── Viral Component ─────────────────────────────────────────────
    with st.sidebar.expander("Viral Component", expanded=False):
        inp.use_viral = st.checkbox("Enable Viral", value=False, key="use_viral")
        if inp.use_viral:
            inp.invites_per_customer = st.number_input(
                "Invites per Customer", value=0.0, step=1.0, key="invites",
                help="Average referral requests per customer during active time.",
            )
            inp.conversion_rate_per_invite = st.number_input(
                "Invite Conversion Rate (%)", value=5.0, step=1.0, key="viral_conv",
            )
            inp.viral_time = int(st.number_input(
                "Viral Time (days)", value=20, step=5, key="viral_time",
                help="Average time for a referral to convert.",
            ))
            inp.viral_start = int(st.number_input(
                "Viral Start (day)", value=0, step=30, key="viral_start",
                help="Day at which referral mechanism begins.",
            ))
            inp.cost_to_sell_viral = st.number_input(
                "Cost to Sell Viral (% of P)", value=15.0, step=1.0, key="c_s_viral",
            )
            inp.cost_to_market_viral = st.number_input(
                "Cost to Market Viral (% of P)", value=10.0, step=1.0, key="c_m_viral",
                help="Referral bonus / cost per successful referral, as % of P.",
            )

    # ── Administration ──────────────────────────────────────────────
    with st.sidebar.expander("Administration", expanded=False):
        inp.transaction_fee = st.number_input(
            "Transaction Fee (%)", value=2.9, step=0.1, key="tf",
            help="Payment processor fee (typically 2.9%).",
        )
        inp.fixed_costs_per_month = st.number_input(
            "Fixed Costs ($/month)", value=10_000.0, step=1000.0, key="fc",
            help="Rent, salaries, engineering, tools, etc.",
        )
        inp.fixed_cost_increase_per_100_customers = st.number_input(
            "FC Increase per 100 Customers ($/month)", value=0.0, step=500.0, key="fc_scale",
            help="Additional fixed cost per 100 active customers.",
        )

    # ── Valuation ───────────────────────────────────────────────────
    with st.sidebar.expander("Valuation Parameters", expanded=False):
        inp.tax_rate = st.number_input(
            "Tax Rate (%)", value=22.0, step=1.0, key="tax",
        )
        inp.inflation_rate = st.number_input(
            "Inflation Rate (%)", value=2.0, step=0.5, key="inflation",
        )
        inp.time_max = int(st.number_input(
            "Simulation Period (days)", value=2500, step=100, key="time_max",
            help="Total number of days to simulate.",
        ))
        inp.number_of_shares = int(st.number_input(
            "Number of Shares", value=1_000_000, step=100_000, key="shares",
        ))

        st.subheader("DCF Method")
        inp.projection_period_dcf = int(st.number_input(
            "DCF Projection Period (days)", value=1825, step=365, key="proj_dcf",
            help="Period over which FCF is discounted.",
        ))
        inp.discount_rate = st.number_input(
            "Discount Rate (%)", value=9.0, step=0.5, key="r_disc",
            help="Required rate of return / WACC.",
        )
        inp.perpetual_growth_rate = st.number_input(
            "Perpetual Growth Rate (%)", value=2.0, step=0.5, key="r_growth",
            help="Long-term steady-state growth rate for terminal value.",
        )

        st.subheader("EBITDA Multiple")
        inp.enterprise_multiple_ebitda = st.number_input(
            "EBITDA Multiple", value=14.0, step=1.0, key="ebitda_mult",
            help="Enterprise value = EBITDA × this multiple.",
        )
        inp.projection_period_ebitda = int(st.number_input(
            "EBITDA Projection Period (days)", value=1825, step=365, key="proj_ebitda",
        ))

    return inp
