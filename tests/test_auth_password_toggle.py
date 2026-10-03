"""Regression guards for the auth password show/hide control.

The toggle sits on top of a password input that the shared floating-label CSS
lifts with ``z-index: 1``. If the toggle is not given a higher stacking order the
input swallows the click and "show password" silently does nothing.
"""

import re
from pathlib import Path


CSS_PATH = Path("app/static/css/auth.css")
JS_PATH = Path("app/static/js/auth.js")


def _rule_body(stylesheet, selector):
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", stylesheet)
    assert match, f"Missing CSS rule for {selector}"
    return match.group(1)


def test_auth_css_keeps_password_toggle_above_the_input():
    body = _rule_body(CSS_PATH.read_text(encoding="utf-8"), ".password-toggle")
    match = re.search(r"z-index:\s*(\d+)", body)
    assert match, ".password-toggle must declare a z-index"
    assert int(match.group(1)) >= 2, "The toggle must stack above the z-index:1 password input"
    assert "position: absolute" in body


def test_auth_js_enables_and_toggles_the_password_control():
    script = JS_PATH.read_text(encoding="utf-8")
    assert "button.disabled = false" in script, "Reset-password toggles start disabled in markup"
    assert 'input.type = reveal ? "text" : "password"' in script


def test_login_page_exposes_a_wired_password_toggle(client):
    page = client.get("/auth/login").get_data(as_text=True)
    assert "data-password-toggle" in page
    assert 'aria-controls="login-password"' in page
    assert 'id="login-password"' in page
    assert "css/auth.css" in page
    assert "js/auth.js" in page


def test_register_page_exposes_wired_password_toggles(client):
    page = client.get("/auth/register").get_data(as_text=True)
    assert 'aria-controls="signup-password"' in page
    assert 'id="signup-password"' in page
    assert 'aria-controls="signup-confirm"' in page
    assert 'id="signup-confirm"' in page