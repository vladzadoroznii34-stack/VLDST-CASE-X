def test_routes():
    from backend.app.main import app
    paths={r.path for r in app.routes}
    assert '/health' in paths and '/api/cases/open' in paths and '/api/shop/invoice' in paths
