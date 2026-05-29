"""Tests for clickwheel/applemusic.py and the Apple Music doctor in
actions.py. We do not touch real Apple endpoints; the REST helpers are
monkeypatched at the module's `_request_json` boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel import applemusic as _am
from clickwheel.actions import (
    AppleMusicAuthError,
    AppleMusicKeyFileError,
    AppleMusicNotConfiguredError,
    _require_apple_music_config,
    _resolve_developer_token,
    _save_apple_music_user_token,
    apple_music_doctor,
)
from clickwheel.config import Config


@pytest.fixture
def _gen_p8(tmp_path: Path) -> Path:
    """Generate a fresh ES256 private key in PEM format and write it as
    a .p8 file. Cheap; ~ms on modern hardware."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    p = tmp_path / "AuthKey_TEST123ABC.p8"
    p.write_bytes(pem)
    return p


@pytest.fixture
def am_cfg(tmp_path: Path, _gen_p8: Path) -> Config:
    """Config with Apple Music enabled and pointed at the generated .p8."""
    return Config(
        music_dir=tmp_path / "music",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_storefront="us",
        apple_music_key_id="TEST123ABC",
        apple_music_team_id="TEAM987XYZ",
        apple_music_key_file=str(_gen_p8),
    )


# ---------------------------------------------------------------------------
# read_private_key
# ---------------------------------------------------------------------------


def test_read_private_key_happy(_gen_p8: Path):
    pem = _am.read_private_key(_gen_p8)
    assert "BEGIN PRIVATE KEY" in pem


def test_read_private_key_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        _am.read_private_key(tmp_path / "nope.p8")


def test_read_private_key_invalid(tmp_path: Path):
    bad = tmp_path / "bad.p8"
    bad.write_text("definitely not a PEM key")
    with pytest.raises(_am.AppleMusicConfigInvalidError):
        _am.read_private_key(bad)


def test_read_private_key_expands_tilde(tmp_path: Path, monkeypatch, _gen_p8: Path):
    """If a config path uses ~, expanduser() resolves it before opening
    the file. We fake $HOME to point at tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Move the key into the faked home so the ~-expanded path lands on it.
    home_p8 = tmp_path / "AuthKey_TEST123ABC.p8"
    home_p8.write_bytes(_gen_p8.read_bytes())
    pem = _am.read_private_key("~/AuthKey_TEST123ABC.p8")
    assert "BEGIN PRIVATE KEY" in pem


# ---------------------------------------------------------------------------
# generate_developer_token + verify
# ---------------------------------------------------------------------------


def test_generate_developer_token_signs_and_decodes(_gen_p8: Path):
    """Signed JWT round-trips through PyJWT with the public key derived
    from the same private key."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    pem = _gen_p8.read_text()
    token = _am.generate_developer_token(pem, "KEYID12345", "TEAM987XYZ", 600)

    priv = load_pem_private_key(pem.encode(), password=None)
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    decoded = jwt.decode(token, pub_pem, algorithms=["ES256"])
    assert decoded["iss"] == "TEAM987XYZ"

    header = jwt.get_unverified_header(token)
    assert header["kid"] == "KEYID12345"
    assert header["alg"] == "ES256"


# ---------------------------------------------------------------------------
# _request_json error wrapping
# ---------------------------------------------------------------------------


def test_decode_body_gzip(monkeypatch):
    """_decode_body unwraps gzip — Apple Music's library/playlists POST
    sometimes returns gzip even when the client didn't request it."""
    import gzip

    raw = gzip.compress(b'{"ok":true}')
    assert _am._decode_body(raw, "gzip") == '{"ok":true}'


def test_decode_body_identity_passthrough():
    """No encoding → decode utf-8 directly."""
    assert _am._decode_body(b'{"a":1}', None) == '{"a":1}'


def test_decode_body_empty():
    assert _am._decode_body(b"", None) == ""
    assert _am._decode_body(b"", "gzip") == ""


def test_request_json_wraps_http_errors(monkeypatch):
    """A urllib HTTPError gets re-raised as AppleMusicHTTPError carrying
    the status and body."""
    import urllib.error
    import urllib.request

    class _FakeResponse:
        def __init__(self) -> None:
            self._body = b'{"errors":[{"status":"401","title":"Unauthorized"}]}'

        def read(self) -> bytes:
            return self._body

    def _raise(*args, **kwargs):
        err = urllib.error.HTTPError(
            "https://api.music.apple.com/test", 401, "Unauthorized", {}, None
        )
        err.read = lambda: b'{"errors":[{"status":"401"}]}'  # type: ignore[method-assign]
        raise err

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(_am.AppleMusicHTTPError) as exc_info:
        _am._request_json(
            "https://api.music.apple.com/test", headers={"Authorization": "Bearer x"}
        )
    assert exc_info.value.status == 401
    assert "401" in exc_info.value.body


# ---------------------------------------------------------------------------
# detect_icloud_music_library: True / False / propagated
# ---------------------------------------------------------------------------


def test_detect_icml_on(monkeypatch):
    monkeypatch.setattr(_am, "_request_json", lambda url, headers, **kw: {"data": []})
    assert _am.detect_icloud_music_library("dev", "user", "us") is True


def test_detect_icml_off(monkeypatch):
    def _raise(*args, **kw):
        raise _am.AppleMusicHTTPError(403, "USER_LIBRARY_DISABLED", "url")

    monkeypatch.setattr(_am, "_request_json", _raise)
    assert _am.detect_icloud_music_library("dev", "user", "us") is False


def test_detect_icml_propagates_other_errors(monkeypatch):
    def _raise(*args, **kw):
        raise _am.AppleMusicHTTPError(401, "bad token", "url")

    monkeypatch.setattr(_am, "_request_json", _raise)
    with pytest.raises(_am.AppleMusicHTTPError):
        _am.detect_icloud_music_library("dev", "user", "us")


# ---------------------------------------------------------------------------
# _require_apple_music_config
# ---------------------------------------------------------------------------


def test_require_apple_music_config_when_disabled(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m", project_dir=tmp_path, apple_music_enabled=False
    )
    with pytest.raises(AppleMusicNotConfiguredError):
        _require_apple_music_config(cfg)


def test_require_apple_music_config_missing_team_id(tmp_path: Path, _gen_p8: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_key_id="K",
        apple_music_key_file=str(_gen_p8),
    )
    with pytest.raises(AppleMusicNotConfiguredError) as exc:
        _require_apple_music_config(cfg)
    assert "apple_music_team_id" in str(exc.value)


def test_require_apple_music_config_accepts_pre_signed_token(tmp_path: Path):
    """If APPLE_MUSIC_DEVELOPER_TOKEN is provided, key_id and key_file
    aren't required — only team_id."""
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_developer_token="pre.signed.token",
    )
    _require_apple_music_config(cfg)  # should not raise


# ---------------------------------------------------------------------------
# _resolve_developer_token
# ---------------------------------------------------------------------------


def test_resolve_developer_token_prefers_env_override(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_developer_token="pre.signed.token",
    )
    assert _resolve_developer_token(cfg) == "pre.signed.token"


def test_resolve_developer_token_signs_from_p8(am_cfg: Config):
    token = _resolve_developer_token(am_cfg)
    assert token.count(".") == 2  # JWT has three segments
    import jwt

    header = jwt.get_unverified_header(token)
    assert header["kid"] == "TEST123ABC"


def test_resolve_developer_token_missing_p8(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_key_id="K",
        apple_music_key_file=str(tmp_path / "nope.p8"),
    )
    with pytest.raises(AppleMusicKeyFileError):
        _resolve_developer_token(cfg)


# ---------------------------------------------------------------------------
# _save_apple_music_user_token
# ---------------------------------------------------------------------------


def test_save_apple_music_user_token_appends(tmp_path: Path, monkeypatch):
    from clickwheel import config as _cfg_mod

    monkeypatch.setattr(_cfg_mod, "CONFIG_DIR", tmp_path)
    env = tmp_path / ".env"
    env.write_text("LASTFM_API_KEY=abc\n")
    _save_apple_music_user_token("user_tok_xyz")
    text = env.read_text()
    assert "LASTFM_API_KEY=abc" in text
    assert "APPLE_MUSIC_USER_TOKEN=user_tok_xyz" in text


def test_save_apple_music_user_token_replaces_existing(tmp_path: Path, monkeypatch):
    from clickwheel import config as _cfg_mod

    monkeypatch.setattr(_cfg_mod, "CONFIG_DIR", tmp_path)
    env = tmp_path / ".env"
    env.write_text("APPLE_MUSIC_USER_TOKEN=old\nOTHER=keep\n")
    _save_apple_music_user_token("new_token")
    text = env.read_text()
    assert "APPLE_MUSIC_USER_TOKEN=new_token" in text
    assert "OTHER=keep" in text
    # No duplicate
    assert text.count("APPLE_MUSIC_USER_TOKEN=") == 1


def test_save_apple_music_user_token_creates_env(tmp_path: Path, monkeypatch):
    from clickwheel import config as _cfg_mod

    monkeypatch.setattr(_cfg_mod, "CONFIG_DIR", tmp_path)
    _save_apple_music_user_token("only_one_token")
    text = (tmp_path / ".env").read_text()
    assert text == "APPLE_MUSIC_USER_TOKEN=only_one_token\n"


# ---------------------------------------------------------------------------
# apple_music_doctor stages
# ---------------------------------------------------------------------------


def test_doctor_stops_at_disabled_config(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m", project_dir=tmp_path, apple_music_enabled=False
    )
    result = apple_music_doctor(cfg)
    assert result.ok is False
    assert [s.name for s in result.stages] == ["config"]
    assert "disabled" in result.stages[0].detail.lower()


def test_doctor_stops_at_missing_p8(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_key_id="K",
        apple_music_key_file=str(tmp_path / "nope.p8"),
    )
    result = apple_music_doctor(cfg)
    stage_names = [s.name for s in result.stages]
    assert "p8 readable" in stage_names
    last = result.stages[-1]
    assert last.name == "p8 readable" and last.ok is False


def test_doctor_passes_catalog_stage(am_cfg: Config, monkeypatch):
    """With a happy mocked catalog response, the doctor reaches the
    user-token stage and stops there (no token configured yet)."""

    def _fake_request(url, headers, **kw):
        # only the catalog search endpoint should be called in this test
        assert "catalog/us/search" in url
        return {
            "results": {
                "songs": {
                    "data": [
                        {"attributes": {"artistName": "Nirvana", "name": "Lithium"}}
                    ]
                }
            }
        }

    monkeypatch.setattr(_am, "_request_json", _fake_request)
    result = apple_music_doctor(am_cfg)
    by_name = {s.name: s for s in result.stages}
    assert by_name["catalog reachable"].ok is True
    assert "Nirvana" in by_name["catalog reachable"].detail
    # user token stage is reached and fails (token not in config)
    assert by_name["user token"].ok is False
    assert "apple auth" in by_name["user token"].detail


def test_doctor_surfaces_revoked_key(am_cfg: Config, monkeypatch):
    """A 401 from Apple at the catalog stage is reported with the
    'revoked key' hint so the user knows to regen."""

    def _fake_request(url, headers, **kw):
        raise _am.AppleMusicHTTPError(401, "", url)

    monkeypatch.setattr(_am, "_request_json", _fake_request)
    result = apple_music_doctor(am_cfg)
    by_name = {s.name: s for s in result.stages}
    assert by_name["catalog reachable"].ok is False
    assert "revoked" in by_name["catalog reachable"].detail.lower()


def test_doctor_full_pass_with_user_token(am_cfg: Config, monkeypatch):
    """When a user token is present and Apple accepts everything, all
    stages pass (including iCML probe + storefront agreement)."""
    am_cfg.apple_music_user_token = "user_tok_abc"  # type: ignore[misc]

    calls: list[str] = []

    def _fake_request(url, headers, **kw):
        calls.append(url)
        if "catalog" in url:
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "attributes": {
                                    "artistName": "Pearl Jam",
                                    "name": "Alive",
                                }
                            }
                        ]
                    }
                }
            }
        if "/me/storefront" in url:
            return {"data": [{"id": "us"}]}
        if "/me/library/songs" in url:
            return {"data": []}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(_am, "_request_json", _fake_request)
    result = apple_music_doctor(am_cfg)
    assert result.ok is True, [(s.name, s.detail) for s in result.stages if not s.ok]
    stage_names = [s.name for s in result.stages]
    assert stage_names == [
        "config",
        "applemusic extra",
        "p8 readable",
        "developer token",
        "catalog reachable",
        "user token",
        "user token verified",
        "iCloud Music Library",
        "storefront match",
    ]


def test_doctor_flags_storefront_mismatch(am_cfg: Config, monkeypatch):
    """If user's actual storefront differs from configured, the
    storefront-match stage fails with both values surfaced."""
    am_cfg.apple_music_user_token = "user_tok"  # type: ignore[misc]
    am_cfg.apple_music_storefront = "us"  # type: ignore[misc]

    def _fake_request(url, headers, **kw):
        if "catalog" in url:
            return {"results": {"songs": {"data": []}}}
        if "/me/storefront" in url:
            return {"data": [{"id": "gb"}]}
        if "/me/library/songs" in url:
            return {"data": []}
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake_request)
    result = apple_music_doctor(am_cfg)
    by_name = {s.name: s for s in result.stages}
    assert by_name["storefront match"].ok is False
    detail = by_name["storefront match"].detail
    assert "'us'" in detail and "'gb'" in detail


# ---------------------------------------------------------------------------
# apple_music_auth — only the failure path, since the happy path opens
# a real browser. Happy path covered in the live `clickwheel apple auth`
# command + manual QA.
# ---------------------------------------------------------------------------


def test_apple_music_auth_propagates_dance_failure(am_cfg: Config, monkeypatch):
    """If the auth server times out / user cancels, the action raises
    AppleMusicAuthError with the underlying reason."""
    from clickwheel.actions import apple_music_auth

    def _fake_dance(
        dev_token, *, build, port=None, timeout_seconds=300.0, open_browser=True
    ):
        return _am.AuthServerResult(
            user_token=None, error="Timed out waiting for browser."
        )

    monkeypatch.setattr(_am, "run_user_token_auth", _fake_dance)
    with pytest.raises(AppleMusicAuthError) as exc:
        apple_music_auth(am_cfg, build="test")
    assert "Timed out" in str(exc.value)
