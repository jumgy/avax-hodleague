# Test Avalanche flow: auth -> tournaments -> validate-deck (preferred_network, avalanche_contract_address)
$Base = "http://localhost:8000"
$Wallet = "0xB39bc1Db1A9DbE3A19fC212973a9663997778CfD"

Write-Host "[1] POST /api/auth/test-verify ..."
$auth = Invoke-RestMethod -Uri "$Base/api/auth/test-verify" -Method POST -ContentType "application/json" -Body (@{wallet_address=$Wallet} | ConvertTo-Json)
$token = $auth.access_token
if (-not $token) { Write-Host "No token"; exit 1 }
Write-Host "    OK, token received"

$headers = @{ Authorization = "Bearer $token" }

Write-Host "[2] GET /api/tournaments?status_filter=registration ..."
$tournaments = Invoke-RestMethod -Uri "$Base/api/tournaments?status_filter=registration&limit=5" -Headers $headers
$items = $tournaments.items
if (-not $items -or $items.Count -eq 0) {
    Write-Host "    No tournaments in registration, trying without filter ..."
    $tournaments = Invoke-RestMethod -Uri "$Base/api/tournaments?limit=5" -Headers $headers
    $items = $tournaments.items
}
$tid = if ($items -and $items.Count -gt 0) { $items[0].id } else { 1 }
Write-Host "    tournament_id = $tid"

Write-Host "[3] GET /api/users/me?include_cards=true ..."
$me = Invoke-RestMethod -Uri "$Base/api/users/me?include_cards=true" -Headers $headers
$cards = @()
if ($me.cards) { $cards = @($me.cards) }
$deck = @()
$w = 0
$weightLimit = 30
foreach ($c in $cards) {
    $ucId = $c.user_card_id; if (-not $ucId) { $ucId = $c.id }
    $weight = 0; if ($null -ne $c.token_weight) { $weight = [double]$c.token_weight }; if ($null -ne $c.weight) { $weight = [double]$c.weight }
    if ($ucId -and ($w + $weight) -le $weightLimit) { $deck += $ucId; $w += $weight }
    if ($deck.Count -ge 5) { break }
}
if ($deck.Count -lt 5) {
    Write-Host "    User has $($deck.Count) cards (need 5). Taking first 5 by user_card_id anyway..."
    $deck = @()
    foreach ($c in $cards) {
        $ucId = $c.user_card_id; if (-not $ucId) { $ucId = $c.id }
        if ($ucId) { $deck += $ucId }; if ($deck.Count -ge 5) { break }
    }
}
if ($deck.Count -lt 5) {
    Write-Host "    FAIL: User has only $($deck.Count) cards. Need 5 for validate-deck."
    exit 1
}
$deck = $deck[0..4]
Write-Host "    deck_composition = [$($deck -join ',')] (5 cards)"

Write-Host "[4] POST /api/tournaments/$tid/validate-deck ..."
$body = @{ deck_composition = $deck } | ConvertTo-Json
try {
    $validate = Invoke-RestMethod -Uri "$Base/api/tournaments/$tid/validate-deck" -Method POST -Headers $headers -ContentType "application/json" -Body $body
} catch {
    Write-Host "    Error: $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
    exit 1
}

Write-Host ""
Write-Host "--- validate-deck response (network / Avalanche) ---"
Write-Host "  preferred_network:         $($validate.preferred_network)"
Write-Host "  switch_network_required:   $($validate.switch_network_required)"
Write-Host "  avalanche_chain_id:        $($validate.avalanche_chain_id)"
Write-Host "  avalanche_contract_address: $($validate.avalanche_contract_address)"
Write-Host "  valid: $($validate.valid), deck_hash: $($validate.deck_hash)"
Write-Host ""

$expectedContract = "0x6BE2e8C41E899c51e899B962e2C8dcED2125B48e"
if ($validate.avalanche_contract_address -eq $expectedContract -and $validate.avalanche_chain_id -eq 43114) {
    Write-Host "[OK] Avalanche config present (contract + chain_id). For no Abstract gas, preferred_network should be avalanche."
} elseif ($validate.preferred_network -eq "avalanche") {
    Write-Host "[OK] preferred_network=avalanche (wallet has no gas on Abstract, only on Avalanche)."
} else {
    Write-Host "[INFO] preferred_network=$($validate.preferred_network). Set WEB3_PROVIDER_URL_AVALANCHE and TOURNAMENT_CONTRACT_ADDRESS_AVALANCHE in .env if needed."
}
