import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.DARKLY],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
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
                    dbc.NavItem(dbc.NavLink("Source Data", href="/source-data", active="exact")),
                    dbc.NavItem(dbc.NavLink("GPC Metrics", href="/gpc", active="exact")),
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
                    dbc.DropdownMenuItem("New Session", id="menu-new-session", disabled=True),
                    dbc.DropdownMenuItem("Save Session", id="menu-save-session", disabled=True),
                    dbc.DropdownMenuItem("Save Session As…", id="menu-save-as", disabled=True),
                    dbc.DropdownMenuItem("Open Session…", id="menu-open-session", disabled=True),
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
        navbar,
        dummy_div,
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


if __name__ == "__main__":
    print("🚀 Canneberge Web Server starting on http://0.0.0.0:8050")
    app.run(host="0.0.0.0", port=8050, debug=True)