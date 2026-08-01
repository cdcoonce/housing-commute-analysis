"""Tests for src.pipelines.utils module."""
from __future__ import annotations

import gzip
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
import requests
from urllib3.util.retry import Retry

import src.pipelines.utils as utils
from src.pipelines.utils import _get_session, esri_geojson_to_gdf, http_json_to_dict


def test_get_session_has_retry():
    """Session HTTPS adapter must use a Retry with total=3."""
    session = _get_session()
    adapter = session.get_adapter("https://")
    retry: Retry = adapter.max_retries

    assert isinstance(retry, Retry)
    assert retry.total == 3


def test_get_session_mounts_https():
    """Session must have an adapter mounted for the https:// prefix."""
    session = _get_session()
    adapter = session.get_adapter("https://example.com")

    assert adapter is not None


@patch("src.pipelines.utils._get_session")
def test_esri_geojson_to_gdf_valid(mock_get_session: MagicMock):
    """Valid ESRI JSON with features returns a GeoDataFrame with correct rows."""
    esri_response = {
        "features": [
            {
                "attributes": {"NAME": "test"},
                "geometry": {"type": "Point", "coordinates": [-111.9, 33.4]},
            },
            {
                "attributes": {"NAME": "test2"},
                "geometry": {"type": "Point", "coordinates": [-112.0, 33.5]},
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = esri_response
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_get_session.return_value = mock_session

    gdf = esri_geojson_to_gdf("https://example.com/query", params={"where": "1=1"})

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert list(gdf["NAME"]) == ["test", "test2"]


@patch("src.pipelines.utils._get_session")
def test_esri_geojson_to_gdf_empty_features(mock_get_session: MagicMock):
    """Empty features list returns an empty GeoDataFrame."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"features": []}
    mock_response.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    mock_get_session.return_value = mock_session

    gdf = esri_geojson_to_gdf("https://example.com/query", params={"where": "1=1"})

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 0


class _StubResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _StubSession:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def get(self, url: str, timeout: int = 180, params=None):
        return _StubResponse(self._content)


def test_http_csv_to_df_plain_csv_unchanged(monkeypatch) -> None:
    csv_bytes = b"a,b\n1,2\n"
    monkeypatch.setattr(utils, "_get_session", lambda: _StubSession(csv_bytes))
    df = utils.http_csv_to_df("https://example.com/x.csv")
    assert df.shape == (1, 2) and df["a"][0] == 1


def test_http_csv_to_df_gzip_passthrough(monkeypatch) -> None:
    """LODES files are gzip-as-payload: requests does NOT auto-decode them and
    pandas cannot infer compression from BytesIO — the kwarg must reach read_csv."""
    raw = b"w_geocode,C000\n040130001001000,42\n"
    gz = gzip.compress(raw)
    monkeypatch.setattr(utils, "_get_session", lambda: _StubSession(gz))
    df = utils.http_csv_to_df(
        "https://example.com/x.csv.gz",
        compression="gzip",
        dtype={"w_geocode": str},
    )
    assert df["w_geocode"][0] == "040130001001000"  # str dtype preserved leading zero
    assert df["C000"][0] == 42


def _stub_json_response(
    content: bytes, url: str, status_code: int = 200, content_type: str = "application/json"
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    response.headers["Content-Type"] = content_type
    response._content = content
    return response


class _StubJsonSession:
    def __init__(self, response: requests.Response) -> None:
        self._response = response

    def get(self, url: str, params=None, timeout: int = 180):
        return self._response


def test_http_json_to_dict_non_json_response_names_url_status_content_type_and_body(
    monkeypatch,
) -> None:
    url = "https://example.com/api"
    response = _stub_json_response(
        b"<html><title>Service Unavailable</title></html>",
        url=url,
        status_code=200,
        content_type="text/html",
    )
    monkeypatch.setattr(utils, "_get_session", lambda: _StubJsonSession(response))

    with pytest.raises(requests.exceptions.JSONDecodeError) as exc_info:
        http_json_to_dict(url)

    message = str(exc_info.value)
    assert url in message
    assert "200" in message
    assert "text/html" in message
    assert "Service Unavailable" in message


def test_http_json_to_dict_non_json_response_truncates_body(monkeypatch) -> None:
    url = "https://example.com/api"
    response = _stub_json_response(
        b"x" * 5000, url=url, status_code=200, content_type="text/html"
    )
    monkeypatch.setattr(utils, "_get_session", lambda: _StubJsonSession(response))

    with pytest.raises(requests.exceptions.JSONDecodeError) as exc_info:
        http_json_to_dict(url)

    message = str(exc_info.value)
    assert len(message) < 1000
    assert "x" * 5000 not in message


def test_http_json_to_dict_non_json_response_preserves_valueerror_and_requestexception(
    monkeypatch,
) -> None:
    url = "https://example.com/api"
    response = _stub_json_response(
        b"<html></html>", url=url, status_code=200, content_type="text/html"
    )
    monkeypatch.setattr(utils, "_get_session", lambda: _StubJsonSession(response))

    with pytest.raises(requests.exceptions.JSONDecodeError) as exc_info:
        http_json_to_dict(url)

    assert isinstance(exc_info.value, ValueError)
    assert isinstance(exc_info.value, requests.RequestException)


def test_http_json_to_dict_non_json_response_sets_cause(monkeypatch) -> None:
    url = "https://example.com/api"
    response = _stub_json_response(
        b"<html></html>", url=url, status_code=200, content_type="text/html"
    )
    monkeypatch.setattr(utils, "_get_session", lambda: _StubJsonSession(response))

    with pytest.raises(requests.exceptions.JSONDecodeError) as exc_info:
        http_json_to_dict(url)

    assert isinstance(exc_info.value.__cause__, requests.exceptions.JSONDecodeError)


def test_http_json_to_dict_valid_json_returned_unchanged(monkeypatch) -> None:
    url = "https://example.com/api"
    response = _stub_json_response(b'{"a": 1, "b": [2, 3]}', url=url)
    monkeypatch.setattr(utils, "_get_session", lambda: _StubJsonSession(response))

    result = http_json_to_dict(url)

    assert result == {"a": 1, "b": [2, 3]}
