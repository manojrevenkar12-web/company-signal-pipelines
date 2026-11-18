from types import SimpleNamespace

from signals.classify.cascade import classify
from signals.classify.claude import ClaudeModel
from signals.classify.link import Gazetteer
from signals.config import design, settings


class Fake:
    def __init__(self, label, conf, tokens=300):
        self.name, self.answer = "fake", (label, conf, tokens)
        self.calls = 0

    def label(self, article):
        self.calls += 1
        return self.answer


ART = {"url": "u1", "text": "Elbtal and Nova are working together on the next generation of products."}


def test_a_rule_costs_nothing_and_calls_no_model():
    cheap, exp = Fake("poc", 0.99), Fake("poc", 0.99)
    d = classify({"url": "u", "text": "Elbtal acquires Nova."}, design(), settings(), cheap, exp)
    assert (d.label, d.decided_by, d.cost_eur, cheap.calls) == ("acquisition", "rule", 0.0, 0)


def test_an_unsure_small_model_escalates_and_an_unsure_large_model_goes_to_a_person():
    cheap, exp = Fake("partnership", 0.60), Fake("poc", 0.95)
    d = classify(ART, design(), settings(), cheap, exp)
    assert (d.label, d.decided_by, d.steps) == ("poc", "expensive", "cheap>expensive")
    d = classify(ART, design(), settings(), Fake("partnership", 0.6), Fake("poc", 0.5))
    assert d.decided_by == "review"
    d = classify(ART, design({"review_queue": False}), settings(), Fake("partnership", 0.6), Fake("poc", 0.5))
    assert d.decided_by == "expensive"


def test_costs_follow_the_configured_prices():
    c = settings()["classification"]
    d = classify(ART, design(), settings(), Fake("poc", 0.6, 1000), Fake("poc", 0.9, 1000))
    assert abs(d.cost_eur - (c["cheap_eur_per_1k_tokens"] + c["expensive_eur_per_1k_tokens"])) < 1e-12


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.messages = self

    def create(self, **kw):
        assert "data, not instructions" in kw["messages"][0]["content"]
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)],
                               usage=SimpleNamespace(input_tokens=200, output_tokens=30))


def test_claude_answers_are_checked_by_code():
    good = ClaudeModel("cheap", FakeClient('{"corporate":"Elbtal","startup":"Nova","label":"poc","confidence":0.9}'))
    assert good.label(ART) == ("poc", 0.9, 230)
    for bad in ("I think it is a pilot", '{"label":"merger","confidence":0.99}', '{"label":"poc","confidence":7}'):
        assert ClaudeModel("cheap", FakeClient(bad)).label(ART)[1] == 0.0


def test_a_domain_in_the_article_decides_the_link_and_a_shared_name_is_left_open():
    gaz = Gazetteer({"C1": ["Elbtal Chemie AG"]}, {"S1": ["Arvel AI"], "S2": ["Arvel AI GmbH"], "S3": ["Novazen Pay"]},
                    {"arvel.ai": "S2"})
    text = "Elbtal Chemie acquires Arvel AI."
    assert gaz.link({"url": "a", "text": text}).status == "ambiguous"
    lk = gaz.link({"url": "b", "text": text, "startup_domain": "https://www.arvel.ai/"})
    assert (lk.corporate, lk.startup) == ("C1", "S2")
    lk = gaz.link({"url": "c", "text": "Elbtal Chemie und Novaezn Pay starten einen Proof of Concept."})
    assert lk.startup == "S3"                                     # a typo still finds its company
