"""
Tests for Avalanche-only tournament registration.
Covers: get_network_info_for_chain_id, _get_avalanche_web3_config.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from config import Config
from services.tournament_registration_service import TournamentRegistrationService


class TestGetNetworkInfoForChainId:
    """get_network_info_for_chain_id(chain_id) - for unregister: network by registration_chain_id."""

    def test_returns_avalanche_for_avalanche_chain_id_when_configured(self):
        with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", "0xAvax"):
                info = TournamentRegistrationService.get_network_info_for_chain_id(43114)
        assert info is not None
        assert info["network"] == "avalanche"
        assert info["chain_id"] == 43114
        assert info["contract_address"] == "0xAvax"

    def test_returns_none_for_none_chain_id(self):
        assert TournamentRegistrationService.get_network_info_for_chain_id(None) is None

    def test_returns_none_for_unknown_chain_id(self):
        assert TournamentRegistrationService.get_network_info_for_chain_id(99999) is None

    def test_returns_none_for_avalanche_chain_id_when_contract_not_configured(self):
        with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", ""):
                info = TournamentRegistrationService.get_network_info_for_chain_id(43114)
        assert info is None


class TestGetAvalancheWeb3Config:
    """_get_avalanche_web3_config() - provider, contract, chain_id for Avalanche."""

    def test_raises_when_provider_not_configured(self):
        with patch.object(Config, "WEB3_PROVIDER_URL", ""):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", "0xAvax"):
                with pytest.raises(HTTPException) as exc_info:
                    TournamentRegistrationService._get_avalanche_web3_config()
        assert exc_info.value.status_code == 503
        assert "not configured" in (exc_info.value.detail or "").lower()

    def test_raises_when_contract_not_configured(self):
        with patch.object(Config, "WEB3_PROVIDER_URL", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", ""):
                with pytest.raises(HTTPException) as exc_info:
                    TournamentRegistrationService._get_avalanche_web3_config()
        assert exc_info.value.status_code == 503
        assert "not configured" in (exc_info.value.detail or "").lower()

    def test_returns_config_when_configured(self):
        with patch.object(Config, "WEB3_PROVIDER_URL", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", "0xAvaxContract"):
                with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
                    url, addr, chain_id = TournamentRegistrationService._get_avalanche_web3_config()
        assert url == "https://avax.example.com"
        assert addr == "0xAvaxContract"
        assert chain_id == 43114
