from junior.reporting.email_sender import send_email_report


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.message = message


def _settings(**changes):
    values = {
        "enabled": True,
        "sender": "junior@example.com",
        "sender_name": "Junior",
        "recipients": ["candidate@example.com"],
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "junior@example.com",
        "smtp_password_env": "JUNIOR_SMTP_PASSWORD",
        "smtp_tls_mode": "starttls",
    }
    values.update(changes)
    return values


def test_email_refuses_disabled_or_missing_credentials(monkeypatch) -> None:
    assert not send_email_report(_settings(enabled=False), "Report", "Body").sent
    monkeypatch.delenv("JUNIOR_SMTP_PASSWORD", raising=False)
    result = send_email_report(_settings(), "Report", "Body")
    assert not result.sent
    assert "JUNIOR_SMTP_PASSWORD" in result.message


def test_email_sends_with_starttls(monkeypatch) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setenv("JUNIOR_SMTP_PASSWORD", "secret")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    result = send_email_report(_settings(), "Junior report", "Body")
    smtp = FakeSMTP.instances[0]
    assert result.sent
    assert smtp.started_tls
    assert smtp.credentials == ("junior@example.com", "secret")
    assert smtp.message["From"] == "Junior <junior@example.com>"
