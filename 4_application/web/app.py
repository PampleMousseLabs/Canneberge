import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output

# Initialize Dash App with multi-page support and Dark theme
app = dash.Dash(
    __name__,
    use_pages=True,  # Enables automatic multi-page routing
    external_stylesheets=[dbc.themes.DARKLY],  # Modern dark theme matching PyQt
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ]
)

app.title = "Project Canneberge"

# Tell HTML to include the Fullscreen JavaScript function
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
                } else {
                    if (document.exitFullscreen) {
                        document.exitFullscreen();
                    }
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

# Top Navigation Bar with "Native Mode" Fullscreen button
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Home & Status", href="/", active="exact")),
        dbc.NavItem(dbc.NavLink("GPC Metrics", href="/gpc", active="exact")),
        dbc.Button("Native Mode ⛶", id="fullscreen-btn", color="info", size="sm", className="ms-3", n_clicks=0),
    ],
    brand="🍒 Canneberge Valuations",
    brand_href="/",
    color="primary",
    dark=True,
    className="mb-4"
)

# Dummy div needed for the clientside callback output
dummy_div = html.Div(id="dummy-output", style={"display": "none"})

# Main App Layout (Shell)
app.layout = dbc.Container(
    [
        navbar,
        dummy_div,
        # This is where page content dynamically loads based on URL:
        dash.page_container
    ],
    fluid=True,
    className="px-4"
)

# Clientside Callback: Triggers browser fullscreen when button is tapped
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks > 0) {
            toggleFullScreen();
        }
        return "";
    }
    """,
    Output("dummy-output", "children"),
    Input("fullscreen-btn", "n_clicks"),
)

if __name__ == "__main__":
    print("🚀 Canneberge Web Server starting on http://0.0.0.0:8050")
    app.run(host="0.0.0.0", port=8050, debug=True)