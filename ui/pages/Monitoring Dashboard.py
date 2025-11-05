from __future__ import annotations

import runpy


def main() -> None:
    """
    Thin wrapper that renders the existing monitoring dashboard as a Streamlit page.

    This keeps the dashboard logic in `app/monitoring/dashboard.py` unchanged while
    exposing it through Streamlit's native multipage routing.
    """

    runpy.run_module("app.monitoring.dashboard", run_name="__main__")


if __name__ == "__main__":
    main()
