import cache_service


def test_cache_round_trip_and_unicode():
    cache_service.save_to_cache("Été/夏", {"text": "été 夏"})
    assert cache_service.get_from_cache("Été/夏") == {"text": "été 夏"}


def test_cache_keys_do_not_collide():
    cache_service.save_to_cache("a/b", 1)
    cache_service.save_to_cache("ab", 2)
    assert cache_service.get_from_cache("a/b") == 1
    assert cache_service.get_from_cache("ab") == 2


def test_corrupt_cache_is_miss():
    cache_service.save_to_cache("bad", {})
    cache_service._get_cache_filepath("bad").write_text("invalid json")
    assert cache_service.get_from_cache("bad") is None


def test_cache_miss():
    assert cache_service.get_from_cache("missing") is None
