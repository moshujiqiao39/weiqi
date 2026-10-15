"""18 级到 9 段。"""

from __future__ import annotations

RANKS: list[str] = [f"{k}级" for k in range(18, 0, -1)] + [f"{d}段" for d in range(1, 10)]


def rank_index(rank: str) -> int:
    if rank not in RANKS:
        raise ValueError(f"没有这个段位：{rank}")
    return RANKS.index(rank)


def katago_profile(rank: str) -> str:
    """KataGo 人类棋力档。18级 → rank_18k，1段 → rank_1d。"""
    if rank.endswith("级"):
        return f"rank_{int(rank[:-1])}k"
    return f"rank_{int(rank[:-1])}d"


def builtin_style(rank: str) -> dict:
    """没有 KataGo 时，用失误率和搜索深度拉开级别。0 最弱，26 最强。"""
    t = rank_index(rank) / (len(RANKS) - 1)
    return {
        "temperature": 1.35 - 1.15 * t,
        "top_k": max(1, round(14 - 13 * t)),
        "blunder": max(0.0, 0.34 * (1 - t * 1.15)),
        "read": 0 if t < 0.35 else 1 if t < 0.7 else 2,
    }


def katago_style(rank: str) -> dict:
    """低段几乎按该级别的人类着法分布走；段位越高，温度越低、搜索越多。"""
    i = rank_index(rank)
    t = i / (len(RANKS) - 1)
    dan = max(0, i - 17)
    return {
        "profile": katago_profile(rank),
        "temperature": round(1.05 - 0.95 * t, 3),
        "max_visits": 8 if dan == 0 else 24 + dan * 36,
        "max_time": 2.5 if dan == 0 else min(8.0, 3.2 + dan * 0.45),
        "pikl_lambda": 1e8 if dan <= 1 else round(max(0.2, 1.3 - dan * 0.12), 3),
    }
