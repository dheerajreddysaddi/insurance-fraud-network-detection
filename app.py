"""Streamlit entry point.  Run with:  python -m streamlit run app.py"""
import streamlit as st

from src import app_data, config, database, fraud_detection, ui
from views import claims, evaluation_page, indicators, network, overview, workspace

st.set_page_config(page_title="Fraud Network Review", layout="wide")

PAGES = {
    "Overview": overview,
    "Claims Explorer": claims,
    "Network Analysis": network,
    "Fraud Indicators & Exceptions": indicators,
    "Investigation Workspace": workspace,
    "Evaluation": evaluation_page,
}


@st.cache_resource(show_spinner=False)
def init_database() -> str:
    """Connects and creates any missing tables (never deletes or overwrites anything)."""
    database.check_connection()
    database.create_schema()
    return database.get_engine().dialect.name


def main() -> None:
    ui.inject_css()
    try:
        dialect = init_database()
    except (database.DatabaseError, config.ConfigError) as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # noqa: BLE001 - show the type only; messages can contain connection details
        st.error(f"Database error ({type(exc).__name__}). Check DATABASE_URL and the app logs.")
        st.stop()

    page = st.session_state.setdefault("page", "Overview")
    with st.sidebar:
        ui.brand()
        ui.nav(list(PAGES))
        st.divider()
        label = f"Signed in: {ui.reviewer()}" if ui.reviewer() else "Reviewer sign-in & tools"
        with st.expander(label, expanded=not ui.reviewer()):
            ui.sidebar_login(dialect)
            st.divider()
            if st.button("Reload data"):
                st.cache_data.clear()
                st.rerun()
            if st.button("Run detection now"):
                if not ui.reviewer():
                    st.warning("Sign in first.")
                else:
                    with st.spinner("Running detection..."):
                        app_data.run_detection_and_save()
                    ui.flash("Detection finished. It was saved as a new run; earlier runs are kept.")
                    st.rerun()
        st.caption("Database: " + ("local SQLite file" if dialect == "sqlite" else "hosted PostgreSQL"))
        st.caption("A high score means review recommended, not fraud proven.")

    version = app_data.source_version()
    tables = app_data.load_source_tables(version)
    if tables["claims"].empty:
        st.warning("The database has no claims yet. Load data from a terminal:\n\n"
                   "`python scripts/generate_data.py --scale full --replace`\n\n"
                   "(for a hosted database, set DATABASE_URL first; see DEPLOYMENT.md).")
        return

    run = app_data.latest_run()
    analysis = app_data.load_analysis(run["run_id"], version) if run else None
    if run and run["rules_hash"] != fraud_detection.rules_hash(fraud_detection.load_rules()):
        st.sidebar.warning("detection_rules.yaml changed since the last run. Press 'Run detection now'.")

    ui.show_flash()
    PAGES[page].render({"tables": tables, "analysis": analysis, "run": run, "src_version": version})


main()