import dash
import dash_bootstrap_components as dbc
from dash import html, dcc

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

# Simple Top Navigation Bar
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Home & Status", href="/", active="exact")),
        dbc.NavItem(dbc.NavLink("GPC Metrics", href="/gpc", active="exact")),
    ],
    brand="🍒 Canneberge Valuations",
    brand_href="/",
    color="primary",
    dark=True,
    className="mb-4"
)

# Main App Layout (Shell)
app.layout = dbc.Container(
    [
        navbar,
        # This is where page content dynamically loads based on URL:
        dash.page_container
    ],
    fluid=True,
    className="px-4"
)

if __name__ == "__main__":
    # Host '0.0.0.0' allows tablet access on home Wi-Fi
    print("🚀 Canneberge Web Server starting on http://0.0.0.0:8050")
    app.run(host="0.0.0.0", port=8050, debug=True)