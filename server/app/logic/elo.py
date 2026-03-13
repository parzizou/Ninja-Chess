from __future__ import annotations

K = 32


def expected_score(rating_a: int, rating_b: int) -> float:
    """Return expected score of player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def compute_new_ratings(
    winner_elo: int, loser_elo: int
) -> tuple[int, int]:
    """Return (new_winner_elo, new_loser_elo) after a decisive game."""
    e_winner = expected_score(winner_elo, loser_elo)
    e_loser = expected_score(loser_elo, winner_elo)

    new_winner = round(winner_elo + K * (1.0 - e_winner))
    new_loser = round(loser_elo + K * (0.0 - e_loser))

    # Floor at 100 to avoid negative elo
    new_loser = max(new_loser, 100)

    return new_winner, new_loser
