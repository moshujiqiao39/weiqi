"""对局和做题的局面。"""

from __future__ import annotations

from .ai import choose_move
from .engine import BLACK, WHITE, Board, collect, guess_dead, idx, opponent, to_gtp, xy
from .katago_engine import KataGo
from .problems import by_id

COLOR_NAME = {BLACK: "B", WHITE: "W"}


def color_of(text: str) -> int:
    return BLACK if text == "B" else WHITE


def score_text(score: dict) -> str:
    if score.get("resigned"):
        winner = "黑" if score["winner"] == "B" else "白"
        return f"{winner}胜，对方认输"
    if score["winner"] == "draw":
        return "和棋"
    winner = "黑" if score["winner"] == "B" else "白"
    margin = score["margin"]
    text = f"{margin:.1f}".rstrip("0").rstrip(".")
    return f"{winner}胜 {text} 目"


class Game:
    def __init__(self, size: int, rank: str, human: str, engine: str):
        self.board = Board(size, 7.5)
        self.rank = rank
        self.human = color_of(human)
        self.engine = engine
        self.phase = "play"
        self.dead: set[int] = set()
        self.message = ""
        self.score: dict | None = None
        self.undo_stack: list[tuple] = []

    def snapshot(self) -> tuple:
        return (self.board.clone(), set(self.dead), self.phase, self.message, self.score)

    def restore(self, snap: tuple) -> None:
        self.board, dead, self.phase, self.message, self.score = snap
        self.dead = set(dead)

    def public(self) -> dict:
        moves = []
        for n, (color, x, y) in enumerate(self.board.moves, start=1):
            moves.append(
                {
                    "n": n,
                    "color": COLOR_NAME[color],
                    "coord": "停" if x is None else to_gtp(x, y, self.board.size),
                }
            )
        score = None
        if self.score:
            score = dict(self.score)
            score["text"] = score_text(score)
        return {
            "size": self.board.size,
            "board": self.board.grid,
            "toPlay": COLOR_NAME[self.board.to_play],
            "human": COLOR_NAME[self.human],
            "last": self.board.last,
            "captures": {
                "B": self.board.captures[BLACK],
                "W": self.board.captures[WHITE],
            },
            "moves": moves[-40:],
            "moveCount": len(self.board.moves),
            "phase": self.phase,
            "dead": [list(xy(i, self.board.size)) for i in sorted(self.dead)],
            "score": score,
            "rank": self.rank,
            "engine": self.engine,
            "message": self.message,
            "yourTurn": self.phase == "play" and self.board.to_play == self.human,
        }

    def enter_scoring(self) -> None:
        self.phase = "scoring"
        self.dead = set(guess_dead(self.board))
        self.score = self.board.score(self.dead)
        self.message = "双方停一手。点死子可以改判，然后确认数子。"

    def finish(self) -> None:
        self.phase = "over"
        self.score = self.board.score(self.dead)
        self.message = score_text(self.score)

    def toggle_dead(self, x: int, y: int) -> str | None:
        if self.phase != "scoring":
            return "现在不是数子"
        i = idx(x, y, self.board.size)
        if self.board.grid[i] == 0:
            return "这里没有棋子"
        stones, _libs = collect(self.board.grid, i, self.board.size)
        group = set(stones)
        if group <= self.dead:
            self.dead -= group
        else:
            self.dead |= group
        self.score = self.board.score(self.dead)
        return None

    def _ai(self, katago: KataGo | None) -> None:
        if self.phase != "play" or self.board.to_play == self.human:
            return
        color = self.board.to_play
        note = ""
        x = y = None
        used = self.engine
        if used == "katago" and katago is not None and katago.ready:
            try:
                x, y, note = katago.genmove(color)
            except Exception as exc:
                used = "builtin"
                self.engine = "builtin"
                self.message = f"KataGo 这一步失败，改用自对弈引擎。{exc}"
                x, y, note = choose_move(self.board, self.rank)
        else:
            if used == "katago":
                self.engine = "builtin"
            x, y, note = choose_move(self.board, self.rank)
        if note == "resign":
            self.phase = "over"
            winner = COLOR_NAME[self.human]
            self.score = {"winner": winner, "resigned": True, "black": 0, "white": 0, "margin": 0}
            self.message = "对方认输"
            return
        before = self.board.captures[color]
        err = self.board.play(x, y)
        if err:
            self.board.play(None, None)
            note = "停一手"
        else:
            taken = self.board.captures[color] - before
            if taken and not note:
                note = f"提掉 {taken} 子"
        if note:
            self.message = note
        if self.board.over and self.phase == "play":
            self.enter_scoring()

    def start(self, katago: KataGo | None) -> str | None:
        if self.engine == "katago" and katago is not None and katago.ready:
            try:
                katago.new_game(self.board.size, self.board.komi, self.rank)
            except Exception as exc:
                self.engine = "builtin"
                self.message = f"KataGo 没能开局，这一盘用自对弈引擎。{exc}"
        elif self.engine == "katago":
            self.engine = "builtin"
            self.message = "KataGo 还没就绪，这一盘用自对弈引擎。级别越高，它越少下错，但不是真实的高段。"
        if self.board.to_play != self.human:
            self._ai(katago)
        return None

    def move(self, x: int | None, y: int | None, katago: KataGo | None) -> str | None:
        if self.phase != "play":
            return "这一局现在不能落子"
        if self.board.to_play != self.human:
            return "还没轮到你"
        self.undo_stack.append(self.snapshot())
        before = self.board.captures[self.human]
        err = self.board.play(x, y)
        if err:
            self.undo_stack.pop()
            return err
        taken = self.board.captures[self.human] - before
        if self.engine == "katago" and katago is not None and katago.ready:
            try:
                katago.play_move(self.human, x, y)
            except Exception as exc:
                self.engine = "builtin"
                self.message = f"KataGo 没有跟上这步棋，之后改用自对弈引擎。{exc}"
        if taken:
            self.message = f"你提掉 {taken} 子"
        if self.board.over:
            self.enter_scoring()
            return None
        self._ai(katago)
        return None

    def undo(self, katago: KataGo | None) -> str | None:
        if not self.undo_stack:
            return "没有可悔的棋"
        target = self.undo_stack.pop()
        extra = len(self.board.moves) - len(target[0].moves)
        self.restore(target)
        if self.engine == "katago" and katago is not None and katago.ready and extra:
            try:
                katago.undo(extra)
            except Exception:
                try:
                    katago.sync(self.board, self.rank)
                except Exception as exc:
                    self.engine = "builtin"
                    self.message = f"悔棋后 KataGo 没有对齐，改用自对弈引擎。{exc}"
        return None

    def resign(self) -> None:
        self.phase = "over"
        winner = COLOR_NAME[opponent(self.human)]
        self.score = {"winner": winner, "resigned": True, "black": 0, "white": 0, "margin": 0}
        self.message = "你认输了"


class Practice:
    def __init__(self, problem_id: str):
        self.problem = by_id(problem_id)
        self.board = Board(self.problem["size"], 7.5)
        self.board.setup(self.problem["black"], self.problem["white"], BLACK)
        self.step = 0
        self.done = False
        self.success = False
        self.message = self.problem["intro"]
        self.log: list[str] = []
        self.history: list[tuple] = []

    def public(self) -> dict:
        return {
            "problemId": self.problem["id"],
            "title": self.problem["title"],
            "level": self.problem["level"],
            "category": self.problem["category"],
            "intro": self.problem["intro"],
            "size": self.board.size,
            "board": self.board.grid,
            "last": self.board.last,
            "done": self.done,
            "success": self.success,
            "message": self.message,
            "log": self.log,
            "toPlay": "B",
        }

    def _remember(self) -> None:
        self.history.append((self.board.clone(), self.step, list(self.log), self.done, self.success, self.message))

    def move(self, x: int, y: int) -> str | None:
        if self.done:
            return "这道题已经做完了"
        step = self.problem["solution"][self.step]
        self._remember()
        err = self.board.play(x, y)
        if err:
            self.history.pop()
            return err
        good = [tuple(pair) for pair in step["moves"]]
        if (x, y) not in good:
            self.board, self.step, self.log, self.done, self.success, self.message = self.history.pop()
            self.message = self.problem["fail"]
            return self.problem["fail"]
        self.log.append(step["note"])
        self.message = step["note"]
        reply = step.get("reply")
        if reply:
            reply_error = self.board.play(reply[0], reply[1])
            if not reply_error:
                note = step.get("reply_note") or "对方应了一手。"
                self.log.append(note)
                self.message = note
        self.step += 1
        if self.step >= len(self.problem["solution"]):
            self.done = True
            self.success = True
            self.message = self.problem["success"]
            self.log.append(self.problem["success"])
        return None

    def undo(self) -> str | None:
        if not self.history:
            return "已经是初始局面"
        self.board, self.step, self.log, self.done, self.success, self.message = self.history.pop()
        self.log = list(self.log)
        return None

    def hint(self) -> dict:
        if self.done:
            return {"message": "已经做完了"}
        step = self.problem["solution"][self.step]
        x, y = step["moves"][0]
        return {"x": x, "y": y, "text": step["note"]}

    def solve(self) -> None:
        while not self.done:
            step = self.problem["solution"][self.step]
            x, y = step["moves"][0]
            err = self.move(x, y)
            if err:
                self.message = err
                return
