from handlers.casino.games_rps import _rps_winner, _RPS_MAP, _RPS_REV, RULES


def test_rps_map():
    assert _RPS_MAP["rock"] == "🪨"
    assert _RPS_MAP["scissors"] == "✂️"
    assert _RPS_MAP["paper"] == "📄"


def test_rps_rev():
    assert _RPS_REV["🪨"] == "rock"
    assert _RPS_REV["✂️"] == "scissors"
    assert _RPS_REV["📄"] == "paper"


def test_rps_winner_tie():
    assert _rps_winner("🪨", "🪨") == 0
    assert _rps_winner("✂️", "✂️") == 0
    assert _rps_winner("📄", "📄") == 0


def test_rps_winner_player1():
    assert _rps_winner("🪨", "✂️") == 1  # камень бьёт ножницы
    assert _rps_winner("✂️", "📄") == 1  # ножницы бьют бумагу
    assert _rps_winner("📄", "🪨") == 1  # бумага бьёт камень


def test_rps_winner_player2():
    assert _rps_winner("✂️", "🪨") == 2
    assert _rps_winner("📄", "✂️") == 2
    assert _rps_winner("🪨", "📄") == 2


def test_rules_nonempty():
    assert "Камень" in RULES or "🪨" in RULES
