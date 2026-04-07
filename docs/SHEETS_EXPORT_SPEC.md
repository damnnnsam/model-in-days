# Google Sheets Export/Import — Feature Spec

## Repo & Branch
- **Repo:** `https://github.com/damnnnsam/model-in-days.git`
- **Branch:** `feature/client-architecture` (branch off this, not main)
- **Working dir:** `/Users/samwest/financial_modeling`

## Context

This is a financial modeling tool built on Streamlit. It models internet businesses (channels, product, costs → simulation → DCF valuation) and operator deal economics (before/after comparison + compensation structures).

The app has a client-centric architecture:
- **Clients** have **models** (business configurations) and **deals** (compensation structures connecting two models)
- A **model** is either a base model (full `ModelInputs` snapshot) or a layered model (overrides on a parent)
- A **deal** connects a before model + after model + `CompensationStructure` + engagement terms

## What to build

### 1. Export a model to Google Sheets

Take a resolved `ModelInputs` and write it to a Google Sheet as a structured, readable spreadsheet.

**Layout:**
- One sheet per model
- Rows grouped by section: Starting State, Sales, Inbound, Outbound, Organic, Viral, Product, Renewals, Administration, Valuation
- Columns: `Section | Parameter | Value | Unit | Description`
- Section headers as merged/bold rows
- Values formatted appropriately ($ for money, % for percentages, days for time)

### 2. Export a deal to Google Sheets

Full deal export as a multi-sheet workbook:
- **Sheet 1: "Baseline"** — baseline model params (same format as model export)
- **Sheet 2: "Target"** — target model params, with changed fields highlighted (bold, colored)
- **Sheet 3: "Deltas"** — only the fields that changed, with before/after/delta columns
- **Sheet 4: "Compensation"** — compensation structure params (retainer, rev share, per-deal, etc.)
- **Sheet 5: "Engagement"** — engagement terms (duration, ramp, post-engagement)
- **Sheet 6: "Summary"** — computed outputs: operator earned, client ROI, break-even day, equity delta, etc.

### 3. Import a model from Google Sheets

Read a sheet in the export format and parse it back into a `ModelInputs`:
- Read the Parameter/Value columns
- Map parameter names back to `ModelInputs` field names
- Create a new base model via `store/model.py`'s `create_base_model()`

### Integration approach

Use `gspread` + Google service account (simplest path):
- `pip install gspread google-auth` (add to requirements.txt)
- Service account JSON stored in Streamlit secrets
- Create sheets in a configurable Google Drive folder

### UI integration points

Add buttons in `app.py`:
- **Model view** (~line 270): "Export to Sheets" button after the model title
- **Deal view** (~line 330): "Export to Sheets" button after the deal title
- **Client overview** (`views/client_manager.py`): "Import from Sheets" alongside existing URL import

## Key files to read

| File | What it does |
|------|-------------|
| `store/serialization.py` | `model_inputs_to_dict()`, `comp_structure_to_dict()`, `deal_terms_to_dict()` — JSON roundtrip for all dataclasses |
| `engine/inputs.py` | `ModelInputs` — 55+ field dataclass with all business model params |
| `model_2_operator/compensation.py` | `CompensationStructure` — 24+ field dataclass with nested lists (DecayStep, RetainerStep, etc.) |
| `store/model.py` | `resolve_model()` walks override chain → full ModelInputs. `create_base_model()` saves a new model. |
| `store/deal.py` | `load_deal()`, `get_compensation_structure()`, `get_engagement_config()` |
| `app.py` | Unified entry point — add export/import buttons here |
| `views/client_manager.py` | Client overview — add Sheets import here |
| `ui/sidebar.py` | `render_model_inputs()` — canonical input renderer, shows all field labels/help text (useful reference for sheet column descriptions) |

## Data format reference

**ModelInputs fields** (from `engine/inputs.py`):
```
cash_in_bank, assets, liabilities, customer_count, total_addressable_market,
upfront_investment_costs, debt, interest_rate, cost_to_sell, time_to_sell,
avg_deals_per_rep_per_month, use_inbound, use_outbound, use_organic, use_viral,
media_spend, cpm, ctr, funnel_conversion_rate, time_to_market_inbound,
lead_conversion_rate_inbound, outbound_salary, contacts_per_month, number_of_sdrs,
outbound_conversion_rate, time_to_market_outbound, lead_conversion_rate_outbound,
organic_views_per_month, organic_view_to_lead_rate, lead_to_customer_rate_organic,
time_to_market_organic, organic_cost_per_month, price_of_offer, realization_rate,
cost_to_fulfill, time_to_collect, refund_period, refund_rate, contract_length,
churn_rate, price_of_renewal, cost_to_sell_renewal, cost_to_fulfill_renewal,
time_to_collect_renewal, renewal_rate_of_renewals, invites_per_customer,
conversion_rate_per_invite, viral_time, viral_start, cost_to_sell_viral,
cost_to_market_viral, transaction_fee, fixed_costs_per_month,
fixed_cost_increase_per_100_customers, tax_rate, discount_rate,
perpetual_growth_rate, time_max, ...
```

**CompensationStructure fields** (from `model_2_operator/compensation.py`):
```
retainer_amount, retainer_start_month, retainer_escalation_enabled,
rev_share_mode (none|baseline|per_client), rev_share_percentage, rev_share_basis,
rev_share_baseline, rev_share_client_window_months, rev_share_decay_enabled,
rev_share_cap_monthly, rev_share_cap_total, per_deal_amount, per_deal_trigger,
upfront_fee_amount, contract_term_months, ...
```

**Engagement config** (dict):
```
duration_days, ramp_days, ramp_curve (linear|step),
post_engagement (metrics_persist|metrics_decay|metrics_partial), decay_rate_days
```

## Streamlit note

Streamlit runs the entire .py file top-to-bottom on every interaction. All function definitions must come before any code that calls them. Never define functions below the code that uses them.
