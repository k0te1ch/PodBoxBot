def test_enter_method(wordpress):
    with wordpress as entered_wp:
        assert entered_wp is wordpress
