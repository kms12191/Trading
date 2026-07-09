from backend.services.ml_scheduler import get_stock_shadow_preset_keys


def test_get_stock_shadow_preset_keys():
    expected = ["kr-stock-v1-full", "us-stock-v1-full", "stock-v11-full"]
    actual = get_stock_shadow_preset_keys()
    assert actual == expected
