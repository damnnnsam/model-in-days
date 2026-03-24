import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Deal Modeling Tool",
    layout="wide",
    initial_sidebar_state="expanded",
)

from engine.inputs import ModelInputs
from engine.simulation import run_simulation, to_daily_df
from engine.valuation import compute_valuation
import importlib
import engine.metrics as _metrics_mod
_metrics_mod = importlib.reload(_metrics_mod)
from engine.metrics import compute_kpis
from ui.charts import COLORS, DAILY_LAYOUT
from model_2_operator.deal import DealTerms, Bonus, compute_deal
from model_2_operator.compensation import (
    CompensationStructure, DecayStep, RetainerStep,
    compute_compensation, ALL_PRESETS,
)

import base64, zlib, json as _json


def _encode_deal_state() -> str:
    """Compress all sidebar input keys into a URL-safe string."""
    state = {}
    for k, v in st.session_state.items():
        if any(k.startswith(p) for p in ("sb_", "b_", "a_", "d_")):
            # Only serialize simple types
            if isinstance(v, (int, float, str, bool)):
                state[k] = v
    data = _json.dumps(state, separators=(",", ":"))
    compressed = zlib.compress(data.encode(), level=9)
    return base64.urlsafe_b64encode(compressed).decode()


def _decode_deal_state(encoded: str):
    """Restore sidebar inputs from a URL-safe string."""
    try:
        compressed = base64.urlsafe_b64decode(encoded)
        state = _json.loads(zlib.decompress(compressed).decode())
        for k, v in state.items():
            st.session_state[k] = v
    except Exception:
        pass


# ── Restore state from URL if present ──
if "d" in st.query_params and "deal_loaded" not in st.session_state:
    _decode_deal_state(st.query_params["d"])
    st.session_state["deal_loaded"] = True


st.markdown("# Deal Modeling Tool")
st.markdown(
    "<span style='color:#666;font-size:14px'>Model both sides of the engagement. "
    "Find the deal structure where operator and client both win.</span>",
    unsafe_allow_html=True,
)


def _fd(v):
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:,.1f}K"
    return f"${v:,.0f}"


# ── Reusable state renderer ─────────────────────────────────────────

_DEFAULTS = dict(
    cash_in_bank=0.0, customer_count=0, total_addressable_market=100_000,
    upfront_investment_costs=0.0, debt=0.0, interest_rate=6.0,
    price_of_offer=10000.0, realization_rate=93.0,
    cost_to_fulfill=60.0, cost_to_sell=15.0,
    time_to_collect=28, time_to_sell=20,
    contract_length=30, refund_period=60, refund_rate=2.0,
    churn_rate=10.0, price_of_renewal=10000.0,
    cost_to_sell_renewal=10.0, cost_to_fulfill_renewal=40.0,
    time_to_collect_renewal=30, renewal_rate_of_renewals=90.0,
    use_inbound=False, media_spend=50000.0, cpm=55.0, ctr=1.0,
    funnel_conversion_rate=2.0, time_to_market_inbound=1, lead_conversion_rate_inbound=8.0,
    use_outbound=True, number_of_sdrs=1, outbound_salary=3500.0,
    contacts_per_month=25000, outbound_conversion_rate=0.15,
    lead_conversion_rate_outbound=4.0, time_to_market_outbound=11,
    use_organic=False, organic_views_per_month=0, organic_view_to_lead_rate=0.0,
    lead_to_customer_rate_organic=0.0, time_to_market_organic=30, organic_cost_per_month=0.0,
    use_viral=False, invites_per_customer=0.0, conversion_rate_per_invite=5.0,
    viral_time=20, viral_start=0, cost_to_sell_viral=15.0, cost_to_market_viral=10.0,
    transaction_fee=2.9, fixed_costs_per_month=10000.0,
    fixed_cost_increase_per_100_customers=0.0,
    tax_rate=22.0, discount_rate=9.0, perpetual_growth_rate=2.0,
    time_max=2500,
)


def _render_state(prefix: str, label: str, before: ModelInputs | None = None, **overrides) -> ModelInputs:
    """Render a full model input set in the sidebar and return ModelInputs.
    If `before` is provided, Starting State is inherited (not rendered) and
    each input's tooltip shows the Before value."""
    D = {**_DEFAULTS, **overrides}
    p = prefix

    def _bv(field, fmt="$"):
        """Build 'Before: ...' suffix for help tooltips."""
        if before is None:
            return ""
        v = getattr(before, field, None)
        if v is None:
            return ""
        if fmt == "$":
            return f" · Before: ${v:,.0f}"
        elif fmt == "%":
            return f" · Before: {v}%"
        return f" · Before: {v}"

    # Starting State: only render for Before; After inherits from Before
    if before is not None:
        # Inherit starting state from Before
        cash = before.cash_in_bank
        customer_count = before.customer_count
        tam = before.total_addressable_market
        upfront = before.upfront_investment_costs
        debt = before.debt
        interest = before.interest_rate
    else:
        with st.sidebar.expander(f"{label} — Starting State", expanded=False):
            cash = st.number_input("Cash in Bank ($)", value=float(D["cash_in_bank"]), step=5000.0, key=f"{p}_cash",
                                   help="Cash on hand at t=0.")
            customer_count = int(st.number_input("Current Customers", value=int(D["customer_count"]), step=1, key=f"{p}_cc",
                                                 help="Active customers at t=0."))
            tam = int(st.number_input("TAM", value=int(D["total_addressable_market"]), step=10000, key=f"{p}_tam",
                                      help="Total addressable market size."))
            upfront = st.number_input("Upfront Investment ($)", value=float(D["upfront_investment_costs"]), step=5000.0, key=f"{p}_upfront",
                                      help="One-time startup cost (infrastructure, setup).")
            debt = st.number_input("Debt ($)", value=float(D["debt"]), step=5000.0, key=f"{p}_debt",
                                   help="Outstanding debt at t=0.")
            interest = st.number_input("Interest Rate (%)", value=float(D["interest_rate"]), step=0.5, key=f"{p}_interest",
                                       help="Annual interest rate on debt.")

    with st.sidebar.expander(f"{label} — Product", expanded=(p == "b")):
        price = st.number_input("Price ($)", value=float(D["price_of_offer"]), step=1000.0, key=f"{p}_price",
                                help=f"Total contract price (P).{_bv('price_of_offer')}")
        realization = st.number_input("Realization Rate (%)", value=float(D["realization_rate"]), step=1.0, key=f"{p}_rr",
                                      help=f"% of price actually collected (payment defaults).{_bv('realization_rate', '%')}")
        cost_fulfill = st.number_input("Cost to Fulfill (%)", value=float(D["cost_to_fulfill"]), step=5.0, key=f"{p}_cf",
                                       help=f"Delivery cost as % of P.{_bv('cost_to_fulfill', '%')}")
        cost_sell = st.number_input("Cost to Sell (%)", value=float(D["cost_to_sell"]), step=1.0, key=f"{p}_cs",
                                    help=f"Sales commission as % of P.{_bv('cost_to_sell', '%')}")
        time_collect = int(st.number_input("Time to Collect (days)", value=int(D["time_to_collect"]), step=7, key=f"{p}_tc",
                                           help=f"Days from sale to full payment.{_bv('time_to_collect', 'd')}"))
        time_sell = int(st.number_input("Time to Sell (days)", value=int(D["time_to_sell"]), step=5, key=f"{p}_tts",
                                        help=f"Sales cycle length.{_bv('time_to_sell', 'd')}"))
        contract = int(st.number_input("Contract Length (days)", value=int(D["contract_length"]), step=30, key=f"{p}_cl",
                                       help=f"Days between purchase and renewal.{_bv('contract_length', 'd')}"))
        refund_period = int(st.number_input("Refund Period (days)", value=int(D["refund_period"]), step=10, key=f"{p}_refper",
                                            help=f"Window for refund requests.{_bv('refund_period', 'd')}"))
        refund_rate = st.number_input("Refund Rate (%)", value=float(D["refund_rate"]), step=0.5, key=f"{p}_refr",
                                      help=f"% of customers who refund.{_bv('refund_rate', '%')}")

    with st.sidebar.expander(f"{label} — Renewals", expanded=False):
        churn = st.number_input("Churn Rate (%)", value=float(D["churn_rate"]), step=5.0, key=f"{p}_churn",
                                help=f"% who don't renew after contract ends.{_bv('churn_rate', '%')}")
        p_renewal = st.number_input("Price of Renewal ($)", value=float(D["price_of_renewal"]), step=1000.0, key=f"{p}_pren",
                                    help=f"Renewal contract price.{_bv('price_of_renewal')}")
        cs_renewal = st.number_input("Cost to Sell Renewal (%)", value=float(D["cost_to_sell_renewal"]), step=1.0, key=f"{p}_csren",
                                     help=f"Sales cost as % of renewal price.{_bv('cost_to_sell_renewal', '%')}")
        cf_renewal = st.number_input("Cost to Fulfill Renewal (%)", value=float(D["cost_to_fulfill_renewal"]), step=5.0, key=f"{p}_cfren",
                                     help=f"Delivery cost as % of renewal price.{_bv('cost_to_fulfill_renewal', '%')}")
        tc_renewal = int(st.number_input("Time to Collect Renewal (days)", value=int(D["time_to_collect_renewal"]), step=10, key=f"{p}_tcren",
                                         help=f"Days to collect renewal payment.{_bv('time_to_collect_renewal', 'd')}"))
        ren_of_ren = st.number_input("Renewal of Renewals (%)", value=float(D["renewal_rate_of_renewals"]), step=5.0, key=f"{p}_ror",
                                     help=f"% of renewers who renew again.{_bv('renewal_rate_of_renewals', '%')}")

    with st.sidebar.expander(f"{label} — Channels", expanded=(p == "b")):
        st.subheader("Inbound")
        use_inbound = st.checkbox("Enable Inbound", value=bool(D["use_inbound"]), key=f"{p}_use_inbound")
        if use_inbound:
            media_spend = st.number_input("Media Spend ($/mo)", value=float(D["media_spend"]), step=5000.0, key=f"{p}_media",
                                          help=f"Monthly paid media budget.{_bv('media_spend')}")
            cpm = st.number_input("CPM ($)", value=float(D["cpm"]), step=5.0, key=f"{p}_cpm",
                                  help=f"Cost per 1000 ad impressions.{_bv('cpm')}")
            ctr = st.number_input("CTR (%)", value=float(D["ctr"]), step=0.1, key=f"{p}_ctr",
                                  help=f"% of impressions that get clicked.{_bv('ctr', '%')}")
            funnel_conv = st.number_input("Funnel Conv (%)", value=float(D["funnel_conversion_rate"]), step=0.5, key=f"{p}_funnel",
                                          help=f"% of clicks that become leads.{_bv('funnel_conversion_rate', '%')}")
            ttm_inbound = int(st.number_input("TTM Inbound (days)", value=int(D["time_to_market_inbound"]), step=1, key=f"{p}_ttm_in",
                                              help=f"Days from impression to lead.{_bv('time_to_market_inbound', 'd')}"))
            lcr_inbound = st.number_input("Lead→Customer (%)", value=float(D["lead_conversion_rate_inbound"]), step=1.0, key=f"{p}_lcr_in",
                                          help=f"% of inbound leads that close.{_bv('lead_conversion_rate_inbound', '%')}")
        else:
            media_spend, cpm, ctr = float(D["media_spend"]), float(D["cpm"]), float(D["ctr"])
            funnel_conv, ttm_inbound, lcr_inbound = float(D["funnel_conversion_rate"]), int(D["time_to_market_inbound"]), float(D["lead_conversion_rate_inbound"])

        st.divider()
        st.subheader("Outbound")
        use_outbound = st.checkbox("Enable Outbound", value=bool(D["use_outbound"]), key=f"{p}_use_outbound")
        if use_outbound:
            sdrs = int(st.number_input("SDRs", value=int(D["number_of_sdrs"]), step=1, key=f"{p}_sdrs",
                                       help=f"Number of sales development reps.{_bv('number_of_sdrs', 'd')}"))
            salary = st.number_input("SDR Salary ($/mo)", value=float(D["outbound_salary"]), step=500.0, key=f"{p}_sal",
                                     help=f"Monthly salary/commission per SDR.{_bv('outbound_salary')}")
            contacts = int(st.number_input("Contacts/Month", value=int(D["contacts_per_month"]), step=5000, key=f"{p}_contacts",
                                           help=f"Emails/calls/messages per SDR per month.{_bv('contacts_per_month', 'd')}"))
            reply = st.number_input("Reply Rate (%)", value=float(D["outbound_conversion_rate"]), step=0.05, key=f"{p}_reply",
                                    help=f"% of contacts that become leads.{_bv('outbound_conversion_rate', '%')}")
            lcr_outbound = st.number_input("Lead→Customer (%)", value=float(D["lead_conversion_rate_outbound"]), step=1.0, key=f"{p}_lcr_out",
                                           help=f"% of outbound leads that close.{_bv('lead_conversion_rate_outbound', '%')}")
            ttm_outbound = int(st.number_input("TTM Outbound (days)", value=int(D["time_to_market_outbound"]), step=1, key=f"{p}_ttm_out",
                                               help=f"Days from first contact to discovery.{_bv('time_to_market_outbound', 'd')}"))
        else:
            sdrs, salary, contacts = int(D["number_of_sdrs"]), float(D["outbound_salary"]), int(D["contacts_per_month"])
            reply, lcr_outbound, ttm_outbound = float(D["outbound_conversion_rate"]), float(D["lead_conversion_rate_outbound"]), int(D["time_to_market_outbound"])

        st.divider()
        st.subheader("Organic")
        use_organic = st.checkbox("Enable Organic", value=bool(D["use_organic"]), key=f"{p}_use_organic")
        if use_organic:
            org_views = int(st.number_input("Views/Month", value=int(D["organic_views_per_month"]), step=1000, key=f"{p}_org_views",
                                            help=f"Monthly organic content views.{_bv('organic_views_per_month', 'd')}"))
            org_vl = st.number_input("View→Lead (%)", value=float(D["organic_view_to_lead_rate"]), step=0.1, key=f"{p}_org_vl",
                                     help=f"% of views that become leads.{_bv('organic_view_to_lead_rate', '%')}")
            org_lcr = st.number_input("Lead→Customer (%)", value=float(D["lead_to_customer_rate_organic"]), step=1.0, key=f"{p}_org_lcr",
                                      help=f"% of organic leads that close.{_bv('lead_to_customer_rate_organic', '%')}")
            org_ttm = int(st.number_input("TTM Organic (days)", value=int(D["time_to_market_organic"]), step=1, key=f"{p}_org_ttm",
                                          help=f"Days from view to lead.{_bv('time_to_market_organic', 'd')}"))
            org_cost = st.number_input("Organic Cost ($/mo)", value=float(D["organic_cost_per_month"]), step=500.0, key=f"{p}_org_cost",
                                       help=f"Monthly content/SEO cost.{_bv('organic_cost_per_month')}")
        else:
            org_views, org_vl, org_lcr = int(D["organic_views_per_month"]), float(D["organic_view_to_lead_rate"]), float(D["lead_to_customer_rate_organic"])
            org_ttm, org_cost = int(D["time_to_market_organic"]), float(D["organic_cost_per_month"])

    with st.sidebar.expander(f"{label} — Viral", expanded=False):
        use_viral = st.checkbox("Enable Viral", value=bool(D["use_viral"]), key=f"{p}_use_viral")
        if use_viral:
            invites = st.number_input("Invites/Customer", value=float(D["invites_per_customer"]), step=1.0, key=f"{p}_invites",
                                      help=f"Referrals per active customer.{_bv('invites_per_customer', 'd')}")
            viral_conv = st.number_input("Invite Conv (%)", value=float(D["conversion_rate_per_invite"]), step=1.0, key=f"{p}_viral_conv",
                                         help=f"% of referrals that convert.{_bv('conversion_rate_per_invite', '%')}")
            viral_time = int(st.number_input("Viral Time (days)", value=int(D["viral_time"]), step=5, key=f"{p}_viral_time",
                                             help=f"Days for a referral to convert.{_bv('viral_time', 'd')}"))
            viral_start = int(st.number_input("Viral Start (day)", value=int(D["viral_start"]), step=30, key=f"{p}_viral_start",
                                              help=f"Day referral program begins.{_bv('viral_start', 'd')}"))
            cs_viral = st.number_input("Cost to Sell Viral (%)", value=float(D["cost_to_sell_viral"]), step=1.0, key=f"{p}_cs_viral",
                                       help=f"Commission on referral sales (% of P).{_bv('cost_to_sell_viral', '%')}")
            cm_viral = st.number_input("Cost to Market Viral (%)", value=float(D["cost_to_market_viral"]), step=1.0, key=f"{p}_cm_viral",
                                       help=f"Referral bonus cost (% of P).{_bv('cost_to_market_viral', '%')}")
        else:
            invites, viral_conv = float(D["invites_per_customer"]), float(D["conversion_rate_per_invite"])
            viral_time, viral_start = int(D["viral_time"]), int(D["viral_start"])
            cs_viral, cm_viral = float(D["cost_to_sell_viral"]), float(D["cost_to_market_viral"])

    # Admin & Valuation: only render for Before; After inherits
    if before is not None:
        txn_fee = before.transaction_fee
        fc = before.fixed_costs_per_month
        fc_scale = before.fixed_cost_increase_per_100_customers
        tax = before.tax_rate
        disc = before.discount_rate
        growth = before.perpetual_growth_rate
        time_max = before.time_max
    else:
        with st.sidebar.expander(f"{label} — Admin & Valuation", expanded=False):
            txn_fee = st.number_input("Transaction Fee (%)", value=float(D["transaction_fee"]), step=0.1, key=f"{p}_txn",
                                      help="Payment processor fee (e.g. Stripe 2.9%).")
            fc = st.number_input("Fixed Costs ($/mo)", value=float(D["fixed_costs_per_month"]), step=1000.0, key=f"{p}_fc",
                                 help="Base monthly overhead (rent, salaries, tools).")
            fc_scale = st.number_input("FC per 100 Cust ($/mo)", value=float(D["fixed_cost_increase_per_100_customers"]), step=500.0, key=f"{p}_fcs",
                                       help="Additional overhead per 100 active customers.")
            tax = st.number_input("Tax Rate (%)", value=float(D["tax_rate"]), step=1.0, key=f"{p}_tax",
                                  help="Corporate tax rate on positive EBIT.")
            disc = st.number_input("Discount Rate (%)", value=float(D["discount_rate"]), step=0.5, key=f"{p}_disc",
                                   help="WACC / required rate of return.")
            growth = st.number_input("Perpetual Growth (%)", value=float(D["perpetual_growth_rate"]), step=0.5, key=f"{p}_growth",
                                     help="Long-term growth for terminal value.")
            time_max = int(st.number_input("Simulation Days", value=int(D["time_max"]), step=100, key=f"{p}_tmax",
                                           help="Total simulation period."))

    return ModelInputs(
        cash_in_bank=cash, customer_count=customer_count,
        total_addressable_market=tam, upfront_investment_costs=upfront,
        debt=debt, interest_rate=interest,
        price_of_offer=price, realization_rate=realization,
        cost_to_fulfill=cost_fulfill, cost_to_sell=cost_sell,
        time_to_collect=time_collect, time_to_sell=time_sell,
        contract_length=contract, refund_period=refund_period, refund_rate=refund_rate,
        churn_rate=churn, price_of_renewal=p_renewal,
        cost_to_sell_renewal=cs_renewal, cost_to_fulfill_renewal=cf_renewal,
        time_to_collect_renewal=tc_renewal, renewal_rate_of_renewals=ren_of_ren,
        use_inbound=use_inbound, media_spend=media_spend, cpm=cpm, ctr=ctr,
        funnel_conversion_rate=funnel_conv, time_to_market_inbound=ttm_inbound,
        lead_conversion_rate_inbound=lcr_inbound,
        use_outbound=use_outbound, number_of_sdrs=sdrs, outbound_salary=salary,
        contacts_per_month=contacts, outbound_conversion_rate=reply,
        lead_conversion_rate_outbound=lcr_outbound, time_to_market_outbound=ttm_outbound,
        use_organic=use_organic, organic_views_per_month=org_views,
        organic_view_to_lead_rate=org_vl, lead_to_customer_rate_organic=org_lcr,
        time_to_market_organic=org_ttm, organic_cost_per_month=org_cost,
        use_viral=use_viral, invites_per_customer=invites,
        conversion_rate_per_invite=viral_conv, viral_time=viral_time,
        viral_start=viral_start, cost_to_sell_viral=cs_viral, cost_to_market_viral=cm_viral,
        transaction_fee=txn_fee, fixed_costs_per_month=fc,
        fixed_cost_increase_per_100_customers=fc_scale,
        tax_rate=tax, discount_rate=disc, perpetual_growth_rate=growth,
        time_max=time_max,
    )


# ── Sidebar: Two States ─────────────────────────────────────────────
st.sidebar.title("Current Business")
inp_before = _render_state("b", "Before")

st.sidebar.markdown("---")
st.sidebar.title("After Operator")
inp_after = _render_state("a", "After", before=inp_before,
    outbound_conversion_rate=0.5,
    lead_conversion_rate_outbound=6.0,
)


# ── Sidebar: Compensation Structure (Full Spec) ─────────────────────
st.sidebar.markdown("---")
st.sidebar.title("Compensation")

# Preset loader
_preset_choice = st.sidebar.selectbox(
    "Load Preset", ["— Custom —", "Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
    key="sb_preset_choice",
)
if _preset_choice != "— Custom —" and st.sidebar.button("Apply Preset", key="sb_apply_preset"):
    _p = ALL_PRESETS[_preset_choice]()
    st.session_state["sb_upfront"] = _p.upfront_fee_amount
    st.session_state["sb_retainer"] = _p.retainer_amount
    st.session_state["sb_esc"] = _p.retainer_escalation_enabled
    st.session_state["sb_rs_mode"] = ["none", "baseline", "per_client"].index(_p.rev_share_mode)
    st.session_state["sb_rs_pct"] = _p.rev_share_percentage
    st.session_state["sb_rs_basis"] = 0 if _p.rev_share_basis == "gross_revenue" else 1
    st.session_state["sb_rs_baseline"] = _p.rev_share_baseline
    st.session_state["sb_rs_window"] = _p.rev_share_client_window_months
    st.session_state["sb_decay"] = _p.rev_share_decay_enabled
    st.session_state["sb_per_deal"] = _p.per_deal_amount
    n = len(_p.rev_share_decay_schedule)
    st.session_state["sb_decay_n"] = min(n, 4)
    for i in range(4):
        if i < n:
            st.session_state[f"sb_d{i}_from"] = _p.rev_share_decay_schedule[i].from_month
            st.session_state[f"sb_d{i}_to"] = _p.rev_share_decay_schedule[i].to_month or 999
            st.session_state[f"sb_d{i}_rate"] = _p.rev_share_decay_schedule[i].rate * 100
    st.rerun()

# 1. Upfront
with st.sidebar.expander("Upfront Fee", expanded=False):
    sb_upfront = st.number_input("Upfront Fee ($)", value=0.0, step=1000.0, key="sb_upfront",
                                 help="One-time payment at contract execution. Covers initial asset development.")
    sb_split = st.checkbox("Split Payment", key="sb_split",
                           help="Split into two installments (e.g. 50% at signing, 50% at day 30).")
    if sb_split:
        sb_split_pct = st.number_input("% at Signing", value=50.0, step=10.0, key="sb_split_pct",
                                       help="Percentage of upfront fee paid at contract signing.")
        sb_split_day = int(st.number_input("Day for 2nd Payment", value=30, step=15, key="sb_split_day",
                                           help="Day the second installment is due."))
    else:
        sb_split_pct, sb_split_day = 100.0, 30

# 2. Retainer
with st.sidebar.expander("Monthly Retainer", expanded=True):
    sb_retainer = st.number_input("Retainer ($/mo)", value=7500.0, step=500.0, key="sb_retainer",
                                  help="Fixed monthly payment. Guaranteed regardless of performance.")
    sb_esc = st.checkbox("Escalation", key="sb_esc",
                         help="Step-up retainer at defined months (e.g. $7.5K→$8.5K→$10K).")
    if sb_esc:
        sb_esc_m1 = int(st.number_input("Step 1: Month", value=7, step=1, key="sb_esc_m1",
                                        help="Month when first step-up takes effect."))
        sb_esc_a1 = st.number_input("Step 1: Amount ($)", value=sb_retainer + 1000, step=500.0, key="sb_esc_a1",
                                    help="New retainer amount at step 1.")
        sb_esc_m2 = int(st.number_input("Step 2: Month", value=13, step=1, key="sb_esc_m2",
                                        help="Month when second step-up takes effect."))
        sb_esc_a2 = st.number_input("Step 2: Amount ($)", value=sb_retainer + 2500, step=500.0, key="sb_esc_a2",
                                    help="New retainer amount at step 2.")
        sb_esc_schedule = [RetainerStep(sb_esc_m1, sb_esc_a1), RetainerStep(sb_esc_m2, sb_esc_a2)]
    else:
        sb_esc_schedule = []

# 3. Rev Share
with st.sidebar.expander("Rev Share", expanded=True):
    sb_rs_mode = st.selectbox("Mode", ["none", "baseline", "per_client"],
                              format_func=lambda x: {"none": "None", "baseline": "Mode A: Baseline", "per_client": "Mode B: Per-Client"}[x],
                              key="sb_rs_mode",
                              help="None = no rev share. Baseline = % of total revenue above a threshold. Per-Client = % of each new client's revenue individually.")
    sb_rs_pct = st.number_input("Base Rate (%)", value=12.0, step=1.0, key="sb_rs_pct",
                                help="Base rev share percentage. Overridden by decay schedule if enabled.")
    sb_rs_basis = st.selectbox("Basis", ["gross_revenue", "gross_profit"],
                               format_func=lambda x: "Gross Revenue" if x == "gross_revenue" else "Gross Profit",
                               key="sb_rs_basis",
                               help="Gross Revenue = % of client's monthly payment. Gross Profit = % of margin after fulfillment.")
    if sb_rs_mode == "baseline":
        sb_rs_baseline = st.number_input("Baseline ($/mo)", value=50000.0, step=5000.0, key="sb_rs_baseline",
                                         help="Revenue threshold — only revenue ABOVE this generates rev share. Set to current MRR at signing.")
    else:
        sb_rs_baseline = 50000.0
    if sb_rs_mode == "per_client":
        sb_rs_window = int(st.number_input("Client Window (months)", value=18, step=3, key="sb_rs_window",
                                           help="Months of rev share per client. After window expires, that client stops generating rev share."))
    else:
        sb_rs_window = 18
    sb_decay = st.checkbox("Decay Schedule", key="sb_decay",
                           help="Rev share rate decreases over time. Front-loads operator value, goes to zero eventually.")
    sb_decay_schedule = []
    if sb_decay:
        sb_decay_n = int(st.number_input("Decay Periods", value=3, min_value=1, max_value=4, step=1, key="sb_decay_n",
                                         help="Number of rate steps in the decay schedule."))
        for i in range(sb_decay_n):
            d_from = int(st.number_input(f"P{i+1} From Mo", value=i * 6 + 1, step=1, key=f"sb_d{i}_from",
                                         help=f"Start month for period {i+1}."))
            d_to_v = int(st.number_input(f"P{i+1} To Mo (999=open)", value=(i + 1) * 6 if i < sb_decay_n - 1 else 999, step=1, key=f"sb_d{i}_to",
                                         help=f"End month for period {i+1}. Use 999 for open-ended."))
            d_rate = st.number_input(f"P{i+1} Rate (%)", value=max(0.0, sb_rs_pct - i * 5), step=1.0, key=f"sb_d{i}_rate",
                                    help=f"Rev share rate during period {i+1}.")
            sb_decay_schedule.append(DecayStep(d_from, None if d_to_v >= 999 else d_to_v, d_rate / 100.0))
    sb_cap_mo = st.number_input("Monthly Cap ($, 0=none)", value=0.0, step=1000.0, key="sb_cap_mo",
                                help="Max rev share earned per month. 0 = unlimited.")
    sb_cap_tot = st.number_input("Total Cap ($, 0=none)", value=0.0, step=10000.0, key="sb_cap_tot",
                                 help="Lifetime cap on total rev share. 0 = unlimited.")

# 4. Per-Deal
with st.sidebar.expander("Per-Deal Bonus", expanded=False):
    sb_per_deal = st.number_input("Per-Deal ($)", value=0.0, step=250.0, key="sb_per_deal",
                                  help="One-time payment per closed deal. Paid on first payment collected.")

# 5. Engagement Timing
RAMP_OPTIONS = {"Linear (gradual)": "linear", "Step (instant at ramp end)": "step"}
POST_ENG_OPTIONS = {
    "Improvements persist": "metrics_persist",
    "Improvements decay to baseline": "metrics_decay",
    "50% of improvements persist": "metrics_partial",
}
with st.sidebar.expander("Engagement", expanded=True):
    d_duration = int(st.number_input("Duration (days, 0=permanent)", value=365, step=90, key="d_dur",
                                     help="Total engagement length. 0 = runs for full simulation."))
    d_ramp = int(st.number_input("Ramp Period (days)", value=60, step=15, key="d_ramp",
                                 help="Days before operator's improvements reach full effect."))
    d_ramp_curve = RAMP_OPTIONS[st.selectbox("Ramp Curve", list(RAMP_OPTIONS.keys()), key="d_ramp_curve",
                                             help="Linear = gradual ramp-up. Step = instant at ramp end.")]
    d_post_eng = POST_ENG_OPTIONS[st.selectbox("Post-Engagement", list(POST_ENG_OPTIONS.keys()), key="d_post_eng",
                                               help="What happens to improvements after the engagement ends.")]
    d_decay = 180
    if d_post_eng == "metrics_decay":
        d_decay = int(st.number_input("Decay Period (days)", value=180, step=30, key="d_decay",
                                      help="Days for improvements to revert to baseline after engagement ends."))


# ── Build CompensationStructure from sidebar inputs ──────────────────
active_comp = CompensationStructure(
    name="Active",
    upfront_fee_amount=sb_upfront,
    upfront_fee_split=sb_split,
    upfront_fee_split_pct_signing=sb_split_pct,
    upfront_fee_split_day_2=sb_split_day,
    retainer_amount=sb_retainer,
    retainer_escalation_enabled=sb_esc,
    retainer_escalation_schedule=sb_esc_schedule,
    rev_share_mode=sb_rs_mode,
    rev_share_percentage=sb_rs_pct,
    rev_share_basis=sb_rs_basis,
    rev_share_baseline=sb_rs_baseline,
    rev_share_client_window_months=sb_rs_window,
    rev_share_decay_enabled=sb_decay,
    rev_share_decay_schedule=sb_decay_schedule,
    rev_share_cap_monthly=sb_cap_mo,
    rev_share_cap_total=sb_cap_tot,
    per_deal_amount=sb_per_deal,
)

# Build DealTerms for existing tabs (maps from new comp inputs)
_rs_basis_map = {"gross_revenue": "total_revenue", "gross_profit": "gross_profit"}
deal = DealTerms(
    revenue_share_pct=sb_rs_pct if sb_rs_mode != "none" else 0.0,
    revenue_share_basis=_rs_basis_map.get(sb_rs_basis, "delta"),
    revenue_share_cap=sb_cap_tot,
    monthly_retainer=sb_retainer,
    pay_per_close=sb_per_deal,
    upfront_fee=sb_upfront,
    bonuses=[],
    ramp_days=d_ramp,
    ramp_curve=d_ramp_curve,
    engagement_duration=d_duration,
    post_engagement_retention=d_post_eng,
    decay_rate_days=d_decay,
)

# ── Share button ──
st.sidebar.markdown("---")
_encoded = _encode_deal_state()
_current_param = st.query_params.get("d", "")
if _encoded != _current_param:
    st.query_params["d"] = _encoded
if st.sidebar.button("Copy Share Link", key="share_btn_deal"):
    st.sidebar.code(f"?d={_encoded}", language=None)
    st.sidebar.success("Copy the URL from your browser address bar to share this deal model.")

sim_before = run_simulation(inp_before)
sim_after = run_simulation(inp_after)
val_before = compute_valuation(inp_before, sim_before)
val_after = compute_valuation(inp_after, sim_after)
result = compute_deal(inp_before, inp_after, deal, sim_before, sim_after, val_before, val_after)
T = len(result.days)


# ── KPI Summary ─────────────────────────────────────────────────────
st.markdown("---")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Value Created", _fd(result.total_value_created))
c2.metric("Operator Earned", _fd(result.operator_total_earned))
c3.metric("Client Net Gain", _fd(result.client_net_gain))
c4.metric("Client ROI", f"{result.client_roi:.1f}x")
if result.break_even_day >= 0:
    c5.metric("Break-Even", f"Day {result.break_even_day}")
else:
    c5.metric("Break-Even", "Never")

c6, c7, c8, c9, c10 = st.columns(5)
c6.metric("Equity Before", _fd(result.client_equity_before))
c7.metric("Equity After", _fd(result.client_equity_after))
c8.metric("Equity Delta", _fd(result.equity_delta))
eq_pct = (result.equity_delta / abs(result.client_equity_before) * 100) if result.client_equity_before != 0 else 0
c9.metric("Equity Change", f"{eq_pct:+.0f}%")
c10.metric("Lifetime ROI", f"{result.lifetime_roi:.1f}x")

st.markdown("---")


# ── Tabs ─────────────────────────────────────────────────────────────
tab_overview, tab_client, tab_operator, tab_finder, tab_roi, tab_calc, tab_comp, tab_comp_cmp, tab_comp_sens = st.tabs(
    ["Overview", "Client View", "Operator View", "Deal Finder", "ROI Timeline", "Calculations",
     "Comp Structure", "Compare Structures", "Comp Sensitivity"]
)

# ── Run compensation engine from sidebar inputs ─────────────────────
comp_result = compute_compensation(active_comp, sim_after, inp_after)

# Convert monthly operator compensation to a daily array for KPI adjustment
_T_sim = len(sim_after.days)
_op_cost_daily = np.zeros(_T_sim)
for _m in range(comp_result.n_months):
    _s, _e = _m * 30, min((_m + 1) * 30, _T_sim)
    _days_in_month = _e - _s
    if _days_in_month > 0:
        _op_cost_daily[_s:_e] = comp_result.total_compensation[_m] / _days_in_month

# ---------- Tab: Overview ----------
with tab_overview:
    x = np.arange(T)

    fig_fcf = go.Figure()
    fig_fcf.add_trace(go.Scatter(
        x=x, y=sim_before.free_cash_flow,
        name="Before Operator", line=dict(color=COLORS["gray"], width=1),
    ))
    fig_fcf.add_trace(go.Scatter(
        x=x, y=result.eff_fcf,
        name="After Operator (ramped)", line=dict(color=COLORS["green"], width=1),
    ))
    fig_fcf.add_trace(go.Scatter(
        x=x, y=result.client_fcf_after_fees,
        name="After (net of fees)", line=dict(color=COLORS["sky"], width=1, dash="dash"),
    ))
    fig_fcf.add_hline(y=0, line_dash="dash", line_color="#333")
    if d_duration > 0:
        fig_fcf.add_vline(
            x=d_duration, line_dash="dot", line_color=COLORS["amber"],
            annotation_text="Engagement End", annotation_position="top left",
        )
    fig_fcf.update_layout(title="Daily FCF: Before vs After Operator", **DAILY_LAYOUT)
    st.plotly_chart(fig_fcf, use_container_width=True)

    fig_cust = go.Figure()
    fig_cust.add_trace(go.Scatter(
        x=x, y=sim_before.active_customers,
        name="Before", line=dict(color=COLORS["gray"], width=1),
    ))
    fig_cust.add_trace(go.Scatter(
        x=x, y=result.eff_active_customers,
        name="After (ramped)", line=dict(color=COLORS["green"], width=1),
    ))
    fig_cust.update_layout(title="Active Customers: Before vs After", **DAILY_LAYOUT)
    st.plotly_chart(fig_cust, use_container_width=True)

    fig_gain = go.Figure()
    fig_gain.add_trace(go.Scatter(
        x=x, y=result.client_cumulative_gain,
        name="Client Cumulative Gain", fill="tozeroy",
        line=dict(color=COLORS["green"], width=1),
    ))
    fig_gain.add_hline(y=0, line_dash="dash", line_color="#333")
    if result.break_even_day >= 0:
        fig_gain.add_vline(
            x=result.break_even_day, line_dash="dash", line_color=COLORS["green"],
            annotation_text=f"Break-even (day {result.break_even_day})",
        )
    fig_gain.update_layout(
        title="Client Cumulative Gain (vs doing nothing, after operator fees)", **DAILY_LAYOUT,
    )
    st.plotly_chart(fig_gain, use_container_width=True)

    fig_roi_ov = go.Figure()
    fig_roi_ov.add_trace(go.Scatter(
        x=x, y=result.roi_curve,
        name="Client ROI", fill="tozeroy",
        fillcolor="rgba(96,165,250,0.1)",
        line=dict(color=COLORS["sky"], width=2),
    ))
    fig_roi_ov.add_hline(y=0, line_dash="dash", line_color="#333")
    if result.break_even_day >= 0:
        fig_roi_ov.add_vline(
            x=result.break_even_day, line_dash="dash", line_color=COLORS["green"],
            annotation_text="Break-even",
        )
    if d_duration > 0:
        fig_roi_ov.add_vline(
            x=d_duration, line_dash="dot", line_color=COLORS["amber"],
            annotation_text="Engagement End",
        )
    fig_roi_ov.update_layout(title="Client ROI Over Time", yaxis_title="ROI (x)", **DAILY_LAYOUT)
    st.plotly_chart(fig_roi_ov, use_container_width=True)


# ---------- Tab: Client View ----------
with tab_client:
    st.markdown("### What the client gets")

    kpis_b = compute_kpis(inp_before, sim_before)
    kpis_a = compute_kpis(inp_after, sim_after, operator_cost_daily=_op_cost_daily)

    comparison = pd.DataFrame({
        "Metric": [
            "Active Customers (end)", "Monthly Revenue", "Monthly FCF",
            "Time to Profitability", "CAC (Blended)", "LTV", "LTV/CAC",
            "Profit/Customer/Month", "Equity Value (DCF)",
        ],
        "Before Operator": [
            f"{kpis_b.active_customers:,.0f}", _fd(kpis_b.monthly_revenue),
            _fd(kpis_b.monthly_fcf), f"{kpis_b.time_to_profitability_days} days",
            _fd(kpis_b.cac_blended), _fd(kpis_b.ltv), f"{kpis_b.ltv_cac_ratio:.1f}x",
            _fd(kpis_b.profit_per_customer_per_month), _fd(val_before.equity_value_dcf),
        ],
        "After Operator": [
            f"{kpis_a.active_customers:,.0f}", _fd(kpis_a.monthly_revenue),
            _fd(kpis_a.monthly_fcf), f"{kpis_a.time_to_profitability_days} days",
            _fd(kpis_a.cac_blended), _fd(kpis_a.ltv), f"{kpis_a.ltv_cac_ratio:.1f}x",
            _fd(kpis_a.profit_per_customer_per_month), _fd(val_after.equity_value_dcf),
        ],
    })
    st.dataframe(comparison, use_container_width=True, hide_index=True)

    be_text = (
        f"Break-even at **day {result.break_even_day}** (~month {result.break_even_day // 30 + 1})."
        if result.break_even_day >= 0
        else "The engagement **does not break even** within the simulation window."
    )
    st.markdown(
        f"**Bottom line for the client:** The operator creates **{_fd(result.total_value_created)}** "
        f"in FCF over the engagement. After paying the operator **{_fd(result.operator_total_earned)}**, "
        f"the client keeps **{_fd(result.client_net_gain)}** — a **{result.client_roi:.1f}x ROI** "
        f"on operator fees. Equity value increases by **{_fd(result.equity_delta)}**. {be_text}"
    )


# ---------- Tab: Operator View ----------
with tab_operator:
    st.markdown("### What the operator earns")

    eng_days = deal.engagement_duration if deal.engagement_duration > 0 else inp_before.time_max
    retainer_total = float(np.sum(result.operator_retainer))
    revshare_total = float(np.sum(result.operator_rev_share))
    ppc_total = float(np.sum(result.operator_pay_per_close))
    bonus_total = float(np.sum(result.operator_bonus))

    o1, o2, o3, o4, o5 = st.columns(5)
    o1.metric("Retainer", _fd(retainer_total))
    o2.metric("Rev Share", _fd(revshare_total))
    o3.metric("Pay/Close", _fd(ppc_total))
    o4.metric("Bonuses", _fd(bonus_total))
    o5.metric("Total Earned", _fd(result.operator_total_earned))

    o6, o7, o8 = st.columns(3)
    o6.metric("Avg Monthly", _fd(result.monthly_earnings_avg))
    o7.metric("Effective $/Customer", _fd(result.effective_rate_per_customer))
    total_new_eng = float(np.sum(result.eff_new_customers[: min(eng_days, T)]))
    o8.metric("Customers Acquired", f"{total_new_eng:,.0f}")

    fig_earn = go.Figure()
    fig_earn.add_trace(go.Scatter(
        x=np.arange(T), y=result.operator_cumulative_earnings,
        name="Cumulative Earnings", fill="tozeroy",
        line=dict(color=COLORS["amber"], width=1),
    ))
    if d_duration > 0:
        fig_earn.add_vline(
            x=d_duration, line_dash="dot", line_color=COLORS["gray"],
            annotation_text="Engagement End",
        )
    fig_earn.update_layout(title="Operator Cumulative Earnings", **DAILY_LAYOUT)
    st.plotly_chart(fig_earn, use_container_width=True)

    fig_break = go.Figure()
    fig_break.add_trace(go.Scatter(
        x=np.arange(T), y=np.cumsum(result.operator_retainer),
        name="Retainer", stackgroup="earnings",
        line=dict(color=COLORS["gray"], width=0),
    ))
    fig_break.add_trace(go.Scatter(
        x=np.arange(T), y=np.cumsum(result.operator_rev_share),
        name="Rev Share", stackgroup="earnings",
        line=dict(color=COLORS["green"], width=0),
    ))
    if sb_per_deal > 0:
        fig_break.add_trace(go.Scatter(
            x=np.arange(T), y=np.cumsum(result.operator_pay_per_close),
            name="Pay/Close", stackgroup="earnings",
            line=dict(color=COLORS["sky"], width=0),
        ))
    if bonus_total > 0:
        fig_break.add_trace(go.Scatter(
            x=np.arange(T), y=np.cumsum(result.operator_bonus),
            name="Bonuses", stackgroup="earnings",
            line=dict(color=COLORS["purple"], width=0),
        ))
    fig_break.update_layout(title="Earnings Breakdown (Cumulative, Stacked)", **DAILY_LAYOUT)
    st.plotly_chart(fig_break, use_container_width=True)



# ---------- Tab: Deal Finder ----------
with tab_finder:
    st.markdown("### Find the deal that works for both sides")
    finder_mode = st.radio(
        "Mode", ["Revenue Share Sweep", "Deal Comparison"], horizontal=True, key="finder_mode",
    )

    if finder_mode == "Revenue Share Sweep":
        st.caption("Sweep the revenue share % and see where both sides are profitable.")
        target_client_roi = st.number_input(
            "Minimum client ROI (x)", value=3.0, step=0.5, key="target_roi",
        )

        results_sweep = []
        for rs in np.arange(0, 51, 2.5):
            test_deal = DealTerms(
                revenue_share_pct=rs, revenue_share_basis=deal.revenue_share_basis,
                revenue_share_cap=deal.revenue_share_cap, monthly_retainer=sb_retainer,
                pay_per_close=sb_per_deal, bonuses=[],
                ramp_days=d_ramp, ramp_curve=d_ramp_curve,
                engagement_duration=d_duration,
                post_engagement_retention=d_post_eng, decay_rate_days=d_decay,
            )
            tr = compute_deal(
                inp_before, inp_after, test_deal, sim_before, sim_after, val_before, val_after,
            )
            results_sweep.append({
                "rev_share": rs,
                "operator_earned": tr.operator_total_earned,
                "client_net_gain": tr.client_net_gain,
                "client_roi": tr.client_roi,
                "break_even": tr.break_even_day,
            })

        rs_vals = [r["rev_share"] for r in results_sweep]
        op_vals = [r["operator_earned"] for r in results_sweep]
        cl_vals = [r["client_net_gain"] for r in results_sweep]

        fig_finder = go.Figure()
        fig_finder.add_trace(go.Scatter(
            x=rs_vals, y=op_vals,
            name="Operator Earned", line=dict(color=COLORS["amber"], width=2),
        ))
        fig_finder.add_trace(go.Scatter(
            x=rs_vals, y=cl_vals,
            name="Client Net Gain", line=dict(color=COLORS["green"], width=2),
        ))
        fig_finder.add_hline(y=0, line_dash="dash", line_color="#333")
        fig_finder.update_layout(
            title="Revenue Share % → Earnings for Both Sides",
            xaxis_title="Revenue Share (%)",
            yaxis_title="$",
            **{k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"},
        )
        st.plotly_chart(fig_finder, use_container_width=True)

        sweet_spots = [
            r for r in results_sweep
            if r["client_roi"] >= target_client_roi and r["operator_earned"] > 0
        ]
        if sweet_spots:
            best = max(sweet_spots, key=lambda r: r["operator_earned"])
            be_label = f"day {best['break_even']}" if best["break_even"] >= 0 else "never"
            st.success(
                f"**Sweet spot: {best['rev_share']:.1f}% revenue share**  \n"
                f"Operator earns **{_fd(best['operator_earned'])}** over the engagement.  \n"
                f"Client keeps **{_fd(best['client_net_gain'])}** net gain "
                f"({best['client_roi']:.1f}x ROI — above your {target_client_roi:.0f}x minimum).  \n"
                f"Break-even: {be_label}."
            )
        else:
            st.warning("No revenue share level meets the client's minimum ROI target.")

        sweep_df = pd.DataFrame(results_sweep)
        sweep_df.columns = ["Rev Share %", "Operator Earned", "Client Net Gain", "Client ROI", "Break-Even"]
        sweep_df["Operator Earned"] = sweep_df["Operator Earned"].apply(_fd)
        sweep_df["Client Net Gain"] = sweep_df["Client Net Gain"].apply(_fd)
        sweep_df["Client ROI"] = sweep_df["Client ROI"].apply(lambda v: f"{v:.1f}x")
        sweep_df["Break-Even"] = sweep_df["Break-Even"].apply(
            lambda v: f"Day {int(v)}" if v >= 0 else "Never",
        )
        st.dataframe(sweep_df, use_container_width=True, hide_index=True)

    else:
        st.caption(
            "Compare up to 4 deal structures side by side. "
            "All share the same engagement timing, bonuses, and ramp settings."
        )

        struct_defaults = [
            {"label": "High Retainer + Low Share", "ret": 5000.0, "rs": 10.0, "ppc": 0.0},
            {"label": "Low Retainer + High Share", "ret": 3000.0, "rs": 15.0, "ppc": 0.0},
            {"label": "Pure Pay Per Close", "ret": 0.0, "rs": 0.0, "ppc": 500.0},
            {"label": "Balanced Hybrid", "ret": 2000.0, "rs": 5.0, "ppc": 250.0},
        ]

        s_cols = st.columns(4)
        struct_params = []
        for i, col in enumerate(s_cols):
            with col:
                st.markdown(f"**{struct_defaults[i]['label']}**")
                s_ret = st.number_input("Retainer ($)", value=struct_defaults[i]["ret"], step=500.0, key=f"s{i}_ret")
                s_rs = st.number_input("Rev Share (%)", value=struct_defaults[i]["rs"], step=1.0, key=f"s{i}_rs")
                s_ppc = st.number_input("Pay/Close ($)", value=struct_defaults[i]["ppc"], step=100.0, key=f"s{i}_ppc")
                struct_params.append({"label": struct_defaults[i]["label"], "ret": s_ret, "rs": s_rs, "ppc": s_ppc})

        comp_results = []
        for sp in struct_params:
            td = DealTerms(
                revenue_share_pct=sp["rs"], revenue_share_basis=deal.revenue_share_basis,
                revenue_share_cap=deal.revenue_share_cap, monthly_retainer=sp["ret"],
                pay_per_close=sp["ppc"], bonuses=[],
                ramp_days=d_ramp, ramp_curve=d_ramp_curve,
                engagement_duration=d_duration,
                post_engagement_retention=d_post_eng, decay_rate_days=d_decay,
            )
            comp_results.append(compute_deal(
                inp_before, inp_after, td, sim_before, sim_after, val_before, val_after,
            ))

        comp_table = []
        for i, cr in enumerate(comp_results):
            comp_table.append({
                "Structure": struct_params[i]["label"],
                "Operator Earned": _fd(cr.operator_total_earned),
                "Client Net Gain": _fd(cr.client_net_gain),
                "Client ROI": f"{cr.client_roi:.1f}x",
                "Break-Even": f"Day {cr.break_even_day}" if cr.break_even_day >= 0 else "Never",
                "Lifetime ROI": f"{cr.lifetime_roi:.1f}x",
                "Eff $/Customer": _fd(cr.effective_rate_per_customer),
            })
        st.dataframe(pd.DataFrame(comp_table), use_container_width=True, hide_index=True)

        labels = [sp["label"] for sp in struct_params]
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name="Operator Earned", x=labels,
            y=[cr.operator_total_earned for cr in comp_results],
            marker_color=COLORS["amber"],
        ))
        fig_comp.add_trace(go.Bar(
            name="Client Net Gain", x=labels,
            y=[cr.client_net_gain for cr in comp_results],
            marker_color=COLORS["green"],
        ))
        fig_comp.update_layout(
            title="Deal Structure Comparison",
            barmode="group", yaxis_title="$",
            **{k: v for k, v in DAILY_LAYOUT.items() if k != "xaxis"},
        )
        st.plotly_chart(fig_comp, use_container_width=True)


# ---------- Tab: ROI Timeline ----------
with tab_roi:
    st.markdown("### ROI Over Time")
    st.caption(
        "How the client's return on the operator engagement evolves. "
        "The value compounds after the engagement ends because retained customers keep generating revenue."
    )

    fig_roi_tl = go.Figure()
    x_roi = np.arange(T)

    fig_roi_tl.add_trace(go.Scatter(
        x=x_roi, y=result.roi_curve,
        name="Client ROI", fill="tozeroy",
        fillcolor="rgba(74,222,128,0.1)",
        line=dict(color=COLORS["green"], width=2),
    ))
    fig_roi_tl.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

    if result.break_even_day >= 0:
        fig_roi_tl.add_vline(
            x=result.break_even_day, line_dash="dash",
            line_color=COLORS["green"], line_width=1,
            annotation_text=f"Break-even (day {result.break_even_day})",
            annotation_position="top left",
            annotation_font=dict(size=10, color=COLORS["green"]),
        )

    if d_duration > 0:
        fig_roi_tl.add_vline(
            x=d_duration, line_dash="dot",
            line_color=COLORS["amber"], line_width=1,
            annotation_text="Engagement End",
            annotation_position="top right",
            annotation_font=dict(size=10, color=COLORS["amber"]),
        )
        if d_duration < T:
            fig_roi_tl.add_vrect(
                x0=d_duration, x1=T,
                fillcolor=COLORS["green"], opacity=0.03, line_width=0,
                annotation_text="Post-Engagement Value",
                annotation_position="top left",
                annotation_font=dict(size=9, color="#666"),
            )

    for label, day in [("6 mo", 180), ("12 mo", 365), ("24 mo", 730)]:
        if day < T and result.cumulative_operator_cost[day] > 0:
            roi_val = float(result.roi_curve[day])
            fig_roi_tl.add_annotation(
                x=day, y=roi_val,
                text=f"{label}: {roi_val:.1f}x",
                showarrow=True, arrowhead=2, arrowwidth=1,
                arrowcolor="#666", font=dict(size=10, color="#ccc"),
                bgcolor="rgba(0,0,0,0.7)", bordercolor="#333",
            )

    fig_roi_tl.update_layout(
        title="Client ROI Timeline", yaxis_title="ROI (x)", **DAILY_LAYOUT,
    )
    st.plotly_chart(fig_roi_tl, use_container_width=True)

    st.markdown("### Monthly ROI Progression")
    max_months = min(T // 30, 30)
    eng_end_day = d_duration if d_duration > 0 else T
    roi_rows = []
    for m in range(1, max_months + 1):
        d = min(m * 30 - 1, T - 1)
        cv = float(result.cumulative_value_created[d])
        co = float(result.cumulative_operator_cost[d])
        cn = cv - co
        r = float(result.roi_curve[d]) if co > 0 else 0.0
        in_eng = "yes" if d < eng_end_day else ""
        roi_rows.append({
            "Month": m,
            "Active": in_eng,
            "Cum Value Created": _fd(cv),
            "Cum Operator Cost": _fd(co),
            "Cum Client Net": _fd(cn),
            "ROI": f"{r:.1f}x" if co > 0 else "—",
        })
    st.dataframe(pd.DataFrame(roi_rows), use_container_width=True, hide_index=True)


# ---------- Tab: Calculations ----------
with tab_calc:
    st.markdown("### Computation Audit Trail")
    st.caption("Every number, every formula, every step. Verify anything.")

    # ── Helper: render channel math for a given state ──
    def _channel_math(inp, label):
        lines = ""
        if inp.use_outbound:
            _cd = inp.contacts_per_month / 30
            _ld = _cd * (inp.outbound_conversion_rate / 100)
            _cusd = _ld * (inp.lead_conversion_rate_outbound / 100)
            _delay = inp.time_to_market_outbound + inp.time_to_sell
            lines += f"""OUTBOUND ({label}):
  contacts/day     = {inp.contacts_per_month:,} / 30 = {_cd:,.1f}
  leads/day        = {_cd:,.1f} × {inp.outbound_conversion_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} × {inp.lead_conversion_rate_outbound}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_outbound} + {inp.time_to_sell} = {_delay} days
"""
        if inp.use_inbound and inp.cpm > 0:
            _imp = (inp.media_spend / inp.cpm) * 1000 / 30
            _clk = _imp * (inp.ctr / 100)
            _ld = _clk * (inp.funnel_conversion_rate / 100)
            _cusd = _ld * (inp.lead_conversion_rate_inbound / 100)
            _delay = inp.time_to_market_inbound + inp.time_to_sell
            lines += f"""INBOUND ({label}):
  impressions/day  = (${inp.media_spend:,.0f} / ${inp.cpm:,.0f}) × 1000 / 30 = {_imp:,.0f}
  clicks/day       = {_imp:,.0f} × {inp.ctr}% = {_clk:,.1f}
  leads/day        = {_clk:,.1f} × {inp.funnel_conversion_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} × {inp.lead_conversion_rate_inbound}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_inbound} + {inp.time_to_sell} = {_delay} days
"""
        if inp.use_organic:
            _vd = inp.organic_views_per_month / 30
            _ld = _vd * (inp.organic_view_to_lead_rate / 100)
            _cusd = _ld * (inp.lead_to_customer_rate_organic / 100)
            _delay = inp.time_to_market_organic + inp.time_to_sell
            lines += f"""ORGANIC ({label}):
  views/day        = {inp.organic_views_per_month:,} / 30 = {_vd:,.0f}
  leads/day        = {_vd:,.0f} × {inp.organic_view_to_lead_rate}% = {_ld:,.2f}
  customers/day    = {_ld:,.2f} × {inp.lead_to_customer_rate_organic}% = {_cusd:,.4f}
  customers/month  = {_cusd * 30:,.1f}
  delay            = {inp.time_to_market_organic} + {inp.time_to_sell} = {_delay} days
"""
        return lines.rstrip()

    # ── 1. Customer Acquisition ──
    st.markdown("### 1. Customer Acquisition — Before vs After")
    _calc1, _calc2 = st.columns(2)
    with _calc1:
        st.code(_channel_math(inp_before, "Before"), language=None)
    with _calc2:
        st.code(_channel_math(inp_after, "After"), language=None)

    # ── 2. Revenue Per Customer ──
    def _unit_econ(inp, label):
        _rc = inp.price_of_offer * (inp.realization_rate / 100)
        _fc = inp.price_of_offer * (inp.cost_to_fulfill / 100)
        _sc = inp.price_of_offer * (inp.cost_to_sell / 100)
        _tc = _rc * (inp.transaction_fee / 100)
        _contrib = _rc - _fc - _sc - _tc
        lines = f"""NEW CUSTOMER ({label}):
  revenue_collected = ${inp.price_of_offer:,.0f} × {inp.realization_rate}% = ${_rc:,.0f}
  - fulfillment     = ${inp.price_of_offer:,.0f} × {inp.cost_to_fulfill}% = ${_fc:,.0f}
  - sales comm      = ${inp.price_of_offer:,.0f} × {inp.cost_to_sell}% = ${_sc:,.0f}
  - transaction fee  = ${_rc:,.0f} × {inp.transaction_fee}% = ${_tc:,.0f}
  = contribution     = ${_contrib:,.0f}

  cash collected over {inp.time_to_collect} days
  refund rate: {inp.refund_rate}% after {inp.refund_period} days
"""
        if inp.churn_rate < 100:
            _rr = 100 - inp.churn_rate
            _rv = inp.price_of_renewal * (inp.realization_rate / 100)
            _rf = inp.price_of_renewal * (inp.cost_to_fulfill_renewal / 100)
            _rs = inp.price_of_renewal * (inp.cost_to_sell_renewal / 100)
            _rt = _rv * (inp.transaction_fee / 100)
            _rc2 = _rv - _rf - _rs - _rt
            lines += f"""
RENEWAL ({label}):
  renewal rate       = {_rr:.0f}%
  renewal price      = ${inp.price_of_renewal:,.0f}
  revenue_collected  = ${_rv:,.0f}
  - fulfillment      = ${_rf:,.0f}
  - sales comm       = ${_rs:,.0f}
  - transaction fee  = ${_rt:,.0f}
  = contribution     = ${_rc2:,.0f}
  contract: {inp.contract_length} days, renewal of renewals: {inp.renewal_rate_of_renewals}%"""
        return lines.rstrip()

    st.markdown("### 2. Revenue Per Customer")
    _calc3, _calc4 = st.columns(2)
    with _calc3:
        st.code(_unit_econ(inp_before, "Before"), language=None)
    with _calc4:
        st.code(_unit_econ(inp_after, "After"), language=None)

    # ── 3. Lifetime Value ──
    def _ltv_calc(inp):
        _P = inp.price_of_offer
        _RR = inp.realization_rate / 100
        _cf = inp.cost_to_fulfill / 100
        _ref = inp.refund_rate / 100
        _ch = inp.churn_rate / 100
        _fv = _P * _RR * (1 - _ref) - _P * _cf
        _pr = inp.price_of_renewal
        _cfr = inp.cost_to_fulfill_renewal / 100
        _csr = inp.cost_to_sell_renewal / 100
        _rv = _pr * _RR - _pr * _cfr - _pr * _csr
        _pf = (1 - _ch) * (1 - _ref)
        _ps = inp.renewal_rate_of_renewals / 100
        _er = _pf * _rv / (1 - _ps) if 0 < _ps < 1 else _pf * _rv
        _ltv = _fv + _er
        return _ltv, f"""first_purchase = ${_P:,.0f} × {_RR:.2f} × {1-_ref:.2f} - ${_P:,.0f} × {_cf:.2f} = ${_fv:,.0f}
renewal_value  = ${_pr:,.0f} × {_RR:.2f} - fulfill - sales = ${_rv:,.0f}
p(1st renewal) = (1-{_ch:.2f}) × (1-{_ref:.2f}) = {_pf:.3f}
p(subsequent)  = {_ps:.2f}
exp_renewals   = {_pf:.3f} × ${_rv:,.0f} / (1-{_ps:.2f}) = ${_er:,.0f}
LTV            = ${_fv:,.0f} + ${_er:,.0f} = ${_ltv:,.0f}"""

    st.markdown("### 3. Lifetime Value")
    _ltv_b, _ltv_b_text = _ltv_calc(inp_before)
    _ltv_a, _ltv_a_text = _ltv_calc(inp_after)
    _calc5, _calc6 = st.columns(2)
    with _calc5:
        st.code(f"BEFORE:\n{_ltv_b_text}", language=None)
    with _calc6:
        st.code(f"AFTER:\n{_ltv_a_text}", language=None)

    # ── 4. CAC ──
    st.markdown("### 4. Customer Acquisition Cost")
    def _cac_calc(inp, sim, label):
        _tm = float(np.sum(sim.cost_marketing))
        _ts = float(np.sum(sim.cost_sales))
        _tc = float(np.sum(sim.new_customers_total))
        _cac = (_tm + _ts) / max(_tc, 1)
        return _cac, f"""{label}:
  total marketing   = ${_tm:,.0f}
  total sales cost  = ${_ts:,.0f}
  total customers   = {_tc:,.0f}
  CAC (blended)     = ${_cac:,.0f}"""

    _cac_b, _cac_b_text = _cac_calc(inp_before, sim_before, "Before")
    _cac_a, _cac_a_text = _cac_calc(inp_after, sim_after, "After")
    _calc7, _calc8 = st.columns(2)
    with _calc7:
        st.code(f"{_cac_b_text}\n\n  LTV / CAC = ${_ltv_b:,.0f} / ${_cac_b:,.0f} = {_ltv_b/max(_cac_b,1):.1f}x", language=None)
    with _calc8:
        st.code(f"{_cac_a_text}\n\n  LTV / CAC = ${_ltv_a:,.0f} / ${_cac_a:,.0f} = {_ltv_a/max(_cac_a,1):.1f}x", language=None)

    # ── 5. Monthly Cost Structure ──
    st.markdown("### 5. Monthly Cost Structure")
    def _cost_structure(inp, label):
        _dm = inp.media_spend if inp.use_inbound else 0
        _do = (inp.number_of_sdrs * inp.outbound_salary) if inp.use_outbound else 0
        _dg = inp.organic_cost_per_month if inp.use_organic else 0
        _di = (inp.debt * inp.interest_rate / 100) / 365
        return f"""{label}:
  MARKETING (monthly):
    inbound media   = ${_dm:,.0f}/mo {"(disabled)" if not inp.use_inbound else ""}
    outbound SDRs   = {inp.number_of_sdrs} × ${inp.outbound_salary:,.0f} = ${_do:,.0f}/mo {"(disabled)" if not inp.use_outbound else ""}
    organic         = ${_dg:,.0f}/mo {"(disabled)" if not inp.use_organic else ""}
  FIXED:
    base            = ${inp.fixed_costs_per_month:,.0f}/mo
    + scaling       = ${inp.fixed_cost_increase_per_100_customers:,.0f}/mo per 100 customers
  TRANSACTION FEE   = {inp.transaction_fee}%
  INTEREST          = ${inp.debt:,.0f} × {inp.interest_rate}% / 365 = ${_di:,.0f}/day
  TAX RATE          = {inp.tax_rate}%"""

    _calc9, _calc10 = st.columns(2)
    with _calc9:
        st.code(_cost_structure(inp_before, "Before"), language=None)
    with _calc10:
        st.code(_cost_structure(inp_after, "After"), language=None)

    # ── 6. P&L Snapshot (last day of simulation) ──
    st.markdown("### 6. P&L Snapshot — End of Simulation")
    def _pl_snapshot(sim, inp, label):
        _d = len(sim.days) - 1
        _s = max(0, _d - 29)
        _tr = float(np.sum(sim.cash_collected_total[_s:_d+1]))
        _tc = float(np.sum(sim.cost_total[_s:_d+1]))
        _gp = float(np.sum(sim.gross_profit[_s:_d+1]))
        _eb = float(np.sum(sim.ebitda[_s:_d+1]))
        _ni = float(np.sum(sim.net_income[_s:_d+1]))
        _fcf = float(np.sum(sim.free_cash_flow[_s:_d+1]))
        return f"""{label} — Trailing 30 Days (day {_s+1} to {_d+1}):
  Cash collected     ${_tr:>12,.0f}
  - Total costs      {-_tc:>12,.0f}
  ────────────────────────────────
  Gross Profit       ${_gp:>12,.0f}
  EBITDA             ${_eb:>12,.0f}
  Net Income         ${_ni:>12,.0f}
  Free Cash Flow     ${_fcf:>12,.0f}

  Active customers   {sim.active_customers[_d]:>12,.0f}
  Cumulative FCF     ${sim.cumulative_fcf[_d]:>12,.0f}
  Cash balance       ${sim.cash_balance[_d]:>12,.0f}"""

    _calc11, _calc12 = st.columns(2)
    with _calc11:
        st.code(_pl_snapshot(sim_before, inp_before, "Before"), language=None)
    with _calc12:
        st.code(_pl_snapshot(sim_after, inp_after, "After"), language=None)

    # ── 7. DCF Valuation ──
    st.markdown("### 7. DCF Valuation — Before vs After")
    def _dcf_calc(inp, val, label):
        return f"""{label}:
  Projection         = {inp.projection_period_dcf} days ({inp.projection_period_dcf/365:.1f} years)
  Discount rate      = {inp.discount_rate}%
  Perpetual growth   = {inp.perpetual_growth_rate}%

  PV of FCF          = ${val.pv_fcf:>14,.0f}
  Terminal value      = ${val.terminal_value:>14,.0f}
  PV of terminal      = ${val.pv_terminal_value:>14,.0f}
  ────────────────────────────────────
  Enterprise value    = ${val.enterprise_value_dcf:>14,.0f}
  - Debt + Cash       {-inp.debt + max(val.cash_at_valuation, 0):>14,.0f}
  ────────────────────────────────────
  Equity value        = ${val.equity_value_dcf:>14,.0f}

  TV as % of EV      = {val.pv_terminal_value / max(val.enterprise_value_dcf, 1) * 100:.0f}%"""

    _calc13, _calc14 = st.columns(2)
    with _calc13:
        st.code(_dcf_calc(inp_before, val_before, "Before"), language=None)
    with _calc14:
        st.code(_dcf_calc(inp_after, val_after, "After"), language=None)

    st.code(f"""EQUITY DELTA  = ${val_after.equity_value_dcf:,.0f} - ${val_before.equity_value_dcf:,.0f} = ${val_after.equity_value_dcf - val_before.equity_value_dcf:,.0f}
EQUITY CHANGE = {(val_after.equity_value_dcf - val_before.equity_value_dcf) / max(val_before.equity_value_dcf, 1) * 100:+,.0f}%""", language=None)

    # ── 8. Operator Compensation Structure ──
    st.markdown("### 8. Operator Compensation")
    _comp_lines = []
    if sb_upfront > 0:
        _comp_lines.append(f"  Upfront Fee        = ${sb_upfront:,.0f}" + (f" (split: {active_comp.upfront_fee_split_pct_signing:.0f}% signing, rest day {active_comp.upfront_fee_split_day_2})" if active_comp.upfront_fee_split else " (at signing)"))
    _comp_lines.append(f"  Monthly Retainer   = ${sb_retainer:,.0f}/mo")
    if sb_rs_mode != "none":
        _comp_lines.append(f"  Rev Share          = {sb_rs_pct:.1f}% on {sb_rs_basis}")
        if sb_cap_tot > 0:
            _comp_lines.append(f"  Rev Share Cap      = ${sb_cap_tot:,.0f}")
    if sb_per_deal > 0:
        _comp_lines.append(f"  Per-Deal Bonus     = ${sb_per_deal:,.0f}")
    _comp_lines.append(f"  Engagement         = {d_duration} days, ramp {d_ramp} days ({d_ramp_curve})")
    _comp_lines.append(f"  Post-engagement    = {d_post_eng}")
    st.code("\n".join(_comp_lines), language=None)

    st.code(f"""TOTAL EARNED (engagement period):
  Upfront            ${comp_result.total_upfront:>12,.0f}
  Retainer           ${comp_result.total_retainer:>12,.0f}
  Rev Share          ${comp_result.total_rev_share:>12,.0f}
  Per-Deal           ${comp_result.total_per_deal:>12,.0f}
  ────────────────────────────────────
  TOTAL              ${comp_result.total_earned:>12,.0f}

  Avg monthly        ${comp_result.avg_monthly_earnings:>12,.0f}
  Eff $/customer     ${comp_result.effective_rate_per_customer:>12,.0f}
  Eff rev share rate {comp_result.effective_rev_share_rate:>11.1f}%""", language=None)

    # ── 9. Cash Conversion Cycle ──
    st.markdown("### 9. Cash Conversion Cycle")
    def _ccc_calc(inp, label):
        _ttm = 0
        _ttm_src = "none"
        if inp.use_outbound:
            _ttm = inp.time_to_market_outbound
            _ttm_src = f"time_to_market_outbound = {_ttm}"
        elif inp.use_inbound:
            _ttm = inp.time_to_market_inbound
            _ttm_src = f"time_to_market_inbound = {_ttm}"
        elif inp.use_organic:
            _ttm = inp.time_to_market_organic
            _ttm_src = f"time_to_market_organic = {_ttm}"
        _ccc = _ttm + inp.time_to_sell + inp.time_to_collect
        return f"""{label}:
  CCC = time_to_market + time_to_sell + time_to_collect
      = {_ttm_src}
      + time_to_sell = {inp.time_to_sell}
      + time_to_collect = {inp.time_to_collect}
      = {_ccc} days"""

    _calc15, _calc16 = st.columns(2)
    with _calc15:
        st.code(_ccc_calc(inp_before, "Before"), language=None)
    with _calc16:
        st.code(_ccc_calc(inp_after, "After"), language=None)

    # ── 10. Input Delta Summary ──
    st.markdown("### 10. Input Deltas")
    _DIFF_FIELDS = [
        ("use_inbound", "Inbound Enabled"), ("use_outbound", "Outbound Enabled"),
        ("use_organic", "Organic Enabled"), ("use_viral", "Viral Enabled"),
        ("price_of_offer", "Price ($)"), ("realization_rate", "Realization (%)"),
        ("cost_to_fulfill", "Cost to Fulfill (%)"), ("cost_to_sell", "Cost to Sell (%)"),
        ("time_to_collect", "Time to Collect (days)"), ("time_to_sell", "Time to Sell (days)"),
        ("contract_length", "Contract Length (days)"),
        ("churn_rate", "Churn (%)"), ("price_of_renewal", "Renewal Price ($)"),
        ("cost_to_sell_renewal", "Cost to Sell Renewal (%)"),
        ("cost_to_fulfill_renewal", "Cost to Fulfill Renewal (%)"),
        ("renewal_rate_of_renewals", "Renewal of Renewals (%)"),
        ("media_spend", "Media Spend ($/mo)"), ("cpm", "CPM ($)"), ("ctr", "CTR (%)"),
        ("funnel_conversion_rate", "Funnel Conv (%)"),
        ("lead_conversion_rate_inbound", "LCR Inbound (%)"),
        ("outbound_conversion_rate", "Reply Rate (%)"),
        ("lead_conversion_rate_outbound", "LCR Outbound (%)"),
        ("number_of_sdrs", "SDRs"), ("outbound_salary", "SDR Salary ($/mo)"),
        ("contacts_per_month", "Contacts/Mo"),
        ("organic_views_per_month", "Organic Views/Mo"),
        ("organic_view_to_lead_rate", "View→Lead (%)"),
        ("lead_to_customer_rate_organic", "LCR Organic (%)"),
        ("organic_cost_per_month", "Organic Cost ($/mo)"),
        ("invites_per_customer", "Invites/Customer"),
        ("conversion_rate_per_invite", "Viral Conv (%)"),
        ("viral_time", "Viral Time (days)"), ("viral_start", "Viral Start (day)"),
        ("fixed_costs_per_month", "Fixed Costs ($/mo)"),
        ("transaction_fee", "Transaction Fee (%)"),
    ]
    input_rows = []
    for field, label in _DIFF_FIELDS:
        bv = getattr(inp_before, field)
        av = getattr(inp_after, field)
        if bv != av:
            if isinstance(bv, bool):
                input_rows.append((label, "Off" if not bv else "On", "Off" if not av else "On", "Changed"))
            elif isinstance(bv, int):
                input_rows.append((label, f"{bv:,}", f"{av:,}", f"{av - bv:+,}"))
            elif abs(bv) >= 1000:
                input_rows.append((label, f"${bv:,.0f}", f"${av:,.0f}", f"${av - bv:+,.0f}"))
            else:
                input_rows.append((label, f"{bv:.2f}", f"{av:.2f}", f"{av - bv:+.2f}"))
    if input_rows:
        st.dataframe(
            pd.DataFrame(input_rows, columns=["Metric", "Before", "After", "Delta"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Both states are identical — adjust the 'After Operator' inputs to model improvements.")

    # ── 11. Monthly Computation Chain ──
    st.markdown("### 11. Monthly Computation Chain")
    max_months_calc = min(T // 30, 30)
    calc_rows = []
    for m in range(1, max_months_calc + 1):
        s = (m - 1) * 30
        e = min(m * 30, T)
        d_end = min(e - 1, T - 1)
        fcf_b = float(np.sum(sim_before.free_cash_flow[s:e]))
        fcf_a = float(np.sum(result.eff_fcf[s:e]))
        calc_rows.append({
            "Mo": m,
            "FCF Before": _fd(fcf_b),
            "FCF After": _fd(fcf_a),
            "Delta": _fd(fcf_a - fcf_b),
            "Retainer": _fd(float(np.sum(result.operator_retainer[s:e]))),
            "Rev Share": _fd(float(np.sum(result.operator_rev_share[s:e]))),
            "Pay/Close": _fd(float(np.sum(result.operator_pay_per_close[s:e]))),
            "Bonus": _fd(float(np.sum(result.operator_bonus[s:e]))),
            "Op Total": _fd(float(np.sum(result.operator_total_earnings[s:e]))),
            "Client Net": _fd(float(np.sum(
                result.client_fcf_after_fees[s:e] - sim_before.free_cash_flow[s:e],
            ))),
            "ROI": (
                f"{result.roi_curve[d_end]:.1f}x"
                if result.cumulative_operator_cost[d_end] > 0 else "—"
            ),
            "Ramp": f"{result.ramp_factor[d_end]:.0%}",
        })
    st.dataframe(pd.DataFrame(calc_rows), use_container_width=True, hide_index=True)

    # ── 12. Key Formulas ──
    st.markdown("### 12. Key Formulas")
    be_formula = f"Day {result.break_even_day}" if result.break_even_day >= 0 else "Never"
    st.code(f"""Value Created      = FCF(after, ramped) − FCF(before)
                   = {_fd(result.total_value_created)}

Operator Earned    = Upfront + Retainer + Rev Share + Pay/Close + Bonuses
                   = {_fd(comp_result.total_upfront)} + {_fd(comp_result.total_retainer)} + {_fd(comp_result.total_rev_share)} + {_fd(comp_result.total_per_deal)}
                   = {_fd(result.operator_total_earned)}

Client Net Gain    = Value Created − Operator Earned
                   = {_fd(result.total_value_created)} − {_fd(result.operator_total_earned)}
                   = {_fd(result.client_net_gain)}

Client ROI         = Client Net Gain / Operator Earned
                   = {_fd(result.client_net_gain)} / {_fd(result.operator_total_earned)}
                   = {result.client_roi:.1f}x

Lifetime ROI       = Cumulative Net / Cumulative Op Cost at sim end
                   = {result.lifetime_roi:.1f}x

Break-Even Day     = First day client cumulative net ≥ 0
                   = {be_formula}""", language=None)


# ---------- Tab: Comp Structure (output only — inputs in sidebar) ----------
# Compute business health KPIs for both states
_kpis_before = compute_kpis(inp_before, sim_before)
_kpis_after = compute_kpis(inp_after, sim_after, operator_cost_daily=_op_cost_daily)

with tab_comp:
    st.markdown("### Compensation Structure")
    st.caption("Configure all compensation parameters in the sidebar. Results update live.")

    # ── Operator compensation KPIs ──
    st.markdown("**Operator Compensation**")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Earned", _fd(comp_result.total_earned))
    k2.metric("Avg Monthly", _fd(comp_result.avg_monthly_earnings))
    k3.metric("Eff $/Customer", _fd(comp_result.effective_rate_per_customer))
    k4.metric("Eff RS Rate", f"{comp_result.effective_rev_share_rate:.1f}%")
    k5.metric("Client Cum. Profit", _fd(comp_result.client_cumulative_profit_after_comp[-1]))

    k6, k7, k8, k9, k10 = st.columns(5)
    k6.metric("Upfront", _fd(comp_result.total_upfront))
    k7.metric("Retainer", _fd(comp_result.total_retainer))
    k8.metric("Rev Share", _fd(comp_result.total_rev_share))
    k9.metric("Per-Deal", _fd(comp_result.total_per_deal))
    k10.metric("Total Customers", f"{float(np.sum(comp_result.monthly_new_customers)):,.0f}")

    # ── Business health KPIs (Before → After with deltas) ──
    st.markdown("---")
    st.markdown("**Client Business Health — Before vs After Operator**")

    h1, h2, h3, h4, h5 = st.columns(5)
    _ttp_b = f"{_kpis_before.time_to_profitability_months}mo" if _kpis_before.time_to_profitability_months > 0 else "Never"
    _ttp_a = f"{_kpis_after.time_to_profitability_months}mo" if _kpis_after.time_to_profitability_months > 0 else "Never"
    _ttp_delta = _kpis_before.time_to_profitability_days - _kpis_after.time_to_profitability_days
    h1.metric("Time to Profit", _ttp_a,
              delta=f"{_ttp_delta:+d} days faster" if _ttp_delta > 0 else None)
    h2.metric("Cash Needed", _fd(_kpis_after.cash_needed),
              delta=_fd(_kpis_before.cash_needed - _kpis_after.cash_needed))
    h3.metric("LTV/CAC", f"{_kpis_after.ltv_cac_ratio:.1f}x",
              delta=f"{_kpis_after.ltv_cac_ratio - _kpis_before.ltv_cac_ratio:+.1f}x")
    h4.metric("CAC (Blended)", _fd(_kpis_after.cac_blended),
              delta=_fd(_kpis_before.cac_blended - _kpis_after.cac_blended))
    h5.metric("LTV", _fd(_kpis_after.ltv),
              delta=_fd(_kpis_after.ltv - _kpis_before.ltv))

    h6, h7, h8, h9, h10 = st.columns(5)
    h6.metric("Payback Period", f"{_kpis_after.payback_period_days:.0f}d",
              delta=f"{_kpis_before.payback_period_days - _kpis_after.payback_period_days:+.0f}d")
    h7.metric("Gross Margin", f"{_kpis_after.gross_margin:.1f}%",
              delta=f"{_kpis_after.gross_margin - _kpis_before.gross_margin:+.1f}%")
    h8.metric("Monthly FCF", _fd(_kpis_after.monthly_fcf),
              delta=_fd(_kpis_after.monthly_fcf - _kpis_before.monthly_fcf))
    h9.metric("Profit/Cust/Mo", _fd(_kpis_after.profit_per_customer_per_month),
              delta=_fd(_kpis_after.profit_per_customer_per_month - _kpis_before.profit_per_customer_per_month))
    h10.metric("Cash Conv. Cycle", f"{_kpis_after.cash_conversion_cycle}d",
               delta=f"{_kpis_before.cash_conversion_cycle - _kpis_after.cash_conversion_cycle:+d}d")

    st.markdown("---")

    # ── Cumulative earnings chart ──
    x_mo = np.arange(1, comp_result.n_months + 1)

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.retainer), name="Retainer", stackgroup="e", line=dict(color=COLORS["gray"], width=0)))
    if comp_result.total_rev_share > 0:
        fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.rev_share), name="Rev Share", stackgroup="e", line=dict(color=COLORS["green"], width=0)))
    if comp_result.total_per_deal > 0:
        fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.per_deal_bonus), name="Per-Deal", stackgroup="e", line=dict(color=COLORS["sky"], width=0)))
    if comp_result.total_upfront > 0:
        fig_cum.add_trace(go.Scatter(x=x_mo, y=np.cumsum(comp_result.upfront), name="Upfront", stackgroup="e", line=dict(color=COLORS["amber"], width=0)))
    fig_cum.update_layout(title="Cumulative Operator Earnings (Stacked)", xaxis_title="Month", yaxis_title="$",
                          **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
    st.plotly_chart(fig_cum, use_container_width=True)

    # ── Client profit vs operator earnings ──
    fig_split = go.Figure()
    fig_split.add_trace(go.Scatter(x=x_mo, y=comp_result.cumulative_compensation, name="Operator Earnings", fill="tozeroy",
                                   line=dict(color=COLORS["amber"], width=2), fillcolor="rgba(251,191,36,0.15)"))
    fig_split.add_trace(go.Scatter(x=x_mo, y=comp_result.client_cumulative_profit_after_comp, name="Client Profit (after comp)", fill="tozeroy",
                                   line=dict(color=COLORS["green"], width=2), fillcolor="rgba(74,222,128,0.1)"))
    fig_split.add_hline(y=0, line_dash="dash", line_color="#333")
    fig_split.update_layout(title="Operator vs Client — Cumulative", xaxis_title="Month", yaxis_title="$",
                            **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
    st.plotly_chart(fig_split, use_container_width=True)

    # ── Monthly breakdown table ──
    st.markdown("### Month-by-Month Breakdown")
    comp_rows = []
    for m in range(comp_result.n_months):
        comp_rows.append({
            "Month": m + 1, "Upfront": _fd(comp_result.upfront[m]), "Retainer": _fd(comp_result.retainer[m]),
            "Rev Share": _fd(comp_result.rev_share[m]), "Per-Deal": _fd(comp_result.per_deal_bonus[m]),
            "Total Comp": _fd(comp_result.total_compensation[m]), "Cumulative": _fd(comp_result.cumulative_compensation[m]),
            "Client FCF": _fd(comp_result.client_monthly_fcf[m]), "Client Net": _fd(comp_result.client_profit_after_comp[m]),
            "New Custs": f"{comp_result.monthly_new_customers[m]:.1f}", "Active": f"{comp_result.monthly_active_customers[m]:.0f}",
        })
    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

    # ── Per-cohort heatmap (Mode B only) ──
    if active_comp.rev_share_mode == "per_client":
        st.markdown("### Per-Client Rev Share Heatmap")
        st.caption("Each cell = rev share from cohort (column) in month (row). Watch the decay.")
        max_d = min(36, comp_result.n_months)
        fig_heat = go.Figure(go.Heatmap(
            z=comp_result.rev_share_by_cohort[:max_d, :max_d],
            x=[f"C{c+1}" for c in range(max_d)], y=[f"M{m+1}" for m in range(max_d)],
            colorscale="YlOrRd", hovertemplate="Cohort %{x}, Month %{y}: $%{z:,.0f}<extra></extra>",
        ))
        fig_heat.update_layout(title="Rev Share by Cohort x Month", xaxis_title="Cohort", yaxis_title="Month", height=500,
                               font=dict(family="JetBrains Mono, Consolas, monospace", size=11, color="#b0b0b0"),
                               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(10,10,10,1)")
        st.plotly_chart(fig_heat, use_container_width=True)


# ---------- Tab: Compare Structures ----------
with tab_comp_cmp:
    st.markdown("### Compare Structures")
    st.caption(
        "Save the current comp structure as Structure A. Then adjust inputs in the Comp Structure tab "
        "and come back here to see the delta."
    )

    import json as _json

    if st.button("Save current structure as Structure A", key="save_struct_a"):
        st.session_state["comp_structure_a"] = _json.dumps({
            "upfront_fee_amount": active_comp.upfront_fee_amount,
            "upfront_fee_split": active_comp.upfront_fee_split,
            "upfront_fee_split_pct_signing": active_comp.upfront_fee_split_pct_signing,
            "upfront_fee_split_day_2": active_comp.upfront_fee_split_day_2,
            "retainer_amount": active_comp.retainer_amount,
            "retainer_escalation_enabled": active_comp.retainer_escalation_enabled,
            "retainer_escalation_schedule": [(s.month, s.amount) for s in active_comp.retainer_escalation_schedule],
            "rev_share_mode": active_comp.rev_share_mode,
            "rev_share_percentage": active_comp.rev_share_percentage,
            "rev_share_basis": active_comp.rev_share_basis,
            "rev_share_baseline": active_comp.rev_share_baseline,
            "rev_share_client_window_months": active_comp.rev_share_client_window_months,
            "rev_share_decay_enabled": active_comp.rev_share_decay_enabled,
            "rev_share_decay_schedule": [(d.from_month, d.to_month, d.rate) for d in active_comp.rev_share_decay_schedule],
            "rev_share_cap_monthly": active_comp.rev_share_cap_monthly,
            "rev_share_cap_total": active_comp.rev_share_cap_total,
            "per_deal_amount": active_comp.per_deal_amount,
        })
        st.success("Structure A saved. Adjust inputs in Comp Structure tab, then return here.")

    if "comp_structure_a" not in st.session_state:
        st.info("No Structure A saved yet. Click the button above to save the current configuration.")
    else:
        a_data = _json.loads(st.session_state["comp_structure_a"])
        comp_a = CompensationStructure(
            name="Structure A",
            upfront_fee_amount=a_data["upfront_fee_amount"],
            upfront_fee_split=a_data["upfront_fee_split"],
            upfront_fee_split_pct_signing=a_data["upfront_fee_split_pct_signing"],
            upfront_fee_split_day_2=a_data["upfront_fee_split_day_2"],
            retainer_amount=a_data["retainer_amount"],
            retainer_escalation_enabled=a_data["retainer_escalation_enabled"],
            retainer_escalation_schedule=[RetainerStep(s[0], s[1]) for s in a_data["retainer_escalation_schedule"]],
            rev_share_mode=a_data["rev_share_mode"],
            rev_share_percentage=a_data["rev_share_percentage"],
            rev_share_basis=a_data["rev_share_basis"],
            rev_share_baseline=a_data["rev_share_baseline"],
            rev_share_client_window_months=a_data["rev_share_client_window_months"],
            rev_share_decay_enabled=a_data["rev_share_decay_enabled"],
            rev_share_decay_schedule=[DecayStep(d[0], d[1], d[2]) for d in a_data["rev_share_decay_schedule"]],
            rev_share_cap_monthly=a_data["rev_share_cap_monthly"],
            rev_share_cap_total=a_data["rev_share_cap_total"],
            per_deal_amount=a_data["per_deal_amount"],
        )
        res_a = compute_compensation(comp_a, sim_after, inp_after)
        res_b = comp_result  # current structure from Comp Structure tab

        # ── Delta metrics ──
        st.markdown("---")
        d1, d2, d3, d4, d5 = st.columns(5)
        _delta_earned = res_b.total_earned - res_a.total_earned
        _delta_pct = (_delta_earned / max(abs(res_a.total_earned), 1)) * 100
        d1.metric("Total Earned", _fd(res_b.total_earned), delta=f"{_fd(_delta_earned)} ({_delta_pct:+.0f}%)")
        _d_ret = res_b.total_retainer - res_a.total_retainer
        d2.metric("Retainer", _fd(res_b.total_retainer), delta=_fd(_d_ret))
        _d_rs = res_b.total_rev_share - res_a.total_rev_share
        d3.metric("Rev Share", _fd(res_b.total_rev_share), delta=_fd(_d_rs))
        _d_pd = res_b.total_per_deal - res_a.total_per_deal
        d4.metric("Per-Deal", _fd(res_b.total_per_deal), delta=_fd(_d_pd))
        _d_cl = res_b.client_cumulative_profit_after_comp[-1] - res_a.client_cumulative_profit_after_comp[-1]
        d5.metric("Client Profit", _fd(res_b.client_cumulative_profit_after_comp[-1]), delta=_fd(_d_cl))

        # ── Comparison table ──
        cmp_df = pd.DataFrame({
            "Metric": ["Total Earned", "Upfront", "Retainer", "Rev Share", "Per-Deal",
                        "Avg Monthly", "Eff $/Customer", "Eff RS %", "Client Profit"],
            "Structure A": [_fd(res_a.total_earned), _fd(res_a.total_upfront), _fd(res_a.total_retainer),
                            _fd(res_a.total_rev_share), _fd(res_a.total_per_deal), _fd(res_a.avg_monthly_earnings),
                            _fd(res_a.effective_rate_per_customer), f"{res_a.effective_rev_share_rate:.1f}%",
                            _fd(res_a.client_cumulative_profit_after_comp[-1])],
            "Structure B (Current)": [_fd(res_b.total_earned), _fd(res_b.total_upfront), _fd(res_b.total_retainer),
                                      _fd(res_b.total_rev_share), _fd(res_b.total_per_deal), _fd(res_b.avg_monthly_earnings),
                                      _fd(res_b.effective_rate_per_customer), f"{res_b.effective_rev_share_rate:.1f}%",
                                      _fd(res_b.client_cumulative_profit_after_comp[-1])],
        })
        st.dataframe(cmp_df, use_container_width=True, hide_index=True)

        # ── Overlay charts ──
        x_cmp = np.arange(1, res_a.n_months + 1)
        fig_cmp_earn = go.Figure()
        fig_cmp_earn.add_trace(go.Scatter(x=x_cmp, y=res_a.cumulative_compensation, name="Structure A", line=dict(color=COLORS["gray"], width=2)))
        fig_cmp_earn.add_trace(go.Scatter(x=x_cmp, y=res_b.cumulative_compensation, name="Structure B (Current)", line=dict(color=COLORS["amber"], width=2)))
        fig_cmp_earn.update_layout(title="Cumulative Operator Earnings — A vs B", xaxis_title="Month", yaxis_title="$",
                                   **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
        st.plotly_chart(fig_cmp_earn, use_container_width=True)

        fig_cmp_cl = go.Figure()
        fig_cmp_cl.add_trace(go.Scatter(x=x_cmp, y=res_a.client_cumulative_profit_after_comp, name="Structure A", line=dict(color=COLORS["gray"], width=2)))
        fig_cmp_cl.add_trace(go.Scatter(x=x_cmp, y=res_b.client_cumulative_profit_after_comp, name="Structure B (Current)", line=dict(color=COLORS["green"], width=2)))
        fig_cmp_cl.add_hline(y=0, line_dash="dash", line_color="#333")
        fig_cmp_cl.update_layout(title="Client Cumulative Profit — A vs B", xaxis_title="Month", yaxis_title="$",
                                 **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
        st.plotly_chart(fig_cmp_cl, use_container_width=True)


# ---------- Tab: Comp Sensitivity ----------
with tab_comp_sens:
    st.markdown("### Compensation Sensitivity")
    st.caption("Sweep a single parameter and see how it shifts operator earnings and client profit.")

    _SWEEP_PARAMS = {
        "Retainer ($/mo)": ("retainer_amount", [2000, 3500, 5000, 7500, 10000, 12500, 15000]),
        "Rev Share Rate (%)": ("rev_share_percentage", [2, 5, 8, 10, 12, 15, 18, 20, 25]),
        "Per-Deal Bonus ($)": ("per_deal_amount", [0, 500, 1000, 1500, 2000, 3000, 4000, 5000]),
        "Upfront Fee ($)": ("upfront_fee_amount", [0, 2500, 5000, 7500, 10000, 15000, 20000, 25000]),
        "Baseline ($/mo, Mode A)": ("rev_share_baseline", [0, 10000, 25000, 50000, 75000, 100000]),
        "Client Window (mo, Mode B)": ("rev_share_client_window_months", [6, 9, 12, 15, 18, 24, 30, 36]),
    }

    sens_metric = st.selectbox("Parameter to Sweep", list(_SWEEP_PARAMS.keys()), key="sens_param")
    param_name, test_values = _SWEEP_PARAMS[sens_metric]
    current_val = getattr(active_comp, param_name)

    sens_results = []
    for v in test_values:
        test_comp = CompensationStructure(**{**active_comp.__dict__, param_name: v})
        test_comp.name = f"{param_name}={v}"
        tr = compute_compensation(test_comp, sim_after, inp_after)
        sens_results.append({
            "value": v, "total_earned": tr.total_earned, "retainer": tr.total_retainer,
            "rev_share": tr.total_rev_share, "per_deal": tr.total_per_deal,
            "client_profit": tr.client_cumulative_profit_after_comp[-1],
            "avg_monthly": tr.avg_monthly_earnings,
        })

    base_res = [r for r in sens_results if abs(r["value"] - current_val) < 0.01]
    base_earned = base_res[0]["total_earned"] if base_res else sens_results[0]["total_earned"]

    # ── Bar chart ──
    labels = [f"${v:,.0f}" if "($" in sens_metric else f"{v:g}" for v in test_values]
    earnings = [r["total_earned"] for r in sens_results]
    bar_colors = ["#e0e0e0" if abs(r["value"] - current_val) < 0.01 else "#404040" for r in sens_results]

    fig_sens = go.Figure(go.Bar(
        x=labels, y=earnings, marker_color=bar_colors,
        text=[f"${v / 1_000_000:,.1f}M" if abs(v) >= 1_000_000 else f"${v / 1_000:,.1f}K" for v in earnings],
        textposition="outside", textfont=dict(size=10, color="#888"),
    ))
    fig_sens.update_layout(title=f"Total Operator Earnings by {sens_metric}", yaxis_title="$",
                           **{k: v for k, v in DAILY_LAYOUT.items() if k not in ("xaxis",)})
    st.plotly_chart(fig_sens, use_container_width=True)

    # ── Delta table ──
    sens_rows = []
    for r in sens_results:
        delta = r["total_earned"] - base_earned
        pct = (delta / abs(base_earned) * 100) if base_earned != 0 else 0
        is_current = abs(r["value"] - current_val) < 0.01
        sens_rows.append({
            "": "→" if is_current else "",
            sens_metric: f"${r['value']:,.0f}" if "($" in sens_metric else f"{r['value']:g}",
            "Total Earned": _fd(r["total_earned"]),
            "Retainer": _fd(r["retainer"]),
            "Rev Share": _fd(r["rev_share"]),
            "Per-Deal": _fd(r["per_deal"]),
            "Avg Monthly": _fd(r["avg_monthly"]),
            "Client Profit": _fd(r["client_profit"]),
            "Delta": f"${delta:+,.0f}",
            "Change": f"{pct:+.0f}%",
        })
    st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)
