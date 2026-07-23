from backend import worker


def test_trading_worker_mode_excludes_non_trading_schedulers():
    assert worker.is_trading_worker_mode("trading") is True
    assert worker.is_trading_worker_mode("TRADING") is True
    assert worker.is_trading_worker_mode("full") is False
    assert worker.is_trading_worker_mode("") is False


def test_ai_fund_execution_is_disabled_until_the_execution_node_is_explicitly_enabled():
    assert worker.is_ai_fund_execution_enabled(None) is False
    assert worker.is_ai_fund_execution_enabled("false") is False
    assert worker.is_ai_fund_execution_enabled("true") is True
