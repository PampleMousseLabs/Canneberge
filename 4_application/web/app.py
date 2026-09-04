import dash
from pathlib import Path
from datetime import datetime
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, ctx, no_update, ALL
import diskcache
from dash import DiskcacheManager

from web.lib.session_io import (
    save_session_from_stores,
    load_session_to_stores,
    list_available_sessions,
)

# Setup diskcache for non-blocking background tasks
cache_dir = Path.home() / ".canneberge" / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)
cache = diskcache.Cache(str(cache_dir))
background_callback_manager = DiskcacheManager(cache)

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.DARKLY],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    background_callback_manager=background_callback_manager,
)

app.title = "Project Canneberge"

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="manifest" href="/assets/manifest.json">
        <script>
            function toggleFullScreen() {
                if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen();
                } else if (document.exitFullscreen) {
                    document.exitFullscreen();
                }
            }
        </script>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Global top bar (equivalent to desktop main_window chrome)
navbar = dbc.Navbar(
    dbc.Container(
        [
            dbc.NavbarBrand("🍒 Canneberge Valuations", href="/"),
            dbc.Nav(
                [
                    dbc.NavItem(dbc.NavLink("Home", href="/", active="exact")),
                    dbc.NavItem(dbc.NavLink("Subject Financials", href="/subject-financials", active="exact")),
                    dbc.NavItem(dbc.NavLink("Source Data", href="/source-data", active="exact")),
                    dbc.NavItem(dbc.NavLink("GPC Metrics", href="/gpc", active="exact")),
                    dbc.NavItem(dbc.NavLink("DCF", href="/dcf", active="exact")),
                ],
                navbar=True,
                className="me-3",
            ),
            # Project menu (global like desktop File menu)
            dbc.DropdownMenu(
                label="Project",
                nav=True,
                in_navbar=True,
                children=[
                    dbc.DropdownMenuItem("New Session", id="menu-new-session"),
                    dbc.DropdownMenuItem("Save Session", id="menu-save-session"),
                    dbc.DropdownMenuItem("Save Session As…", id="menu-save-as"),
                    dbc.DropdownMenuItem("Open Session…", id="menu-open-session"),
                    dbc.DropdownMenuItem(divider=True),
                    dbc.DropdownMenuItem("Theme / Preferences", id="menu-theme", disabled=True),
                ],
                className="me-3",
            ),
            # Live session chip
            html.Span(
                id="global-session-chip",
                className="badge bg-secondary me-3",
                children="Live session: ready",
            ),
            dbc.Button(
                "Native Mode ⛶",
                id="fullscreen-btn",
                color="info",
                size="sm",
                n_clicks=0,
            ),
        ],
        fluid=True,
    ),
    color="primary",
    dark=True,
    className="mb-3",
)

dummy_div = html.Div(id="dummy-output", style={"display": "none"})

app.layout = dbc.Container(
    [
        dcc.Store(id="session-store", storage_type="session"),
        dcc.Store(id="source-results-store", storage_type="session"),   # NEW - hoisted from source_data page
        dcc.Store(id="session-load-timestamp", storage_type="session"), # NEW - decoupling load hydration from active typing
        dcc.Store(id="session-io-feedback", storage_type="memory"),      # NEW - toast trigger
        dcc.Download(id="session-download"),                              # NEW - browser file download

        navbar,
        dummy_div,

        # --- Session I/O toast + modals ---
        dbc.Toast(
            id="session-toast",
            header="Session",
            is_open=False,
            dismissable=True,
            duration=4000,
            icon="primary",
            style={"position": "fixed", "top": 70, "right": 20, "zIndex": 1500, "minWidth": 300},
        ),

        # Save As modal
        dbc.Modal(
            [
                dbc.ModalHeader("Save Session As…"),
                dbc.ModalBody([
                    dbc.Label("Session name:"),
                    dbc.Input(id="save-as-name-input", type="text", placeholder="e.g. spcx_baseline"),
                    html.Small(
                        f"Saved to: {Path.home() / '.canneberge' / 'sessions'}",
                        className="text-muted d-block mt-2",
                    ),
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="save-as-cancel", color="secondary"),
                    dbc.Button("Save", id="save-as-confirm", color="primary"),
                ]),
            ],
            id="save-as-modal",
            is_open=False,
        ),

        # Open Session modal
        dbc.Modal(
            [
                dbc.ModalHeader("Open Session"),
                dbc.ModalBody(id="open-session-modal-body"),
                dbc.ModalFooter([
                    dbc.Button("Cancel", id="open-session-cancel", color="secondary"),
                ]),
            ],
            id="open-session-modal",
            is_open=False,
            size="lg",
        ),

        dash.page_container,
    ],
    fluid=True,
    className="px-3",
)

# Fullscreen button
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks > 0) { toggleFullScreen(); }
        return '';
    }
    """,
    Output("dummy-output", "children"),
    Input("fullscreen-btn", "n_clicks"),
)

# Global chip mirrors whatever Home (or later pages) put in session-store
@app.callback(
    Output("global-session-chip", "children"),
    Input("session-store", "data"),
)
def update_global_session_chip(data):
    if not data:
        return "Live session: empty"
    subject = data.get("subject_company_name") or "Untitled"
    n = len(data.get("gpc_tickers") or [])
    disk = data.get("disk_session_name") or "not saved to disk"
    return f"Live: {subject} • {n} GPC • Disk: {disk}"

# ============================================================
# SESSION SAVE / LOAD CALLBACKS
# ============================================================

# Save Session — quick-save to the last-used filename, or fall through
# to Save As if no disk name is set yet.
@app.callback(
    Output("session-toast", "is_open", allow_duplicate=True),
    Output("session-toast", "children", allow_duplicate=True),
    Output("session-toast", "icon", allow_duplicate=True),
    Output("session-store", "data", allow_duplicate=True),
    Output("save-as-modal", "is_open", allow_duplicate=True),
    Input("menu-save-session", "n_clicks"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def on_save_session(n_clicks, session_data, source_results):
    if not n_clicks:
        return no_update, no_update, no_update, no_update, no_update

    session_data = session_data or {}
    existing_name = session_data.get("disk_session_name")

    if not existing_name:
        # No prior save target — open Save As modal instead
        return False, "", "primary", no_update, True

    try:
        filepath = Path.home() / ".canneberge" / "sessions" / f"{existing_name}.json"
        saved_path = save_session_from_stores(session_data, source_results, filepath=filepath)
        return True, f"Saved to {saved_path.name}", "success", no_update, no_update
    except Exception as e:
        return True, f"Save failed: {e}", "danger", no_update, no_update


# Save As — open the modal to prompt for a filename
@app.callback(
    Output("save-as-modal", "is_open", allow_duplicate=True),
    Output("save-as-name-input", "value"),
    Input("menu-save-as", "n_clicks"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def on_save_as_open(n_clicks, session_data):
    if not n_clicks:
        return no_update, no_update
    default_name = (session_data or {}).get("subject_company_name", "session").replace(" ", "_")
    return True, default_name


# Save As — cancel or confirm
@app.callback(
    Output("save-as-modal", "is_open", allow_duplicate=True),
    Output("session-toast", "is_open", allow_duplicate=True),
    Output("session-toast", "children", allow_duplicate=True),
    Output("session-toast", "icon", allow_duplicate=True),
    Output("session-store", "data", allow_duplicate=True),
    Input("save-as-cancel", "n_clicks"),
    Input("save-as-confirm", "n_clicks"),
    State("save-as-name-input", "value"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def on_save_as_submit(cancel_clicks, confirm_clicks, name_value, session_data, source_results):
    trig = ctx.triggered_id
    if trig == "save-as-cancel":
        return False, no_update, no_update, no_update, no_update

    if trig == "save-as-confirm":
        if not name_value or not name_value.strip():
            return no_update, True, "Please enter a session name.", "warning", no_update
        try:
            safe_name = name_value.strip().replace(" ", "_")
            filepath = Path.home() / ".canneberge" / "sessions" / f"{safe_name}.json"
            saved_path = save_session_from_stores(session_data or {}, source_results, filepath=filepath)
            # Update disk_session_name so subsequent Save uses this file
            updated_session = dict(session_data or {})
            updated_session["disk_session_name"] = safe_name
            return False, True, f"Saved to {saved_path.name}", "success", updated_session
        except Exception as e:
            return no_update, True, f"Save failed: {e}", "danger", no_update

    return no_update, no_update, no_update, no_update, no_update


# Open Session — populate modal with list of available sessions
@app.callback(
    Output("open-session-modal", "is_open", allow_duplicate=True),
    Output("open-session-modal-body", "children"),
    Input("menu-open-session", "n_clicks"),
    prevent_initial_call=True,
)
def on_open_session_show(n_clicks):
    if not n_clicks:
        return no_update, no_update

    sessions = list_available_sessions()
    if not sessions:
        body = html.P("No saved sessions found in ~/.canneberge/sessions/", className="text-muted")
        return True, body

    items = []
    for s in sessions:
        saved_at_display = s["saved_at"][:19].replace("T", " ") if s["saved_at"] else "unknown"
        items.append(
            dbc.ListGroupItem(
                [
                    html.Div(s["name"], className="fw-bold"),
                    html.Small(f"Saved: {saved_at_display}", className="text-muted"),
                ],
                action=True,
                id={"type": "session-file-item", "path": s["path"]},
                n_clicks=0,
            )
        )
    body = dbc.ListGroup(items)
    return True, body


# Open Session — cancel button
@app.callback(
    Output("open-session-modal", "is_open", allow_duplicate=True),
    Input("open-session-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def on_open_session_cancel(n_clicks):
    if n_clicks:
        return False
    return no_update


# Open Session — a specific file was clicked, load it
@app.callback(
    Output("session-store", "data", allow_duplicate=True),
    Output("source-results-store", "data", allow_duplicate=True),
    Output("session-load-timestamp", "data", allow_duplicate=True),
    Output("open-session-modal", "is_open", allow_duplicate=True),
    Output("session-toast", "is_open", allow_duplicate=True),
    Output("session-toast", "children", allow_duplicate=True),
    Output("session-toast", "icon", allow_duplicate=True),
    Input({"type": "session-file-item", "path": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def on_session_file_clicked(n_clicks_list):
    if not any(n_clicks_list or []):
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    trig = ctx.triggered_id
    if not trig or not isinstance(trig, dict):
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    filepath = Path(trig["path"])
    try:
        session_dict, source_dict, saved_at = load_session_to_stores(filepath)
        return (
            session_dict,
            source_dict,
            str(datetime.now().timestamp()),
            False,
            True,
            f"Loaded {filepath.stem} (saved {saved_at[:19].replace('T', ' ')})",
            "success",
        )
    except Exception as e:
        return no_update, no_update, no_update, no_update, True, f"Load failed: {e}", "danger"


# New Session — clear both stores
@app.callback(
    Output("session-store", "data", allow_duplicate=True),
    Output("source-results-store", "data", allow_duplicate=True),
    Output("session-load-timestamp", "data", allow_duplicate=True),
    Output("session-toast", "is_open", allow_duplicate=True),
    Output("session-toast", "children", allow_duplicate=True),
    Output("session-toast", "icon", allow_duplicate=True),
    Input("menu-new-session", "n_clicks"),
    prevent_initial_call=True,
)
def on_new_session(n_clicks):
    if not n_clicks:
        return no_update, no_update, no_update, no_update, no_update, no_update
    return {}, {}, str(datetime.now().timestamp()), True, "New session started (unsaved).", "info"


if __name__ == "__main__":
    print("🚀 Canneberge Web Server starting on http://0.0.0.0:8050")
    app.run(host="0.0.0.0", port=8050, debug=True)