"""Utility functions for HTTP requests and geospatial data parsing.

This module provides helpers for fetching CSV data and converting ESRI REST API
responses to GeoDataFrames for use with TIGER/Line geographic data.
"""
from __future__ import annotations

import io
import logging

import geopandas as gpd
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import shape
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Retry configuration for external API requests
_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)


def _get_session() -> requests.Session:
    """Create a requests.Session with automatic retry and exponential backoff.

    Returns
    -------
    requests.Session
        Session configured with retry strategy for HTTPS requests.
    """
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def http_csv_to_df(url: str, timeout: int = 180) -> pd.DataFrame:
    """Fetch a CSV file from a URL and return as a DataFrame.

    Parameters
    ----------
    url : str
        Full URL to the CSV file.
    timeout : int
        Request timeout in seconds (default 180 for large files).

    Returns
    -------
    pd.DataFrame
        DataFrame containing the parsed CSV data.

    Raises
    ------
    requests.HTTPError
        If the HTTP request fails (4xx/5xx status).
    requests.Timeout
        If request exceeds timeout duration.
    requests.ConnectionError
        If network connection fails.

    Notes
    -----
    Uses BytesIO buffer to avoid writing temporary files to disk.
    Timeout of 180s accommodates large Census/Zillow data files.
    """
    try:
        response = _get_session().get(url, timeout=timeout)
        response.raise_for_status()
        return pd.read_csv(io.BytesIO(response.content))
    except requests.Timeout as e:
        raise requests.Timeout(
            f"Request timed out after {timeout}s for URL: {url}. "
            "Try increasing timeout or check network connection."
        ) from e
    except requests.ConnectionError as e:
        raise requests.ConnectionError(
            f"Failed to connect to {url}. Check network connection and URL."
        ) from e


def http_json_to_dict(url: str, params: dict | None = None) -> dict | list:
    """Fetch JSON data from a URL and return as Python dict or list.

    Parameters
    ----------
    url : str
        Full URL to the JSON API endpoint.
    params : dict | None
        Optional query parameters dictionary.

    Returns
    -------
    dict | list
        Parsed JSON response (dict or list depending on API).

    Raises
    ------
    requests.HTTPError
        If the HTTP request fails.
    ValueError
        If response is not valid JSON.
    """
    response = _get_session().get(url, params=params, timeout=180)
    response.raise_for_status()
    return response.json()


def esri_geojson_to_gdf(url: str, params: dict) -> gpd.GeoDataFrame:
    """Fetch geospatial data from ESRI REST API and convert to GeoDataFrame.

    This function handles both ESRI JSON format (with 'attributes' field) and
    standard GeoJSON format (with 'properties' field), making it compatible
    with various Census TIGER/Line services.

    Parameters
    ----------
    url : str
        ESRI REST API endpoint URL (typically ends with /query).
    params : dict
        Query parameters dict (where clause, outFields, f=geojson, etc.).

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame in EPSG:4326 (WGS84) coordinate system. Returns empty
        GeoDataFrame with geometry column if no features found.

    Raises
    ------
    requests.HTTPError
        If the API request fails.
    ValueError
        If response JSON is malformed.
    """
    response = _get_session().get(url, params=params, timeout=180)
    response.raise_for_status()

    data = response.json()
    features = data.get("features", [])

    # Return empty GeoDataFrame if no features returned
    if not features:
        return gpd.GeoDataFrame(
            columns=["geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )

    # Parse features into geometries and attributes
    geometries = []
    attributes = []
    for feature in features:
        # Handle both ESRI JSON (attributes) and GeoJSON (properties) formats
        attr = feature.get("attributes") or feature.get("properties", {})
        attributes.append(attr)

        # Convert geometry to Shapely object
        geom = feature.get("geometry")
        geometries.append(shape(geom) if geom else None)

    # Create GeoDataFrame with WGS84 coordinate system
    gdf = gpd.GeoDataFrame(attributes, geometry=geometries, crs="EPSG:4326")
    return gdf
