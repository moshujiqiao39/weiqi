"""可训练的着法模型：局部特征打分，自对弈后按胜负更新权重。"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from .engine import (
    BLACK,
    EMPTY,
    WHITE,
    Board,
    collect,
    idx,
    is_eye,
    neighbors,
    opponent,
    xy,
)
from .ranks import builtin_style

ROOT = Path(__file__).resolve().parent.parent
WEIGHT_PATH = ROOT / "models" / "rl_policy.json"

FEATURES = [
    "bias",
    "captures",
    "saves",
    "self_atari",
    "eye_fill",
    "own_adj",
    "opp_adj",
    "connect",
    "atari_opp",
    "libs",
    "line1",
    "line2",
    "line3",
    "line4",
    "center",
    "near",
    "opening",
    "split",
]

DEFAULT_WEIGHTS = [
    0.4,   # bias
    82.0,  # captures
    70.0,  # saves
    -58.0, # self_atari
    -96.0, # eye_fill
    2.2,   # own_adj
    1.1,   # opp_adj
    9.0,   # connect
    16.0,  # atari_opp
    3.0,   # libs
    -7.0,  # line1
    0.4,   # line2
    4.2,   # line3
    3.6,   # line4
    1.4,   # center
    2.0,   # near
    7.5,   # opening
    14.0,  # split
]

_lock_weights: list[float] | None = None
_value_weights: list[float] | None = None
_trained_games = 0


def _zeros() -> list[float]:
    return [0.0] * len(FEATURES)


def load_model() -> None:
    global _lock_weights, _value_weights, _trained_games
    if not WEIGHT_PATH.exists():
        _lock_weights = DEFAULT_WEIGHTS[:]
        _value_weights = _zeros()
        _trained_games = 0
        return
    data = json.loads(WEIGHT_PATH.read_text(encoding="utf-8"))
    _lock_weights = list(data["policy"])
    _value_weights = list(data.get("value") or _zeros())
    _trained_games = int(data.get("games") or 0)


def save_model() -> None:
    WEIGHT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHT_PATH.write_text(
        json.dumps(
            {"policy": policy_weights(), "value": value_weights(), "games": _trained_games},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def policy_weights() -> list[float]:
    if _lock_weights is None:
        load_model()
    return _lock_weights  # type: ignore[return-value]


def value_weights() -> list[float]:
    if _value_weights is None:
        load_model()
    return _value_weights  # type: ignore[return-value]


def trained_games() -> int:
    if _lock_weights is None:
        load_model()
    return _trained_games


def dot(weights: list[float], feat: list[float]) -> float:
    return sum(a * b for a, b in zip(weights, feat))


def star_and_approach(size: int) -> set[tuple[int, int]]:
    if size == 19:
        pts = {(x, y) for x in (3, 9, 15) for y in (3, 9, 15)}
        pts.update({(2, 3), (3, 2), (15, 2), (16, 3), (2, 15), (3, 16), (15, 16), (16, 15)})
    elif size == 13:
        pts = {(x, y) for x in (3, 6, 9) for y in (3, 6, 9)}
    else:
        pts = {(2, 2), (2, 6), (6, 2), (6, 6), (4, 4)}
    pts.add((size // 2, size // 2))
    pts.update({(0, 0), (size - 1, 0), (0, size - 1), (1, 1), (size // 2, 0)})
    return pts


def candidate_points(board: Board) -> list[int]:
    size = board.size
    grid = board.grid
    pts: set[int] = set()
    stones = [i for i, v in enumerate(grid) if v]
    if len(stones) < 12:
        for x, y in star_and_approach(size):
            j = idx(x, y, size)
            if grid[j] == EMPTY:
                pts.add(j)
    for i in stones:
        x, y = xy(i, size)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = x + dx, y + dy
                if 0 <= nx < size and 0 <= ny < size:
                    j = idx(nx, ny, size)
                    if grid[j] == EMPTY:
                        pts.add(j)
    return list(pts)


def move_features(board: Board, i: int) -> list[float] | None:
    color = board.to_play
    size = board.size
    grid = board.grid
    if grid[i] != EMPTY:
        return None
    applied = board._apply(i, color)
    if applied is None:
        return None
    new_grid, _taken = applied
    x, y = xy(i, size)
    nei = neighbors(size)[i]
    opp = opponent(color)
    own_adj = sum(1 for n in nei if grid[n] == color)
    opp_adj = sum(1 for n in nei if grid[n] == opp)

    captures = 0
    capture_groups = 0
    atari_opp = 0
    seen: set[int] = set()
    for n in nei:
        if grid[n] != opp or n in seen:
            continue
        stones, libs = collect(grid, n, size)
        seen.update(stones)
        if len(libs) == 1 and libs[0] == i:
            captures += len(stones)
            capture_groups += 1
        elif i in libs and len(libs) == 2:
            atari_opp += 1

    saves = 0
    connect_groups = 0
    seen_own: set[int] = set()
    for n in nei:
        if grid[n] != color or n in seen_own:
            continue
        stones, libs = collect(grid, n, size)
        seen_own.update(stones)
        connect_groups += 1
        if len(libs) == 1 and libs[0] == i:
            saves += len(stones)

    eye = 1.0 if is_eye(grid, i, color, size) else 0.0
    stones, libs = collect(new_grid, i, size)
    self_atari = 1.0 if len(libs) == 1 and captures == 0 else 0.0
    edge = min(x, y, size - 1 - x, size - 1 - y)
    cx = (size - 1) / 2
    center = 1 - (abs(x - cx) + abs(y - cx)) / (size - 1)
    if connect_groups:
        near = 1.0
    else:
        best = 99
        for j, v in enumerate(grid):
            if v != color:
                continue
            jx, jy = xy(j, size)
            best = min(best, max(abs(jx - x), abs(jy - y)))
        near = 0.0 if best >= 99 else 1 / best
    opening = 0.0
    if len(board.moves) < 8 and (x, y) in star_and_approach(size) and edge >= 2:
        opening = 1.0
    values = {
        "bias": 1.0,
        "captures": float(captures),
        "saves": float(saves),
        "self_atari": self_atari,
        "eye_fill": eye,
        "own_adj": float(own_adj),
        "opp_adj": float(opp_adj),
        "connect": float(max(0, connect_groups - 1)),
        "atari_opp": float(atari_opp),
        "libs": len(libs) / 4,
        "line1": 1.0 if edge == 0 else 0.0,
        "line2": 1.0 if edge == 1 else 0.0,
        "line3": 1.0 if edge == 2 else 0.0,
        "line4": 1.0 if edge == 3 else 0.0,
        "center": center,
        "near": near,
        "opening": opening,
        "split": 1.0 if capture_groups >= 2 else 0.0,
    }
    return [values[name] for name in FEATURES]


def describe(feat: list[float]) -> str:
    got = dict(zip(FEATURES, feat))
    if got["split"] and got["captures"] >= 2:
        return "双打吃"
    if got["captures"] >= 1:
        n = int(got["captures"])
        return f"提掉 {n} 子"
    if got["saves"] >= 1:
        return "把被打吃的棋连出去"
    if got["atari_opp"] >= 1:
        return "打吃"
    if got["connect"] >= 1:
        return "连接"
    return ""


def _score_list(board: Board, weights: list[float]) -> list[tuple[float, int, list[float]]]:
    ranked = []
    for i in candidate_points(board):
        feat = move_features(board, i)
        if feat is None:
            continue
        ranked.append((dot(weights, feat), i, feat))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _greedy(board: Board, weights: list[float]) -> tuple[int | None, int | None]:
    ranked = _score_list(board, weights)
    ranked = [item for item in ranked if item[2][FEATURES.index("eye_fill")] < 1 or item[2][FEATURES.index("captures")] > 0]
    if not ranked:
        return None, None
    if ranked[0][0] < 0 and len(board.moves) > 8:
        return None, None
    return xy(ranked[0][1], board.size)


def influence(board: Board, color: int) -> float:
    score = 0.0
    for v in board.grid:
        if v == color:
            score += 6
        elif v == opponent(color):
            score -= 6
    for group in board.group_map():
        sign = 1 if group["color"] == color else -1
        libs = len(group["libs"])
        stones = len(group["stones"])
        if libs <= 1:
            score += sign * (-14 * stones)
        else:
            score += sign * min(libs, 5)
    return score


def choose_move(
    board: Board,
    rank: str,
    rng: random.Random | None = None,
    weights: list[float] | None = None,
) -> tuple[int | None, int | None, str]:
    """按段位选点。返回 x, y, 短评。x 为 None 表示停一手。"""
    if board.over:
        return None, None, ""
    rng = rng or random.Random()
    weights = weights if weights is not None else policy_weights()
    style = builtin_style(rank)
    ranked = _score_list(board, weights)
    if not ranked:
        return None, None, "停一手"

    if style["read"] >= 1:
        color = board.to_play
        refined = []
        for score, i, feat in ranked[:6]:
            trial = board.clone()
            x, y = xy(i, board.size)
            if trial.play(x, y):
                continue
            if style["read"] >= 2 and not trial.over:
                ox, oy = _greedy(trial, weights)
                trial.play(ox, oy)
            refined.append((score * 0.2 + influence(trial, color), i, feat))
        if refined:
            refined.sort(key=lambda item: item[0], reverse=True)
            ranked = refined

    eye_i = FEATURES.index("eye_fill")
    cap_i = FEATURES.index("captures")
    if style["blunder"] < 0.08:
        solid = [item for item in ranked if item[2][eye_i] < 1 or item[2][cap_i] > 0]
        if solid:
            ranked = solid

    best_score, best_i, best_feat = ranked[0]
    save_i = FEATURES.index("saves")
    atari_i = FEATURES.index("atari_opp")
    quiet = best_feat[cap_i] == 0 and best_feat[save_i] == 0 and best_feat[atari_i] == 0
    late = len(board.moves) >= int(board.size * board.size * 0.62)
    opponent_passed = board.passes == 1 and len(board.moves) > board.size
    if quiet and (opponent_passed or (late and best_score < 3)):
        return None, None, "停一手"

    if rng.random() < style["blunder"]:
        pool = ranked[: max(style["top_k"], 2)]
        _score, i, feat = rng.choice(pool)
        return (*xy(i, board.size), describe(feat))

    pool = ranked[: max(1, style["top_k"])]
    temp = max(0.08, style["temperature"])
    peak = pool[0][0]
    logits = [math.exp((score - peak) / (temp * 12)) for score, _i, _f in pool]
    total = sum(logits)
    pick = rng.random() * total
    acc = 0.0
    chosen = pool[0]
    for item, w in zip(pool, logits):
        acc += w
        if acc >= pick:
            chosen = item
            break
    return (*xy(chosen[1], board.size), describe(chosen[2]))


def apply_game_update(records: list[tuple[list[float], int]], black_result: float, lr: float = 0.03) -> None:
    """用一局的胜负更新策略和价值。black_result 为黑棋 +1 / -1 / 0。"""
    global _trained_games
    policy = policy_weights()
    value = value_weights()
    for feat, color in records:
        target = black_result if color == BLACK else -black_result
        pred = math.tanh(dot(value, feat))
        advantage = target - pred
        scale = lr * advantage
        vscale = lr * 2 * advantage * (1 - pred * pred)
        for j, f in enumerate(feat):
            if not f:
                continue
            policy[j] += scale * f
            value[j] += vscale * f
        # 保住提子、不填眼这些底线，避免学坏之后完全不会吃子。
        policy[FEATURES.index("captures")] = max(20.0, policy[FEATURES.index("captures")])
        policy[FEATURES.index("eye_fill")] = min(-20.0, policy[FEATURES.index("eye_fill")])
        policy[FEATURES.index("self_atari")] = min(-8.0, policy[FEATURES.index("self_atari")])
    _trained_games += 1


def play_training_game(rng: random.Random | None = None) -> float:
    """下完一盘 9 路自对弈并更新权重。返回黑棋结果。"""
    rng = rng or random.Random()
    board = Board(9, komi=7.5)
    weights = policy_weights()
    records: list[tuple[list[float], int]] = []
    limit = 9 * 9 * 2
    while not board.over and len(board.moves) < limit:
        ranked = _score_list(board, weights)
        if not ranked:
            board.play(None, None)
            continue
        peak = ranked[0][0]
        pool = ranked[:8]
        logits = [math.exp((score - peak) / 10) for score, _i, _f in pool]
        total = sum(logits)
        pick = rng.random() * total
        acc = 0.0
        chosen = pool[0]
        for item, w in zip(pool, logits):
            acc += w
            if acc >= pick:
                chosen = item
                break
        _score, i, feat = chosen
        records.append((feat, board.to_play))
        x, y = xy(i, board.size)
        err = board.play(x, y)
        if err:
            board.play(None, None)
    from .engine import guess_dead

    result = board.score(set(guess_dead(board)))
    black_result = 1.0 if result["winner"] == "B" else -1.0 if result["winner"] == "W" else 0.0
    apply_game_update(records, black_result)
    save_model()
    return black_result
