"""
ESGRegWatch – Streamlit Dashboard
-----------------------------------
Prototype delivery layer for the ESGRegWatch system.
Demonstrates the customer-facing product: search, regulatory timeline,
impact summaries, and demand evidence.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "processed" / "esgregwatch.sqlite"
DEMAND_JSON = ROOT / "data" / "processed" / "demand_evidence.json"

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ESGRegWatch",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f0f7f4;
    border-left: 4px solid #2e7d5e;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 8px;
}
.priority-high { color: #c0392b; font-weight: 600; }
.priority-medium { color: #e67e22; font-weight: 600; }
.priority-low { color: #27ae60; font-weight: 600; }
.source-badge {
    background: #eaf4ee;
    border: 1px solid #2e7d5e;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.8em;
    color: #2e7d5e;
    font-weight: 600;
}
.tag {
    background: #e8f4fd;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 0.78em;
    color: #1a6394;
    margin-right: 4px;
}
</style>
""", unsafe_allow_html=True)


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_documents():
    if not DB.exists():
        return pd.DataFrame()
    return pd.read_sql("SELECT * FROM documents", sqlite3.connect(DB))


@st.cache_data
def load_demand_evidence():
    if not DEMAND_JSON.exists():
        return {}
    return json.loads(DEMAND_JSON.read_text(encoding="utf-8"))


df = load_documents()
demand = load_demand_evidence()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/48/leaf.png", width=40)
    st.title("ESGRegWatch")
    st.caption("Taiwan ESG & Carbon Regulation Intelligence")
    st.divider()

    st.subheader("🔍 Filters")
    if not df.empty:
        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        sel_category = st.selectbox("Category", categories)

        priorities = ["All", "high", "medium", "low"]
        sel_priority = st.selectbox("Priority", priorities)

        authorities = ["All"] + sorted(df["authority"].dropna().unique().tolist())
        sel_authority = st.selectbox("Authority", authorities)
    else:
        sel_category = sel_priority = sel_authority = "All"

    st.divider()
    st.subheader("📊 System Info")
    if not df.empty:
        st.metric("Total documents", len(df))
        live = (df.get("data_source", pd.Series()) == "live").sum()
        seed = (df.get("data_source", pd.Series()) == "seed").sum()
        st.caption(f"🌐 Live-fetched: {live}  |  📋 Curated: {seed}")
    st.caption("Prototype v1.0 – BDA Spring 2026")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🌿 ESGRegWatch")
st.subheader("Taiwan ESG Regulation & Carbon-Fee Intelligence Dashboard")
st.caption(
    "Monitor ESG and carbon-fee regulatory obligations for Taiwan listed companies. "
    "All sources are official government and exchange announcements with full provenance."
)

tab_search, tab_timeline, tab_demand, tab_system = st.tabs(
    ["🔍 Search Regulations", "📅 Regulatory Timeline", "📈 Demand Evidence", "⚙️ System Design"]
)


# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 – SEARCH
# ════════════════════════════════════════════════════════════════════════════════
with tab_search:
    if df.empty:
        st.warning("⚠️ Database not found. Run the setup commands below:")
        st.code("python scripts/validate_demand.py\npython scripts/ingest.py\npython scripts/build_index.py")
        st.stop()

    query = st.text_input(
        "Search regulations, keywords, or topics",
        placeholder="e.g. carbon fee, IFRS S2, deadline, 25000 tCO2e, disclosure",
        help="Full-text search across title, text, and customer impact fields"
    )

    # Apply sidebar filters
    view = df.copy()
    if sel_category != "All":
        view = view[view["category"] == sel_category]
    if sel_priority != "All":
        view = view[view["priority"] == sel_priority]
    if sel_authority != "All":
        view = view[view["authority"] == sel_authority]

    # Text search
    if query:
        mask = view.apply(
            lambda r: query.lower() in (
                str(r.get("title", "")) + " " +
                str(r.get("text", "")) + " " +
                str(r.get("customer_impact", ""))
            ).lower(),
            axis=1,
        )
        view = view[mask]

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matching documents", len(view))
    c2.metric("High priority", (view["priority"] == "high").sum() if not view.empty else 0)
    c3.metric("Unique authorities", view["authority"].nunique() if not view.empty else 0)
    c4.metric("With fee rates", (view.get("fee_rates", pd.Series()) != "").sum() if not view.empty else 0)

    st.divider()

    if view.empty:
        st.info("No documents match your search. Try broader terms like 'carbon' or 'disclosure'.")
    else:
        # Sort: high priority first
        priority_order = {"high": 0, "medium": 1, "low": 2}
        view = view.copy()
        view["_sort"] = view["priority"].map(priority_order).fillna(3)
        view = view.sort_values("_sort")

        for _, row in view.iterrows():
            priority = row.get("priority", "medium")
            priority_class = f"priority-{priority}"

            with st.container(border=True):
                col_main, col_meta = st.columns([3, 1])

                with col_main:
                    st.markdown(f"### {row.get('title', 'Untitled')}")

                    # Tags
                    cat = row.get("category", "")
                    reg_type = row.get("regulation_type", "")
                    tags_html = ""
                    if cat:
                        tags_html += f'<span class="tag">📁 {cat}</span>'
                    if reg_type:
                        tags_html += f'<span class="tag">⚖️ {reg_type}</span>'
                    if tags_html:
                        st.markdown(tags_html, unsafe_allow_html=True)

                    st.write("")
                    # Text preview
                    text = str(row.get("text", ""))
                    st.write(text[:400] + ("…" if len(text) > 400 else ""))

                    if row.get("customer_impact"):
                        st.info("🎯 **Customer Impact:** " + str(row["customer_impact"]))

                    # Extracted entities
                    entities = []
                    if row.get("fee_rates"):
                        entities.append(f"💰 Fee: {row['fee_rates']}")
                    if row.get("key_years"):
                        entities.append(f"📅 Key years: {row['key_years']}")
                    if row.get("emission_scopes"):
                        entities.append(f"🏭 Scope: {row['emission_scopes']} tCO2e")
                    if entities:
                        st.markdown(" &nbsp;|&nbsp; ".join(entities))

                with col_meta:
                    st.markdown(
                        f'<span class="{priority_class}">▲ {priority.upper()} PRIORITY</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<span class="source-badge">{row.get("authority", "")}</span>',
                        unsafe_allow_html=True,
                    )
                    if row.get("date"):
                        st.caption(f"📆 {row['date']}")
                    if row.get("url"):
                        st.link_button("View source ↗", row["url"])
                    if row.get("top_terms"):
                        with st.expander("TF-IDF terms"):
                            st.caption(row["top_terms"])


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 – REGULATORY TIMELINE
# ════════════════════════════════════════════════════════════════════════════════
with tab_timeline:
    st.subheader("📅 Key Regulatory Deadlines")
    st.caption("Official obligations affecting Taiwan listed companies, sorted by deadline.")

    if demand and demand.get("regulatory_timeline"):
        timeline = demand["regulatory_timeline"]
        for item in sorted(timeline, key=lambda x: x["date"]):
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                with c1:
                    st.markdown(f"**{item['date']}**")
                    st.caption(item["authority"])
                with c2:
                    st.markdown(f"**{item['event']}**")
                    if item.get("rate"):
                        st.markdown(f"💰 Rate: `{item['rate']}`")
                    if item.get("scope"):
                        st.markdown(f"🎯 Scope: {item['scope']}")
                    st.warning("⚠️ " + item["customer_pain"])
                    if item.get("source_url"):
                        st.link_button("Official source ↗", item["source_url"])
    else:
        st.info("Run `python scripts/validate_demand.py` to generate timeline data.")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 – DEMAND EVIDENCE
# ════════════════════════════════════════════════════════════════════════════════
with tab_demand:
    st.subheader("📈 Evidence of Demand & Willingness to Pay")
    st.caption(
        "This section documents the public-data acquisition process used to validate demand "
        "for ESGRegWatch — addressing the course requirement to show *how* evidence was gathered."
    )

    if not demand:
        st.info("Run `python scripts/validate_demand.py` to generate demand evidence.")
    else:
        # Market size
        st.markdown("### 🎯 Addressable Market")
        ms = demand.get("market_size", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Listed companies (TWSE/TPEx)",
                ms.get("total_listed_companies", {}).get("value", "—"),
                help=ms.get("total_listed_companies", {}).get("note", ""),
            )
        with col2:
            st.metric(
                "Carbon-fee regulated entities",
                ms.get("carbon_fee_regulated_entities", {}).get("value", "—"),
            )
        with col3:
            st.metric(
                "ESG consulting firms (Taiwan)",
                ms.get("esg_consulting_firms_taiwan", {}).get("value", "—"),
            )

        st.divider()

        # WTP
        st.markdown("### 💰 Willingness-to-Pay Model")
        wtp = demand.get("willingness_to_pay", {})
        assumptions = wtp.get("assumptions", {})
        savings = wtp.get("monthly_savings", {})
        pricing = wtp.get("pricing_recommendation", {})

        with st.expander("📐 Model assumptions", expanded=True):
            st.markdown(f"""
| Parameter | Value |
|---|---|
| Hours/month monitoring (status quo) | {assumptions.get('hours_per_month_monitoring', '')} hrs |
| Fully-loaded hourly cost | NT${assumptions.get('hourly_cost_NTD', ''):,} |
| Hours saved by ESGRegWatch | {savings.get('hours_saved', '')} hrs |
| Monthly value of time saved | **NT${savings.get('value_NTD', 0):,}** |
| Basic plan price | NT${pricing.get('basic_plan_NTD', 0):,}/month |
| ROI | **Positive from month 1** |
""")

        col1, col2, col3 = st.columns(3)
        col1.metric("Basic Plan", f"NT${pricing.get('basic_plan_NTD',0):,}/mo", "1 company, 5 users")
        col2.metric("Professional", f"NT${pricing.get('professional_plan_NTD',0):,}/mo", "Multi-dept + audit trail")
        col3.metric("Consulting Firm", f"NT${pricing.get('consulting_firm_plan_NTD',0):,}/mo", "Multi-client workspace")

        st.divider()
        st.markdown("### 🔍 Comparable Products")
        for comp in wtp.get("comparable_products", []):
            price = comp.get("price_usd") or comp.get("price_NTD", "")
            st.markdown(f"**{comp['name']}** — {price} — _{comp['note']}_")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 4 – SYSTEM DESIGN
# ════════════════════════════════════════════════════════════════════════════════
with tab_system:
    st.subheader("⚙️ Technical System Design")

    st.markdown("""
### End-to-End Pipeline

```
Data Sources          Ingestion              Storage                Processing           Delivery
─────────────────     ─────────────────      ─────────────────      ─────────────────    ──────────────
FSC press releases    Airflow daily jobs     Raw: Object store      Entity extraction    Web dashboard
TWSE announcements ─► Requests +          ─► (S3 / MinIO)        ─► (fee, deadline,  ─► Email/LINE alerts
MOENV regulations     BeautifulSoup          Versioned HTML/PDF     scope, authority)    PDF briefs
IFRS jurisdiction     PDF text extract       ─────────────────      ─────────────────    Exportable CSV
profiles              Kafka queue (scale)    Warehouse:             TF-IDF + future      REST API
Client uploads                               PostgreSQL +           LLM summariser
(future)                                     OpenSearch / pgvector
```

### Technology Choices & Rationale
""")

    tech_data = {
        "Component": ["Ingestion orchestration", "HTML/PDF fetching", "Raw storage", "Structured store",
                       "Full-text search", "Batch processing (scale)", "Message queue (scale)", "Delivery"],
        "Prototype (this repo)": ["Python schedule", "requests + BeautifulSoup", "JSONL files", "SQLite",
                                   "pandas str.contains + TF-IDF", "pandas", "—", "Streamlit"],
        "Production design": ["Apache Airflow", "requests + BeautifulSoup + pdfminer", "S3 / MinIO (versioned)",
                               "PostgreSQL", "OpenSearch / pgvector", "Apache Spark", "Kafka", "React SPA + REST API"],
        "Why appropriate": [
            "DAG-based scheduling handles dependencies and retries",
            "Standard for HTML; PDF extraction preserves layout metadata",
            "Versioned raw store enables audit trail and re-processing",
            "Structured queries for regulatory entity filtering",
            "Semantic search for regulation interpretation queries",
            "1,000+ annual sustainability reports need batch processing",
            "High-priority regulation updates need low-latency alerting",
            "Dashboard + API covers both human and machine consumers",
        ]
    }
    st.dataframe(pd.DataFrame(tech_data), use_container_width=True, hide_index=True)

    st.markdown("""
### Scalability

| Scale | Infrastructure | Monthly cost estimate |
|---|---|---|
| Prototype (8 docs) | Single VM + SQLite | < NT$500 |
| 10× (hundreds of docs) | Managed PostgreSQL + OpenSearch | ~NT$5,000 |
| 100× (all sustainability reports) | Airflow + S3 + Spark cluster | ~NT$30,000 |

The biggest cost driver is **human review** of high-impact regulatory summaries, not compute.
    """)
