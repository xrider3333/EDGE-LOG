"""AUGUR HTTP API — FastAPI surface over augur_engine (streamlit-free).

Step 2 of the EDGELOG split (docs/EDGELOG_ARCHITECTURE.md): the local runner and
the EDGELOG web frontend call these endpoints; the compute stays on this PC.
Run:  uvicorn api.server:app --reload --port 8787
"""
