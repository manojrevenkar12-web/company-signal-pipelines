from signals.config import design, settings
from signals.resolve.match import resolve
from signals.resolve.records import SourceRecord


def rec(i, feed, names, domain="", city="", country="", founded=None, ident=""):
    return SourceRecord(f"{feed}:{i}", feed, names, domain, city, country, founded, ident)


def test_an_equal_domain_decides():
    a = rec(1, "vendor_profiles", ["Nova Robotics"], "nova.de")
    b = rec(2, "job_posts", [], "nova.de")
    res = resolve([a, b], design(), settings())
    assert res.entity_of[a.id] == res.entity_of[b.id]


def test_umlauts_and_legal_forms_do_not_split_a_company():
    a = rec(1, "register_notices", ["Grünfeld Robotics GmbH"], "", "Köln", "DE", 2019, "register:K|HRB 1")
    b = rec(2, "vendor_profiles", ["Gruenfeld Robotics"], "gruenfeldrobotics.de", "Köln", "DE", 2019)
    res = resolve([a, b], design(), settings())
    assert res.entity_of[a.id] == res.entity_of[b.id]
    plain = resolve([a, b], design({"er_transliterate": False}), settings())
    assert plain.entity_of[a.id] != plain.entity_of[b.id]


def test_two_register_numbers_never_merge_even_through_a_chain():
    a = rec(1, "register_notices", ["Nova Robotics GmbH"], "", "Berlin", "DE", 2019, "register:B|HRB 1")
    b = rec(2, "register_notices", ["Nova Robotics GmbH"], "", "Berlin", "DE", 2019, "register:B|HRB 2")
    v = rec(3, "vendor_profiles", ["Nova Robotics"], "nova.de", "Berlin", "DE", 2019)
    res = resolve([a, b, v], design(), settings())
    assert res.entity_of[a.id] != res.entity_of[b.id]
    assert res.refused or res.review


def test_a_missing_field_does_not_count_against_a_pair():
    a = rec(1, "register_notices", ["Velva Security GmbH"], "", "Graz", "AT", 2020, "register:G|HRB 9")
    b = rec(2, "vendor_profiles", ["Velva Security"], "velva.at", "Graz", "AT", 2020)
    res = resolve([a, b], design(), settings())
    assert res.entity_of[a.id] == res.entity_of[b.id]
    raw = resolve([a, b], design({"er_renormalise": False}), settings())
    assert raw.entity_of[a.id] != raw.entity_of[b.id]


def test_same_name_in_different_cities_is_a_question_not_a_merge():
    a = rec(1, "vendor_profiles", ["Arvel AI"], "arvel.ai", "Berlin", "DE", 2019)
    b = rec(2, "vendor_profiles", ["Arvel AI"], "arvel-ai.io", "Paris", "FR", 2021)
    res = resolve([a, b], design(), settings())
    assert res.entity_of[a.id] != res.entity_of[b.id]
