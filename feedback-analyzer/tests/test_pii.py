from src.ml.pii_sanitizer import PIISanitizer, luhn_ok


def make():
    return PIISanitizer(enable_ner=False)


def test_email():
    s = make()
    assert s.sanitize("mail me at jane.doe+app@sub.example.co.uk now") == "mail me at [EMAIL_REDACTED] now"
    assert s.counts["email"] == 1


def test_phone_formats():
    s = make()
    for raw in ["+1 415-555-0132", "(415) 555-0132", "415.555.0132", "4155550132", "+91 98765 43210", "98765 43210"]:
        out = s.sanitize(f"call {raw} today")
        assert out == "call [PHONE_REDACTED] today", (raw, out)
    assert s.counts["phone"] == 6


def test_credit_card_luhn():
    s = make()
    assert s.sanitize("card 4111 1111 1111 1111 ok") == "card [PII_REDACTED] ok"
    assert s.sanitize("order 1234 5678 9012 3456 ok") == "order 1234 5678 9012 3456 ok"  # fails Luhn
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")


def test_ssn_and_ip():
    s = make()
    assert s.sanitize("ssn 123-45-6789.") == "ssn [PII_REDACTED]."
    assert s.sanitize("from 192.168.1.15 today") == "from [PII_REDACTED] today"
    assert s.sanitize("ipv6 2001:0db8:85a3:0000:0000:8a2e:0370:7334 end") == "ipv6 [PII_REDACTED] end"
    assert s.counts["ssn"] == 1 and s.counts["ip_address"] == 2


def test_no_false_positives_on_ordinary_numbers():
    s = make()
    for text in [
        "Stuck at 1080p after update 2.1.0",
        "I rate it 10/10, been a user since 2019",
        "Paid $12.99 on 2026-10-01",
        "Watched 3 episodes in 45 minutes",
    ]:
        assert s.sanitize(text) == text, text
    assert s.total_redacted == 0


def test_running_tally_and_reset():
    s = make()
    s.sanitize_batch(["a@b.com", "call 4155550132", "clean text"])
    assert s.total_redacted == 2
    assert s.report() == {"email": 1, "phone": 1, "total": 2}
    s.reset()
    assert s.total_redacted == 0


def test_none_and_empty():
    s = make()
    assert s.sanitize(None) == "" and s.sanitize("") == ""
