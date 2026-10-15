"""中国规则围棋：气尽提子、禁自杀、全局同形（位置超级劫）、子空皆地。"""

from __future__ import annotations

import random

EMPTY, BLACK, WHITE = 0, 1, 2
PASS = None

_RNG = random.Random(20261014)
_ZOBRIST = [
    [_RNG.randrange(1 << 62) for _ in range(3)]
    for _ in range(19 * 19)
]


def opponent(color: int) -> int:
    return WHITE if color == BLACK else BLACK


def idx(x: int, y: int, size: int) -> int:
    return y * size + x


def xy(i: int, size: int) -> tuple[int, int]:
    return i % size, i // size


def neighbor_table(size: int) -> list[tuple[int, ...]]:
    table = []
    for y in range(size):
        for x in range(size):
            pts = []
            if x > 0:
                pts.append(idx(x - 1, y, size))
            if x + 1 < size:
                pts.append(idx(x + 1, y, size))
            if y > 0:
                pts.append(idx(x, y - 1, size))
            if y + 1 < size:
                pts.append(idx(x, y + 1, size))
            table.append(tuple(pts))
    return table


_NEI: dict[int, list[tuple[int, ...]]] = {}


def neighbors(size: int) -> list[tuple[int, ...]]:
    if size not in _NEI:
        _NEI[size] = neighbor_table(size)
    return _NEI[size]


def zobrist(grid: list[int], size: int) -> int:
    h = 0
    n = size * size
    for i in range(n):
        v = grid[i]
        if v:
            h ^= _ZOBRIST[i][v]
    return h


def collect(grid: list[int], start: int, size: int) -> tuple[list[int], list[int]]:
    color = grid[start]
    nei = neighbors(size)
    stones = []
    libs = []
    seen = {start}
    stack = [start]
    lib_seen = set()
    while stack:
        p = stack.pop()
        stones.append(p)
        for n in nei[p]:
            v = grid[n]
            if v == EMPTY:
                if n not in lib_seen:
                    lib_seen.add(n)
                    libs.append(n)
            elif v == color and n not in seen:
                seen.add(n)
                stack.append(n)
    return stones, libs


class Board:
    def __init__(self, size: int = 19, komi: float = 7.5):
        if not 5 <= size <= 19:
            raise ValueError("棋盘路数需要在 5 到 19 之间")
        self.size = size
        self.komi = komi
        self.grid = [EMPTY] * (size * size)
        self.to_play = BLACK
        self.captures = {BLACK: 0, WHITE: 0}
        self.history = [zobrist(self.grid, size)]
        self.passes = 0
        self.moves: list[tuple[int, int | None, int | None]] = []
        self.over = False
        self.last = None  # (x, y) or None for pass

    def clone(self) -> "Board":
        b = Board(self.size, self.komi)
        b.grid = self.grid[:]
        b.to_play = self.to_play
        b.captures = dict(self.captures)
        b.history = self.history[:]
        b.passes = self.passes
        b.moves = self.moves[:]
        b.over = self.over
        b.last = self.last
        return b

    def hash(self) -> int:
        return self.history[-1]

    def play(self, x: int | None, y: int | None = None) -> str | None:
        """落子。成功返回 None，否则返回原因。会改动棋盘。"""
        if self.over:
            return "对局已经结束"
        if x is None or y is None:
            self.passes += 1
            self.moves.append((self.to_play, None, None))
            self.last = None
            self.to_play = opponent(self.to_play)
            if self.passes >= 2:
                self.over = True
            return None

        if not (0 <= x < self.size and 0 <= y < self.size):
            return "超出棋盘"
        i = idx(x, y, self.size)
        if self.grid[i] != EMPTY:
            return "这里已经有子"
        placed = self._apply(i, self.to_play)
        if placed is None:
            return "不能下在这里"
        grid, taken = placed
        self.grid = grid
        if taken:
            self.captures[self.to_play] += len(taken)
        self.history.append(zobrist(self.grid, self.size))
        self.passes = 0
        self.moves.append((self.to_play, x, y))
        self.last = (x, y)
        self.to_play = opponent(self.to_play)
        return None

    def _apply(self, i: int, color: int) -> tuple[list[int], list[int]] | None:
        size = self.size
        nei = neighbors(size)
        grid = self.grid[:]
        grid[i] = color
        opp = opponent(color)
        taken: list[int] = []
        seen_opp = set()
        for n in nei[i]:
            if grid[n] != opp or n in seen_opp:
                continue
            stones, libs = collect(grid, n, size)
            seen_opp.update(stones)
            if not libs:
                for s in stones:
                    grid[s] = EMPTY
                    taken.append(s)
        _stones, libs = collect(grid, i, size)
        if not libs:
            return None
        if zobrist(grid, size) in self.history:
            return None
        return grid, taken

    def legal(self, x: int | None, y: int | None = None) -> bool:
        if self.over:
            return False
        if x is None or y is None:
            return True
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False
        i = idx(x, y, self.size)
        if self.grid[i] != EMPTY:
            return False
        return self._apply(i, self.to_play) is not None

    def setup(self, black: list[tuple[int, int]], white: list[tuple[int, int]], to_play: int = BLACK):
        """摆题。直接放入棋子，不走对局规则。"""
        self.grid = [EMPTY] * (self.size * self.size)
        for x, y in black:
            self.grid[idx(x, y, self.size)] = BLACK
        for x, y in white:
            self.grid[idx(x, y, self.size)] = WHITE
        for i, v in enumerate(self.grid):
            if not v:
                continue
            _stones, libs = collect(self.grid, i, self.size)
            if not libs:
                raise ValueError(f"摆题后 {xy(i, self.size)} 没有气")
        self.to_play = to_play
        self.captures = {BLACK: 0, WHITE: 0}
        self.history = [zobrist(self.grid, self.size)]
        self.passes = 0
        self.moves = []
        self.over = False
        self.last = None

    def score(self, dead: set[int] | None = None) -> dict:
        """死子拿掉后按中国规则数子。dead 是要拿掉的棋子下标。"""
        dead = dead or set()
        size = self.size
        grid = self.grid[:]
        for i in dead:
            if grid[i] != EMPTY:
                grid[i] = EMPTY
        seen = [False] * (size * size)
        nei = neighbors(size)
        black_terr = 0
        white_terr = 0
        for i, v in enumerate(grid):
            if v != EMPTY or seen[i]:
                continue
            stack = [i]
            seen[i] = True
            region = []
            borders = set()
            while stack:
                p = stack.pop()
                region.append(p)
                for n in nei[p]:
                    nv = grid[n]
                    if nv == EMPTY and not seen[n]:
                        seen[n] = True
                        stack.append(n)
                    elif nv != EMPTY:
                        borders.add(nv)
            if borders == {BLACK}:
                black_terr += len(region)
            elif borders == {WHITE}:
                white_terr += len(region)
        black = sum(1 for v in grid if v == BLACK) + black_terr
        white = sum(1 for v in grid if v == WHITE) + white_terr + self.komi
        winner = "B" if black > white else "W" if white > black else "draw"
        return {
            "black": black,
            "white": white,
            "komi": self.komi,
            "winner": winner,
            "margin": abs(black - white),
        }

    def group_map(self) -> list[dict]:
        size = self.size
        seen = [False] * (size * size)
        groups = []
        for i, v in enumerate(self.grid):
            if not v or seen[i]:
                continue
            stones, libs = collect(self.grid, i, size)
            for s in stones:
                seen[s] = True
            groups.append({"color": v, "stones": stones, "libs": libs})
        return groups


def is_eye(grid: list[int], i: int, color: int, size: int) -> bool:
    """粗略真眼：直线邻接点都是己方，斜角上对方子不够破眼。"""
    if grid[i] != EMPTY:
        return False
    nei = neighbors(size)
    ns = nei[i]
    if any(grid[n] != color for n in ns):
        return False
    x, y = xy(i, size)
    diags = []
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < size and 0 <= ny < size:
            diags.append(grid[idx(nx, ny, size)])
    opp = opponent(color)
    bad = sum(1 for v in diags if v == opp)
    if len(diags) <= 2:
        return bad == 0
    if len(diags) == 3:
        return bad < 2
    return bad < 2


def guess_dead(board: Board) -> list[int]:
    """终局时猜死子，供用户改正。两眼视为活，气很少且没眼视为死。"""
    dead = []
    grid = board.grid
    size = board.size
    for group in board.group_map():
        eyes = []
        seen = set()
        for s in group["stones"]:
            for n in neighbors(size)[s]:
                if n in seen:
                    continue
                if is_eye(grid, n, group["color"], size):
                    seen.add(n)
                    eyes.append(n)
        if len(eyes) >= 2:
            continue
        if len(group["libs"]) <= 1 or (len(eyes) == 0 and len(group["libs"]) <= 2):
            dead.extend(group["stones"])
    return dead


COLS = "ABCDEFGHJKLMNOPQRST"


def to_gtp(x: int | None, y: int | None, size: int) -> str:
    if x is None or y is None:
        return "pass"
    return f"{COLS[x]}{size - y}"


def from_gtp(text: str, size: int) -> tuple[int | None, int | None]:
    s = text.strip()
    if not s or s.lower() == "pass" or s.lower() == "resign":
        return None, None
    col = COLS.index(s[0].upper())
    row = size - int(s[1:])
    return col, row
