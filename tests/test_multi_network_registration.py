"""
Tests for multi-network tournament registration (Abstract + Avalanche).
Covers: get_registration_network_recommendation, _web3_config_for_network, network param in register/unregister.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from config import Config
from services.tournament_registration_service import TournamentRegistrationService


class TestGetRegistrationNetworkRecommendation:
    """get_registration_network_recommendation(wallet) - balance check and preferred network."""

    @pytest.mark.asyncio
    async def test_returns_abstract_when_avalanche_not_configured(self):
        """When WEB3_PROVIDER_URL_AVALANCHE or TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE is empty, always abstract."""
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", ""):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", ""):
                result = await TournamentRegistrationService.get_registration_network_recommendation(
                    "0x1234567890123456789012345678901234567890"
                )
        assert result["preferred_network"] == "abstract"
        assert result["switch_network_required"] is False
        assert result["avalanche_chain_id"] is None
        assert result["avalanche_contract_address"] is None

    @pytest.mark.asyncio
    async def test_returns_abstract_when_has_gas_on_abstract(self):
        """When user has enough gas on Abstract, recommend abstract."""
        min_gas = 100_000_000_000_000
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvaxContract"):
                with patch.object(Config, "MIN_GAS_BALANCE_ABSTRACT", min_gas):
                    with patch(
                        "services.tournament_registration_service.get_native_balance_wei",
                        new_callable=AsyncMock,
                        side_effect=[min_gas + 1, 0],  # abstract enough, avax zero
                    ):
                        result = await TournamentRegistrationService.get_registration_network_recommendation(
                            "0x1234567890123456789012345678901234567890"
                        )
        assert result["preferred_network"] == "abstract"
        assert result["switch_network_required"] is False

    @pytest.mark.asyncio
    async def test_returns_avalanche_when_no_gas_abstract_but_has_on_avalanche(self):
        """When no gas on Abstract but has on Avalanche, recommend switch to Avalanche."""
        min_abs = 100_000_000_000_000
        min_avax = 100_000_000_000_000
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvaxContract"):
                with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
                    with patch.object(Config, "MIN_GAS_BALANCE_ABSTRACT", min_abs):
                        with patch.object(Config, "MIN_GAS_BALANCE_AVALANCHE", min_avax):
                            with patch(
                                "services.tournament_registration_service.get_native_balance_wei",
                                new_callable=AsyncMock,
                                side_effect=[0, min_avax + 1],  # abstract zero, avax enough
                            ):
                                result = await TournamentRegistrationService.get_registration_network_recommendation(
                                    "0x1234567890123456789012345678901234567890"
                                )
        assert result["preferred_network"] == "avalanche"
        assert result["switch_network_required"] is True
        assert result["avalanche_chain_id"] == 43114
        assert result["avalanche_contract_address"] == "0xAvaxContract"
        assert "Avalanche" in (result["message"] or "")

    @pytest.mark.asyncio
    async def test_returns_abstract_when_no_gas_on_both(self):
        """When no gas on both networks, still recommend abstract (per plan)."""
        min_gas = 100_000_000_000_000
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvaxContract"):
                with patch.object(Config, "MIN_GAS_BALANCE_ABSTRACT", min_gas):
                    with patch.object(Config, "MIN_GAS_BALANCE_AVALANCHE", min_gas):
                        with patch(
                            "services.tournament_registration_service.get_native_balance_wei",
                            new_callable=AsyncMock,
                            side_effect=[0, 0],
                        ):
                            result = await TournamentRegistrationService.get_registration_network_recommendation(
                                "0x1234567890123456789012345678901234567890"
                            )
        assert result["preferred_network"] == "abstract"
        assert result["switch_network_required"] is False

    @pytest.mark.asyncio
    async def test_fallback_to_abstract_on_balance_check_exception(self):
        """When get_native_balance_wei raises, return abstract (no crash)."""
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvaxContract"):
                with patch(
                    "services.tournament_registration_service.get_native_balance_wei",
                    new_callable=AsyncMock,
                    side_effect=Exception("RPC timeout"),
                ):
                    result = await TournamentRegistrationService.get_registration_network_recommendation(
                        "0x1234567890123456789012345678901234567890"
                    )
        assert result["preferred_network"] == "abstract"
        assert result["switch_network_required"] is False


class TestGetNetworkInfoForChainId:
    """get_network_info_for_chain_id(chain_id) - для unregister: сеть по registration_chain_id."""

    def test_returns_abstract_for_abstract_chain_id(self):
        with patch.object(Config, "ABSTRACT_CHAIN_ID", 2741):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", "0xAbstract"):
                info = TournamentRegistrationService.get_network_info_for_chain_id(2741)
        assert info is not None
        assert info["network"] == "abstract"
        assert info["chain_id"] == 2741
        assert info["contract_address"] == "0xAbstract"

    def test_returns_avalanche_for_avalanche_chain_id_when_configured(self):
        with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvax"):
                info = TournamentRegistrationService.get_network_info_for_chain_id(43114)
        assert info is not None
        assert info["network"] == "avalanche"
        assert info["chain_id"] == 43114
        assert info["contract_address"] == "0xAvax"

    def test_returns_none_for_none_chain_id(self):
        assert TournamentRegistrationService.get_network_info_for_chain_id(None) is None

    def test_returns_none_for_unknown_chain_id(self):
        assert TournamentRegistrationService.get_network_info_for_chain_id(99999) is None

    def test_returns_none_for_avalanche_chain_id_when_avalanche_not_configured(self):
        with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", ""):
                info = TournamentRegistrationService.get_network_info_for_chain_id(43114)
        assert info is None


class TestWeb3ConfigForNetwork:
    """_web3_config_for_network(network) - provider, contract, chain_id per network."""

    def test_abstract_returns_main_config(self):
        """network=abstract returns WEB3_PROVIDER_URL, TOURNAMENT_CONTRACT_ADDRESS, ABSTRACT_CHAIN_ID."""
        with patch.object(Config, "WEB3_PROVIDER_URL", "https://abstract.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS", "0xAbstractContract"):
                with patch.object(Config, "ABSTRACT_CHAIN_ID", 2741):
                    url, addr, chain_id = TournamentRegistrationService._web3_config_for_network("abstract")
        assert url == "https://abstract.example.com"
        assert addr == "0xAbstractContract"
        assert chain_id == 2741

    def test_avalanche_raises_when_not_configured(self):
        """network=avalanche when Avalanche URL or contract not set raises HTTPException."""
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", ""):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvax"):
                with pytest.raises(HTTPException) as exc_info:
                    TournamentRegistrationService._web3_config_for_network("avalanche")
        assert exc_info.value.status_code == 400
        assert "not configured" in (exc_info.value.detail or "").lower()

    def test_avalanche_returns_avalanche_config_when_configured(self):
        """network=avalanche when configured returns Avalanche provider, contract, chain_id."""
        with patch.object(Config, "WEB3_PROVIDER_URL_AVALANCHE", "https://avax.example.com"):
            with patch.object(Config, "TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE", "0xAvaxContract"):
                with patch.object(Config, "AVALANCHE_CHAIN_ID", 43114):
                    url, addr, chain_id = TournamentRegistrationService._web3_config_for_network("avalanche")
        assert url == "https://avax.example.com"
        assert addr == "0xAvaxContract"
        assert chain_id == 43114
