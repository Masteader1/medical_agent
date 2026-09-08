"""
Medical Agent — Clinic Administration Dashboard
Connects directly to the PostgreSQL database (sync driver) for read-only queries.
"""

import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database Connection (Sync)
# Streamlit runs synchronously, so we swap asyncpg → psycopg2/psycopg sync.
# ---------------------------------------------------------------------------
_raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/medical_db",
)
SYNC_DATABASE_URL = _raw_url.replace("postgresql+asyncpg", "postgresql+psycopg")

engine = create_engine(SYNC_DATABASE_URL, echo=False)


def run_query(query: str) -> pd.DataFrame:
    """Execute a read-only SQL query and return a DataFrame."""
    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()
        columns = list(result.keys())
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Medical Agent — Admin Dashboard",
    page_icon="🏥",
    layout="wide",
)

st.title("🏥 Medical Agent — Clinic Administration Dashboard")
st.caption(f"Connected to: `{SYNC_DATABASE_URL.split('@')[-1]}`  •  Refreshed at {datetime.now().strftime('%H:%M:%S')}")

if st.button("🔄 Refresh All Data"):
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_appointments, tab_audit, tab_transcripts = st.tabs([
    "📅 Appointments",
    "📨 Webhook Audit Log",
    "💬 Chat Transcripts",
])

# ---- Tab 1: Appointments ---------------------------------------------------
with tab_appointments:
    st.header("Upcoming Appointments")

    appointments_query = """
        SELECT
            a.id        AS appointment_id,
            a.patient_id,
            d.name      AS doctor_name,
            d.department,
            s.start_time,
            s.is_booked,
            d.tenant_id
        FROM appointment a
        JOIN slot s   ON a.slot_id  = s.id
        JOIN doctor d ON s.doctor_id = d.id
        ORDER BY s.start_time ASC
    """

    df_appts = run_query(appointments_query)

    if df_appts.empty:
        st.info("No appointments found.")
    else:
        # Metrics row
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Appointments", len(df_appts))
        col2.metric("Unique Patients", df_appts["patient_id"].nunique())
        col3.metric("Departments", df_appts["department"].nunique())

        st.dataframe(df_appts, use_container_width=True, hide_index=True)

    st.subheader("Available Slots")
    slots_query = """
        SELECT
            s.id        AS slot_id,
            d.name      AS doctor_name,
            d.department,
            s.start_time,
            s.is_booked,
            d.tenant_id
        FROM slot s
        JOIN doctor d ON s.doctor_id = d.id
        ORDER BY s.start_time ASC
    """
    df_slots = run_query(slots_query)

    if df_slots.empty:
        st.info("No slots found in the database.")
    else:
        booked = df_slots["is_booked"].sum()
        available = len(df_slots) - booked
        col1, col2 = st.columns(2)
        col1.metric("Available Slots", int(available))
        col2.metric("Booked Slots", int(booked))

        st.dataframe(df_slots, use_container_width=True, hide_index=True)


# ---- Tab 2: Webhook Audit Log ----------------------------------------------
with tab_audit:
    st.header("Webhook Audit Log (ProcessedMessage)")

    audit_query = """
        SELECT
            id,
            wamid,
            tenant_id,
            patient_phone,
            created_at
        FROM processed_messages
        ORDER BY created_at DESC
        LIMIT 200
    """

    df_audit = run_query(audit_query)

    if df_audit.empty:
        st.info("No processed messages found. Send a WhatsApp message to populate this table.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("Total Messages Processed", len(df_audit))
        col2.metric("Unique Patients", df_audit["patient_phone"].nunique())

        st.dataframe(df_audit, use_container_width=True, hide_index=True)


# ---- Tab 3: Chat Transcripts -----------------------------------------------
with tab_transcripts:
    st.header("LangGraph Chat Transcripts")
    st.caption("Raw checkpoint data from AsyncPostgresSaver. Each row is a conversation state snapshot.")

    # LangGraph's AsyncPostgresSaver creates a 'checkpoints' table.
    # Check which checkpoint tables exist.
    table_check = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'checkpoint%'
        ORDER BY table_name
    """
    df_tables = run_query(table_check)

    if df_tables.empty:
        st.warning("No LangGraph checkpoint tables found. Start a conversation first.")
    else:
        st.success(f"Found checkpoint tables: {', '.join(df_tables['table_name'].tolist())}")

        for tbl in df_tables["table_name"].tolist():
            st.subheader(f"Table: `{tbl}`")

            # Get row count
            count_df = run_query(f"SELECT COUNT(*) as cnt FROM {tbl}")
            row_count = count_df["cnt"].iloc[0] if not count_df.empty else 0
            st.metric(f"Rows in `{tbl}`", int(row_count))

            if row_count > 0:
                # Fetch latest 100 rows. Column names vary by LangGraph version,
                # so we just SELECT * and let pandas figure out the schema.
                transcript_query = f"SELECT * FROM {tbl} LIMIT 100"
                df_transcripts = run_query(transcript_query)

                # If there's a 'thread_id' column, offer a filter
                if "thread_id" in df_transcripts.columns:
                    thread_ids = ["All"] + sorted(df_transcripts["thread_id"].unique().tolist())
                    selected_thread = st.selectbox(
                        f"Filter by Thread ID ({tbl})",
                        thread_ids,
                        key=f"thread_filter_{tbl}",
                    )
                    if selected_thread != "All":
                        df_transcripts = df_transcripts[
                            df_transcripts["thread_id"] == selected_thread
                        ]

                # Try to pretty-print any JSON/binary columns
                for col in df_transcripts.columns:
                    if df_transcripts[col].dtype == object:
                        try:
                            df_transcripts[col] = df_transcripts[col].apply(
                                lambda v: json.dumps(json.loads(v), indent=2)
                                if isinstance(v, str) and v.startswith(("{", "["))
                                else v
                            )
                        except Exception:
                            pass  # Leave non-JSON columns as-is

                st.dataframe(df_transcripts, use_container_width=True, hide_index=True)
            else:
                st.info(f"Table `{tbl}` is empty.")

