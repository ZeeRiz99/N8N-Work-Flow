from app.ai.draft_template import _topic, template_draft


def test_topic_keeps_acronyms():
    assert _topic("AI Chatbot") == "AI chatbot"
    assert _topic("Website Development") == "website development"
    assert _topic("SEO") == "SEO"


def test_recovery_draft_keeps_acronym_in_subject_and_body():
    out = template_draft({"kind": "recovery", "services": [{"name": "AI Chatbot"}]})
    assert out.subject == "Still planning your AI chatbot?"
    assert "talked about AI chatbot." in out.body
