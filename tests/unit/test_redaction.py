"""Redaction unit tests: patterns must never leak into derived copies."""

from openclass_server.redaction import redact_mapping, redact_text


def test_redacts_email():
    assert "john.doe@example.com" not in redact_text("Contact john.doe@example.com now")
    assert "[redacted]" in redact_text("Contact john.doe@example.com now")


def test_redacts_credit_card():
    text = "My card 4111 1111 1111 1111 was charged"
    redacted = redact_text(text)
    assert "4111" not in redacted
    assert "[redacted]" in redacted


def test_redacts_ssn():
    assert "123-45-6789" not in redact_text("SSN 123-45-6789 on file")


def test_redacts_bearer_and_api_tokens():
    for secret in ("sk-live-9f3c2b1a77d2", "oc_dev_0123456789abcdef0123456789abcdef01234567"):
        assert secret not in redact_text(f"key={secret} leaked")


def test_blocklist_terms_are_redacted_first():
    assert "AcmeRocket" not in redact_text("AcmeRocket launch", blocklist=("AcmeRocket",))


def test_plain_text_is_untouched():
    assert redact_text("I was charged twice for my order") == "I was charged twice for my order"


def test_mapping_redacts_nested_values():
    from openclass_server.redaction import configured_blocklist

    payload = {
        "content": "email me at a@b.co",
        "metadata": {
            "note": "token sk-abcdefghijklmnopqr",
            "tags": ["x", "phone 555-1234"],
            "nested_items": [{"secret_email": "nested@example.org", "inner_list": ["123-45-6789"]}],
        },
        "count": 3,
    }
    redacted = redact_mapping(payload, blocklist=configured_blocklist("AcmeSecret , BetaCorp "))
    assert "a@b.co" not in redacted["content"]
    assert "sk-abcdefghijklmnopqr" not in redacted["metadata"]["note"]
    assert "555-1234" not in redacted["metadata"]["tags"][1]
    assert "nested@example.org" not in redacted["metadata"]["nested_items"][0]["secret_email"]
    assert "123-45-6789" not in redacted["metadata"]["nested_items"][0]["inner_list"][0]
    assert redacted["count"] == 3

    unredacted = redact_mapping(payload, enabled=False)
    assert unredacted["content"] == "email me at a@b.co"
    assert redact_text("Contact a@b.co", enabled=False) == "Contact a@b.co"
