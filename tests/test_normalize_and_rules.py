from signals.classify.rules import rule_label
from signals.normalize import compact_key, domain_key, name_key


def test_names_compare_without_legal_form_umlauts_or_typed_suffix():
    assert name_key("Grünfeld Robotics GmbH") == "gruenfeld robotics"
    assert name_key("Gruenfeld Robotics") == "gruenfeld robotics"
    assert name_key("Velva Security GbmH") == "velva security"       # a typed GmbH is still a legal form
    assert name_key("Near B.V.") == "near"
    assert compact_key("Lixft Pa yAG") == "lixftpay"


def test_domains_lose_scheme_www_and_path():
    assert domain_key("https://www.Nova-Robotics.de/en/about") == "nova-robotics.de"
    assert domain_key("NOVA.IO") == "nova.io"
    assert domain_key(None) == ""


def test_rules_name_the_relationship_in_english_and_german():
    assert rule_label("Nordhaus AG acquires Nova Robotics.") == "acquisition"
    assert rule_label("Nordhaus übernimmt das Start-up Nova.") == "acquisition"
    assert rule_label("Elbtal testet die Technologie von Nova in einem Pilotprojekt.") == "poc"
    assert rule_label("After a successful pilot, Elbtal deploys Nova company-wide.") == "implementation"
    assert rule_label("Der Corporate-VC von Elbtal investiert in Nova.") == "investment"


def test_rules_leave_vague_wording_to_a_model():
    assert rule_label("Elbtal and Nova are working together on the next generation of products.") is None
    assert rule_label("Elbtal und Nova arbeiten künftig enger zusammen.") is None
    assert rule_label("Elbtal takes a minority stake in Nova.") is None
