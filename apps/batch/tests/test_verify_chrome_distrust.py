"""Offline tests for the manually invoked Chrome TLS verification script."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from infrastructure.scraper import ScraperConfig

_spec = spec_from_file_location(
    "verify_chrome_distrust",
    Path(__file__).parents[1] / "scripts" / "verify_chrome_distrust.py",
)
assert _spec is not None and _spec.loader is not None
verify = module_from_spec(_spec)
_spec.loader.exec_module(verify)


@pytest.fixture
def driver() -> Mock:
    driver = Mock(spec=WebDriver)
    driver.execute_script.return_value = "https://letsencrypt.org/"
    driver.capabilities = {"browserVersion": "test-version"}
    return driver


@pytest.mark.parametrize("url", [target[0] for target in verify.TARGETS[:2]])
@pytest.mark.parametrize("code", ["ERR_CERT_AUTHORITY_INVALID", "ERR_CERT_REVOKED"])
def test_certificate_exception_is_rejection(driver, url, code, capsys) -> None:
    driver.get.side_effect = WebDriverException(f"unknown error: net::{code}")

    assert verify.verify_host(driver, url, expect_blocked=True)
    assert f"PASS {url}" in capsys.readouterr().out


def test_positive_control_must_not_reject_certificate(driver) -> None:
    driver.get.side_effect = WebDriverException("net::ERR_CERT_AUTHORITY_INVALID")

    assert not verify.verify_host(driver, verify.TARGETS[2][0], expect_blocked=False)


@pytest.mark.parametrize("expect_blocked", [True, False])
@pytest.mark.parametrize(
    "error",
    [
        WebDriverException("net::ERR_NAME_NOT_RESOLVED"),
        WebDriverException("net::ERR_CONNECTION_REFUSED"),
        WebDriverException("net::ERR_CONNECTION_RESET"),
        WebDriverException("net::ERR_SSL_PROTOCOL_ERROR"),
        WebDriverException("browser disconnected"),
        TimeoutException("Timed out receiving message from renderer"),
    ],
)
def test_non_certificate_failures_never_pass(driver, error, expect_blocked, capsys) -> None:
    driver.get.side_effect = error

    assert not verify.verify_host(driver, verify.TARGETS[0][0], expect_blocked=expect_blocked)
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.parametrize("expect_blocked", [True, False])
def test_chrome_certificate_error_page(driver, expect_blocked) -> None:
    driver.execute_script.return_value = "chrome-error://chromewebdata/"
    driver.page_source = "<html><head></head><body></body></html>"
    driver.execute_cdp_cmd.return_value = {"errorText": "net::ERR_CERT_AUTHORITY_INVALID"}

    assert (
        verify.verify_host(driver, verify.TARGETS[0][0], expect_blocked=expect_blocked)
        == expect_blocked
    )
    driver.execute_cdp_cmd.assert_called_once_with("Page.navigate", {"url": verify.TARGETS[0][0]})


@pytest.mark.parametrize("expect_blocked", [True, False])
@pytest.mark.parametrize(
    "error_text", ["net::ERR_NAME_NOT_RESOLVED", "net::ERR_CONNECTION_RESET", "unavailable"]
)
def test_generic_chrome_error_page_never_passes(driver, error_text, expect_blocked) -> None:
    driver.execute_script.return_value = "chrome-error://chromewebdata/"
    driver.execute_cdp_cmd.return_value = {"errorText": error_text}
    driver.page_source = "Unrelated script text: ERR_CERT_AUTHORITY_INVALID"

    assert not verify.verify_host(driver, verify.TARGETS[0][0], expect_blocked=expect_blocked)


@pytest.mark.parametrize("navigation", [{}, {"errorText": ""}, {"errorText": None}])
def test_chrome_error_page_without_cdp_error_is_inconclusive(driver, navigation) -> None:
    driver.execute_script.return_value = "chrome-error://chromewebdata/"
    driver.execute_cdp_cmd.return_value = navigation

    assert not verify.verify_host(driver, verify.TARGETS[0][0], expect_blocked=True)


def test_cdp_failure_does_not_count_as_rejection(driver) -> None:
    driver.execute_script.return_value = "chrome-error://chromewebdata/"
    driver.execute_cdp_cmd.side_effect = WebDriverException("disconnected")

    assert not verify.verify_host(driver, verify.TARGETS[0][0], expect_blocked=True)


@pytest.mark.parametrize("url", [target[0] for target in verify.TARGETS[:2]])
def test_opening_distrusted_host_fails_even_with_certificate_text(driver, url) -> None:
    driver.execute_script.return_value = url
    driver.page_source = "net::ERR_CERT_AUTHORITY_INVALID"

    assert not verify.verify_host(driver, url, expect_blocked=True)


@pytest.mark.parametrize(
    "document_uri",
    [
        "https://letsencrypt.org/",
        "https://letsencrypt.org/getting-started/",
        "https://www.letsencrypt.org/",
    ],
)
def test_positive_control_can_open_https_page(driver, document_uri) -> None:
    driver.execute_script.return_value = document_uri
    driver.page_source = "net::ERR_CERT_AUTHORITY_INVALID"

    assert verify.verify_host(driver, verify.TARGETS[2][0], expect_blocked=False)


@pytest.mark.parametrize(
    "document_uri",
    ["http://letsencrypt.org/", "https://unrelated.example/", "about:blank", None],
)
def test_unexpected_document_does_not_pass_control(driver, document_uri) -> None:
    driver.execute_script.return_value = document_uri

    assert not verify.verify_host(driver, verify.TARGETS[2][0], expect_blocked=False)


@pytest.mark.parametrize("protected", [True, False])
def test_main_checks_every_host_and_quits(driver, monkeypatch, capsys, protected) -> None:
    factory = Mock(return_value=driver)
    monkeypatch.setattr(verify, "_default_chrome_factory", factory)
    monkeypatch.delenv("CHROME_BINARY_LOCATION", raising=False)
    monkeypatch.delenv("CHROME_DRIVER_PATH", raising=False)
    if protected:
        driver.get.side_effect = [
            WebDriverException("net::ERR_CERT_AUTHORITY_INVALID"),
            WebDriverException("net::ERR_CERT_REVOKED"),
            None,
        ]
    else:
        driver.execute_script.side_effect = [target[0] for target in verify.TARGETS]

    assert verify.main() == (0 if protected else 1)

    factory.assert_called_once_with(
        ScraperConfig(
            user_agent="idash-chrome-tls-check",
            chrome_binary_location="/opt/chrome/chrome",
            chrome_driver_path="/opt/chromedriver/chromedriver",
        )
    )
    assert [call.args[0] for call in driver.get.call_args_list] == [
        target[0] for target in verify.TARGETS
    ]
    driver.set_page_load_timeout.assert_called_once_with(30)
    driver.quit.assert_called_once()
    assert "Chrome version: test-version" in capsys.readouterr().out


def test_main_uses_explicit_binary_paths(driver, monkeypatch) -> None:
    factory = Mock(return_value=driver)
    monkeypatch.setattr(verify, "_default_chrome_factory", factory)
    monkeypatch.setenv("CHROME_BINARY_LOCATION", "/tmp/chrome")
    monkeypatch.setenv("CHROME_DRIVER_PATH", "/tmp/chromedriver")
    driver.get.side_effect = WebDriverException("net::ERR_NAME_NOT_RESOLVED")

    assert verify.main() == 1
    config = factory.call_args.args[0]
    assert config.chrome_binary_location == "/tmp/chrome"
    assert config.chrome_driver_path == "/tmp/chromedriver"
    assert driver.get.call_count == len(verify.TARGETS)
    driver.quit.assert_called_once()


def test_startup_error_is_reported(monkeypatch, capsys) -> None:
    factory = Mock(side_effect=WebDriverException("Chrome binary not found"))
    monkeypatch.setattr(verify, "_default_chrome_factory", factory)

    assert verify.main() == 1
    assert "Chrome binary not found" in capsys.readouterr().err


def test_driver_is_closed_on_unexpected_error(driver, monkeypatch) -> None:
    monkeypatch.setattr(verify, "_default_chrome_factory", Mock(return_value=driver))
    driver.set_page_load_timeout.side_effect = RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        verify.main()

    driver.quit.assert_called_once()
