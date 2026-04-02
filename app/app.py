import os
import json

import dash
from dash import dcc, html, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc

import backend

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="Pokemon Card Explorer",
)

CARDS_PER_PAGE = 20

# Load initial data at startup
try:
    metrics = backend.get_metrics()
    initial_cards = backend.get_default_cards(limit=200)
except Exception as e:
    print(f"Failed to load initial data: {e}")
    metrics = {"total_cards": 0, "rare_cards": 0, "total_sets": 0}
    initial_cards = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RARITY_COLORS = {"Common": "success", "Uncommon": "primary", "Rare": "warning"}


def render_card(card):
    rarity = card.get("rarity", "Common") or "Common"
    color = RARITY_COLORS.get(rarity, "secondary")
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardImg(
                    src=card.get("image_url", ""),
                    top=True,
                    style={"objectFit": "contain", "height": "300px"},
                ),
                dbc.CardBody(
                    [
                        html.H5(card.get("name", ""), className="card-title"),
                        html.P(
                            f"Set: {card.get('set_name', '')}",
                            className="text-muted mb-1",
                            style={"fontSize": "0.85rem"},
                        ),
                        dbc.Badge(rarity, color=color, className="me-2"),
                        html.Small(
                            f"HP: {card.get('hp', '?')}",
                            className="text-muted",
                        ),
                    ]
                ),
            ],
            className="mb-3 h-100",
        ),
        xs=12,
        sm=6,
        md=4,
        lg=3,
    )


def make_metric_card(title, value, icon_class):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className=f"fas {icon_class} me-2"),
                        html.Span(title, className="text-muted"),
                    ]
                ),
                html.H3(f"{value:,}", className="mt-2 mb-0"),
            ]
        ),
        className="shadow-sm",
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = dbc.Container(
    [
        # -- Header --
        dbc.Navbar(
            dbc.Container(
                [
                    dbc.NavbarBrand(
                        [
                            html.I(className="fas fa-bolt me-2"),
                            "Pokemon Card Explorer",
                        ],
                        className="fs-4",
                    ),
                    dbc.NavbarBrand(
                        "Powered by Databricks",
                        className="ms-auto text-muted small",
                    ),
                ],
                fluid=True,
            ),
            color="dark",
            dark=True,
            className="mb-4",
        ),
        # -- Metrics row --
        dbc.Row(
            [
                dbc.Col(id="metric-total-cards", md=4),
                dbc.Col(id="metric-rare-cards", md=4),
                dbc.Col(id="metric-card-sets", md=4),
            ],
            id="metrics-row",
            className="mb-4",
        ),
        # -- Search section --
        dbc.Row(
            [
                dbc.Col(
                    dbc.InputGroup(
                        [
                            dbc.Input(
                                id="search-input",
                                placeholder="Search for Pokemon cards...",
                                type="text",
                                debounce=True,
                            ),
                            dbc.Button(
                                [html.I(id="search-icon", className="fas fa-search me-1"), html.Span(id="search-label", children="Search")],
                                id="search-button",
                                color="primary",
                                n_clicks=0,
                            ),
                            dbc.Button(
                                "Clear",
                                id="clear-button",
                                color="secondary",
                                outline=True,
                                n_clicks=0,
                            ),
                        ],
                        size="lg",
                    ),
                    md=6,
                ),
                dbc.Col(
                    dbc.Switch(
                        id="agent-search-toggle",
                        label="Agent Search",
                        value=False,
                        className="fs-5",
                    ),
                    md=2,
                    className="d-flex align-items-center",
                ),
                dbc.Col(
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "All", id="filter-all", color="dark",
                                outline=True, active=True, n_clicks=0,
                            ),
                            dbc.Button(
                                "Common", id="filter-common", color="success",
                                outline=True, n_clicks=0,
                            ),
                            dbc.Button(
                                "Uncommon", id="filter-uncommon", color="primary",
                                outline=True, n_clicks=0,
                            ),
                            dbc.Button(
                                "Rare", id="filter-rare", color="warning",
                                outline=True, n_clicks=0,
                            ),
                        ],
                        className="w-100",
                    ),
                    md=4,
                    className="d-flex align-items-center",
                ),
            ],
            className="mb-3",
        ),
        # -- Agent query rewrite banner --
        html.Div(id="agent-banner"),
        # -- Result count --
        html.Div(id="result-count", className="text-muted mb-3"),
        # -- Card gallery --
        dbc.Row(id="card-gallery"),
        # -- Pagination --
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        [html.I(className="fas fa-chevron-left me-1"), "Previous"],
                        id="prev-btn",
                        color="secondary",
                        outline=True,
                        n_clicks=0,
                    ),
                    width="auto",
                ),
                dbc.Col(
                    html.Span(id="page-info", className="text-muted align-self-center"),
                    className="d-flex justify-content-center",
                ),
                dbc.Col(
                    dbc.Button(
                        ["Next ", html.I(className="fas fa-chevron-right ms-1")],
                        id="next-btn",
                        color="secondary",
                        outline=True,
                        n_clicks=0,
                    ),
                    width="auto",
                ),
            ],
            justify="between",
            align="center",
            className="mt-3 mb-5",
        ),
        # -- Client-side stores --
        dcc.Store(id="cards-store", data=initial_cards),
        dcc.Store(id="page-store", data=0),
        dcc.Store(id="rarity-store", data="All"),
    ],
    fluid=True,
)

# ---------------------------------------------------------------------------
# Callback 0: Toggle search button icon/label on Agent Search switch
# ---------------------------------------------------------------------------
@app.callback(
    [Output("search-icon", "className"), Output("search-label", "children")],
    Input("agent-search-toggle", "value"),
)
def update_search_button_style(agent_mode):
    if agent_mode:
        return "fas fa-robot me-1", "Agent Search"
    return "fas fa-search me-1", "Search"


# ---------------------------------------------------------------------------
# Callback 1: Rarity filter selection
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("filter-all", "active"),
        Output("filter-common", "active"),
        Output("filter-uncommon", "active"),
        Output("filter-rare", "active"),
        Output("rarity-store", "data"),
    ],
    [
        Input("filter-all", "n_clicks"),
        Input("filter-common", "n_clicks"),
        Input("filter-uncommon", "n_clicks"),
        Input("filter-rare", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def update_rarity_filter(*_):
    ctx = callback_context
    if not ctx.triggered:
        return True, False, False, False, "All"
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    mapping = {
        "filter-all": ("All", [True, False, False, False]),
        "filter-common": ("Common", [False, True, False, False]),
        "filter-uncommon": ("Uncommon", [False, False, True, False]),
        "filter-rare": ("Rare", [False, False, False, True]),
    }
    rarity, actives = mapping.get(btn_id, ("All", [True, False, False, False]))
    return *actives, rarity


# ---------------------------------------------------------------------------
# Callback 2: Search / filter / clear → update cards-store
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("cards-store", "data"),
        Output("page-store", "data", allow_duplicate=True),
        Output("result-count", "children"),
        Output("search-input", "value"),
        Output("agent-banner", "children"),
    ],
    [
        Input("search-button", "n_clicks"),
        Input("search-input", "n_submit"),
        Input("clear-button", "n_clicks"),
        Input("rarity-store", "data"),
    ],
    [State("search-input", "value"), State("agent-search-toggle", "value")],
    prevent_initial_call=True,
)
def update_cards(search_clicks, search_submit, clear_clicks, rarity, query, agent_mode):
    ctx = callback_context
    trigger = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""

    # Clear button → reset
    if trigger == "clear-button":
        cards = backend.get_default_cards(limit=200)
        return cards, 0, f"Showing all {len(cards)} cards", "", None

    # Search query present
    if query and query.strip():
        banner = None

        if agent_mode:
            expanded = backend.expand_query(query.strip())
            cards = backend.search_cards(expanded, num_results=50)
            msg = f'Agent Search: {len(cards)} results'
            banner = dbc.Alert(
                [
                    html.I(className="fas fa-robot me-2"),
                    html.Strong("Agent rewrote your query: "),
                    html.Em(expanded),
                ],
                color="info",
                dismissable=True,
                className="mb-3",
            )
        else:
            cards = backend.search_cards(query.strip(), num_results=50)
            msg = f'Found {len(cards)} cards for "{query.strip()}"'

        return cards, 0, msg, no_update, banner

    # No query — rarity filter only
    if rarity and rarity != "All":
        cards = backend.get_default_cards_filtered(rarity, limit=200)
        return cards, 0, f"Showing {len(cards)} {rarity} cards", no_update, None

    # Default
    cards = backend.get_default_cards(limit=200)
    return cards, 0, f"Showing all {len(cards)} cards", no_update, None


# ---------------------------------------------------------------------------
# Callback 2b: Update metrics when cards-store or rarity filter changes
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("metric-total-cards", "children"),
        Output("metric-rare-cards", "children"),
        Output("metric-card-sets", "children"),
    ],
    [Input("cards-store", "data"), Input("rarity-store", "data")],
    State("search-input", "value"),
)
def update_metrics(cards, rarity, query):
    if query and query.strip() and cards:
        # Search is active — compute from VS results (complete set, not capped)
        total = len(cards)
        rare = sum(1 for c in cards if c.get("rarity") == "Rare")
        sets = len({c.get("set_name") for c in cards if c.get("set_name")})
    else:
        # Default/filtered view — query Lakebase for real counts
        m = backend.get_metrics(rarity)
        total = m["total_cards"]
        rare = m["rare_cards"]
        sets = m["total_sets"]
    return (
        make_metric_card("Total Cards", total, "fa-layer-group"),
        make_metric_card("Rare Cards", rare, "fa-star"),
        make_metric_card("Card Sets", sets, "fa-folder-open"),
    )


# ---------------------------------------------------------------------------
# Callback 3: Render gallery from store + page
# ---------------------------------------------------------------------------
@app.callback(
    [
        Output("card-gallery", "children"),
        Output("page-info", "children"),
        Output("prev-btn", "disabled"),
        Output("next-btn", "disabled"),
    ],
    [Input("cards-store", "data"), Input("page-store", "data")],
)
def render_gallery(cards, page):
    if not cards:
        return [html.P("No cards found.", className="text-muted text-center w-100")], "", True, True

    total = len(cards)
    start = page * CARDS_PER_PAGE
    end = min(start + CARDS_PER_PAGE, total)
    page_cards = cards[start:end]
    total_pages = (total + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    gallery = [render_card(c) for c in page_cards]
    info = f"Showing {start + 1}-{end} of {total} cards"

    return gallery, info, page <= 0, page >= total_pages - 1


# ---------------------------------------------------------------------------
# Callback 4: Pagination
# ---------------------------------------------------------------------------
@app.callback(
    Output("page-store", "data"),
    [Input("prev-btn", "n_clicks"), Input("next-btn", "n_clicks")],
    [State("page-store", "data"), State("cards-store", "data")],
    prevent_initial_call=True,
)
def paginate(prev_clicks, next_clicks, current_page, cards):
    ctx = callback_context
    if not ctx.triggered:
        return no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    total = len(cards) if cards else 0
    total_pages = max(1, (total + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)

    if trigger == "prev-btn":
        return max(0, current_page - 1)
    elif trigger == "next-btn":
        return min(total_pages - 1, current_page + 1)
    return no_update


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)),
        debug=False,
    )
