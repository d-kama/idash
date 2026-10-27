"""Verify Chrome's certificate distrust using the production browser factory.

Run via ``task verify:chrome-tls``. DNS errors, timeouts and other connection
failures are inconclusive, not evidence that a certificate was rejected.
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlsplit

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from infrastructure.scraper import ScraperConfig, _default_chrome_factory

TARGETS = (
    ("https://dv-g3b-emudhra.we-have-a-problem.com", True),
    ("https://dv-g3b-aaa-emudhra.we-have-a-problem.com", True),
    ("https://letsencrypt.org", False),
)
_CERT_ERROR = re.compile(r"\bnet::ERR_CERT_[A-Z0-9_]+\b")


def verify_host(driver: WebDriver, url: str, *, expect_blocked: bool) -> bool:
    """Return whether navigation matches the expected TLS outcome."""
    try:
        driver.get(url)
        document_uri = driver.execute_script("return document.documentURI")
        if not isinstance(document_uri, str):
            print(f"FAIL {url}: could not read document.documentURI")
            return False
        if document_uri.startswith("chrome-error://"):
            # headless-shell can return an empty error document without raising.
            # Reprobe via CDP to distinguish TLS rejection from generic failures.
            navigation = driver.execute_cdp_cmd("Page.navigate", {"url": url})
            error_text = navigation.get("errorText")
            match = _CERT_ERROR.fullmatch(error_text) if isinstance(error_text, str) else None
            if match is None:
                print(f"FAIL {url}: Chrome error page without a certificate error: {error_text}")
                return False
            blocked = True
            detail = match.group()
        else:
            target = urlsplit(url)
            loaded = urlsplit(document_uri)
            if loaded.scheme != "https" or loaded.hostname not in (
                target.hostname,
                f"www.{target.hostname}",
            ):
                print(f"FAIL {url}: unexpected document URI {document_uri}")
                return False
            blocked = False
            detail = f"opened {document_uri}"
    except WebDriverException as error:
        match = _CERT_ERROR.search(error.msg or "")
        if match is None:
            print(f"FAIL {url}: navigation failed without a certificate error: {error.msg}")
            return False
        blocked = True
        detail = match.group()

    passed = blocked == expect_blocked
    expected = "certificate rejection" if expect_blocked else "HTTPS page"
    print(f"{'PASS' if passed else 'FAIL'} {url}: expected {expected}; observed {detail}")
    return passed


def main() -> int:
    config = ScraperConfig(
        user_agent="idash-chrome-tls-check",
        chrome_binary_location=os.environ.get("CHROME_BINARY_LOCATION", "/opt/chrome/chrome"),
        chrome_driver_path=os.environ.get("CHROME_DRIVER_PATH", "/opt/chromedriver/chromedriver"),
    )
    try:
        driver = _default_chrome_factory(config)
    except WebDriverException as error:
        print(f"FAIL: Chrome could not start: {error.msg}", file=sys.stderr)
        return 1

    try:
        print(f"Chrome version: {driver.capabilities['browserVersion']}")
        driver.set_page_load_timeout(30)
        results = [
            verify_host(driver, url, expect_blocked=expect_blocked)
            for url, expect_blocked in TARGETS
        ]
        return 0 if all(results) else 1
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
