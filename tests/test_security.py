def test_security():
    from backend.app.security import validate_telegram_init_data
    assert callable(validate_telegram_init_data)
