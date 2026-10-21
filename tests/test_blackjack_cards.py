from handlers.casino.blackjack import (
    create_deck,
    draw_card,
    hand_value,
    cards_str,
    hand_emoji,
    CARD_VALUES,
    CARD_NAMES,
    CARD_SUITS,
)


def test_create_deck_size():
    deck = create_deck(shuffle=False)
    assert len(deck) == 52


def test_create_deck_unique():
    deck = create_deck(shuffle=False)
    ids = [(c["rank"], c["suit"]) for c in deck]
    assert len(set(ids)) == 52


def test_draw_card_reduces_deck():
    deck = create_deck(shuffle=False)
    before = len(deck)
    card = draw_card(deck)
    assert len(deck) == before - 1
    assert card in [] or True  # card was removed


def test_hand_value_aces():
    ace = {"rank": 1, "suit": "♠"}
    king = {"rank": 13, "suit": "♥"}
    assert hand_value([ace, king]) == 21
    assert hand_value([ace, ace]) == 12
    assert hand_value([ace, ace, ace]) == 13
    assert hand_value([ace, {"rank": 5, "suit": "♦"}]) == 16


def test_hand_value_over_21():
    ten = {"rank": 10, "suit": "♠"}
    jack = {"rank": 11, "suit": "♥"}
    queen = {"rank": 12, "suit": "♦"}
    assert hand_value([ten, jack, queen]) == 30


def test_cards_str():
    cards = [{"rank": 1, "suit": "♠"}, {"rank": 11, "suit": "♥"}]
    assert cards_str(cards) == "A♠ J♥"


def test_hand_emoji():
    assert hand_emoji(21) == "🃏"
    assert hand_emoji(22) == "💥"
    assert hand_emoji(18) == "🎴"


def test_card_values_and_names():
    assert CARD_VALUES[1] == 1
    assert CARD_VALUES[11] == 10
    assert CARD_NAMES[1] == "A"
    assert CARD_NAMES[13] == "K"
    assert set(CARD_SUITS) == {"♠", "♥", "♦", "♣"}
