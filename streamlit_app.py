"""Launch with python -m streamlit run streamlit_app.py from this project root."""

import sys
from pathlib import Path

# Also works from a checkout before editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st  # noqa: E402

from geo_research.dashboard.app import main as legacy_main  # noqa: E402
from geo_research.dashboard.platform import main as platform_main  # noqa: E402

# V1 is opt-in, including when GEO_DASHBOARD_DB points at a synthetic demo.
mode = st.sidebar.selectbox(
	"Workspace", ["Legacy explorer", "V1 Platform"], index=0,
	key="dashboard_workspace",
)
if mode == "V1 Platform":
	platform_main()
else:
	legacy_main()