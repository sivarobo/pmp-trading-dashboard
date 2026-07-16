"""
db.py
Neon Postgres connection + schema setup for the Trading Journal and Risk Manager.

Setup:
  1. In your Neon project, copy the connection string (looks like:
     postgresql://user:password@ep-xxxx.region.aws.neon.tech/dbname?sslmode=require)
  2. Set it as an env var: DATABASE_URL
     - Locally: add to your .env file -> DATABASE_URL="postgresql://..."
     - Streamlit Cloud: add to Secrets -> DATABASE_URL = "postgresql://..."
  3. Tables are created automatically on first run (init_db() below).

This reuses the same PMP stack pattern as pmpsuite.in (Neon Postgres).
"""

import os
import streamlit as st
import psycopg2
import psycopg2.extras


@st.cache_resource
def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise EnvironmentError(
            "Set DATABASE_URL env var (Neon Postgres connection string) before using "
            "the Trading Journal / Risk Manager. See modules/db.py docstring for setup steps."
        )
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    return conn


def init_db():
    """Creates tables if they don't exist yet. Safe to call on every page load."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                id SERIAL PRIMARY KEY,
                entry_date DATE NOT NULL,
                entry_time TIME,
                exit_time TIME,
                instrument TEXT,
                structure TEXT,
                regime_call TEXT,
                entry_reason TEXT,
                planned_sl NUMERIC,
                planned_target NUMERIC,
                max_loss NUMERIC,
                exit_reason TEXT,
                pnl NUMERIC,
                rule_adherence BOOLEAN,
                rule_violation TEXT,
                mistake_category TEXT,
                lesson TEXT,
                emotional_state_entry INTEGER,
                emotional_state_exit INTEGER,
                screenshot_note TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS risk_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                capital NUMERIC NOT NULL DEFAULT 1000000,
                max_daily_loss_pct NUMERIC NOT NULL DEFAULT 1.5,
                max_weekly_loss_pct NUMERIC NOT NULL DEFAULT 3.0,
                max_monthly_loss_pct NUMERIC NOT NULL DEFAULT 5.0,
                max_deployment_pct NUMERIC NOT NULL DEFAULT 60.0,
                risk_per_trade_pct NUMERIC NOT NULL DEFAULT 1.5,
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT single_row CHECK (id = 1)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_checklist (
                check_date DATE PRIMARY KEY,
                items JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        # ensure a default risk_settings row exists
        cur.execute("""
            INSERT INTO risk_settings (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING;
        """)
