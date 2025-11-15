## UI Test Helpers

The `ui/tests/mocks.py` module provides lightweight service doubles so Streamlit
pages can be exercised offline (no API calls).  Each mock implements the same
methods as the real service layer (`list_models`, `submit_job`, etc.) and
returns deterministic payloads.  Import `MockServices` and inject it into
`ui.state.session.set_services(...)` within a test to render a page without
network access.

Additional unit tests live under `tests/ui/` (see `test_telemetry.py`) where
client-side spans are asserted without spinning up the full UI.
