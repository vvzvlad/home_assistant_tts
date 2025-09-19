#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylint: disable=multiple-statements, logging-fstring-interpolation, trailing-whitespace, line-too-long
# pylint: disable=broad-exception-caught, missing-function-docstring, missing-class-docstring
# pylint: disable=f-string-without-interpolation, import-error
# pylance: disable=reportMissingImports, reportMissingModuleSource
# mypy: disable-error-code="import-untyped, import-not-found"

import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
import voluptuous as vol

from homeassistant.components.tts import PLATFORM_SCHEMA, Provider # type: ignore
from homeassistant.const import CONF_TIMEOUT # type: ignore
import homeassistant.helpers.config_validation as cv # type: ignore
from homeassistant.helpers.aiohttp_client import async_get_clientsession # type: ignore
from aiohttp import ClientTimeout # type: ignore

CONF_BASE_URL = "base_url"
CONF_FORMAT = "format"

DEFAULT_TIMEOUT = 30
DEFAULT_FORMAT = "mp3"

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_BASE_URL): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.positive_int,
        vol.Optional(CONF_FORMAT, default=DEFAULT_FORMAT): vol.In(["mp3"]),
    }
)


def get_engine(hass: Any, config: Dict[str, Any], discovery_info: Optional[Dict[str, Any]] = None):
    """Return TTS provider instance."""
    _ = discovery_info
    return HaTtsAdapterProvider(hass, config)


class HaTtsAdapterProvider(Provider):
    """Home Assistant TTS provider that proxies text to local TTS server."""

    def __init__(self, hass: Any, config: Dict[str, Any]) -> None:
        self._hass = hass
        self._name: str = "ha_tts_adapter"
        self._lang: str = "ru"
        self._supported_languages: List[str] = ["ru", "ru-ru", "en", "en-us"]
        self._base_url: str = str(config.get(CONF_BASE_URL, "")).rstrip("/")
        self._timeout: int = int(config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
        self._format: str = str(config.get(CONF_FORMAT, DEFAULT_FORMAT))
        # Do NOT create aiohttp session here; get_engine runs in executor without a running loop

    @property
    def default_language(self) -> str:
        return self._lang

    @property
    def supported_languages(self) -> List[str]:
        return self._supported_languages

    @property
    def name(self) -> str:
        return self._name

    async def async_get_tts_audio(
        self,
        message: str,
        language: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[bytes]]:
        _ = language, options

        if not self._base_url:
            _LOGGER.error(
                "TTS configuration error in ha_tts_adapter: missing '%s' base URL",
                CONF_BASE_URL,
            )
            return (None, None)

        encoded_text = quote(message, safe="")
        url = f"{self._base_url}/synthesize/{encoded_text}"

        # Create aiohttp session lazily inside the coroutine where a loop is present
        session = async_get_clientsession(self._hass)

        try:
            async with session.get(
                url,
                timeout=ClientTimeout(total=self._timeout),
                headers={"Accept": "audio/mpeg"},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.error(
                        "TTS HTTP %s at %s in ha_tts_adapter: %s",
                        resp.status,
                        url,
                        text[:256],
                    )
                    return (None, None)
                data = await resp.read()
                if not data:
                    _LOGGER.error(
                        "TTS empty audio at %s in ha_tts_adapter: zero-length response",
                        url,
                    )
                    return (None, None)
                return (self._format, data)
        except Exception as exc:
            _LOGGER.error(
                "TTS request failure at %s in ha_tts_adapter: %s",
                self._base_url,
                str(exc),
            )
            return (None, None)

    # Keep sync version for compatibility where HA calls sync providers
    def get_tts_audio(
        self,
        message: str,
        language: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[bytes]]:
        _ = language, options

        if not self._base_url:
            _LOGGER.error(
                "TTS configuration error in ha_tts_adapter: missing '%s' base URL",
                CONF_BASE_URL,
            )
            return (None, None)

        try:
            encoded_text = quote(message, safe="")
            url = f"{self._base_url}/synthesize/{encoded_text}"
            response = requests.get(url, timeout=self._timeout, headers={"Accept": "audio/mpeg"})

            if response.status_code != 200:
                _LOGGER.error(
                    "TTS HTTP %s at %s in ha_tts_adapter: %s",
                    response.status_code,
                    url,
                    response.text[:256],
                )
                return (None, None)

            if not response.content:
                _LOGGER.error(
                    "TTS empty audio at %s in ha_tts_adapter: zero-length response",
                    url,
                )
                return (None, None)

            return (self._format, response.content)
        except requests.Timeout:
            _LOGGER.error(
                "TTS timeout at %s in ha_tts_adapter: exceeded %s seconds",
                self._base_url,
                self._timeout,
            )
            return (None, None)
        except requests.RequestException as req_exc:
            _LOGGER.error(
                "TTS request exception at %s in ha_tts_adapter: %s",
                self._base_url,
                str(req_exc),
            )
            return (None, None)
