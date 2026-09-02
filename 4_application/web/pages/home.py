import dash
import dash_bootstrap_components as dbc
from dash import html

# Register this file as the default home page ('/')
dash.register_page(__name__, path='/', name="Home")

layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H2("System Overview & Control Panel", className="text-light mb-3"),
            html.P(
                "Welcome to Project Canneberge Web Surface. "
                "Select a module from the top bar to begin.",
                className="text-muted"
            ),
            dbc.Card([
                dbc.CardHeader("System Status"),
                dbc.CardBody([
                    html.H5("Core Engine Connected", className="card-title text-success"),
                    html.P("Canneberge.Calculations engine ready for web queries.", className="card-text"),
                ])
            ], color="secondary", outline=True, className="mt-4")
        ])
    ])
])