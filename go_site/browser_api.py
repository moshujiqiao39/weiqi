"""浏览器里直接调用的接口。没有 KataGo 进程，段位由自对弈模型的失误率拉开。"""

from __future__ import annotations

import json

from .ai import play_training_game, save_model, trained_games
from .ai import WEIGHT_PATH, load_model
from .play import Game, Practice
from .problems import summary
from .ranks import RANKS

WEIGHT_PATH.parent.mkdir(parents=True, exist_ok=True)

GAMES: dict[str, Game] = {}
PRACTICE: dict[str, Practice] = {}
SEQ = 0
TRAIN = {"running": False, "done": 0, "total": 0, "log": [], "error": ""}


def export_model() -> str:
    save_model()
    return WEIGHT_PATH.read_text(encoding="utf-8")


def import_model(text: str) -> None:
    if not text:
        return
    WEIGHT_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEIGHT_PATH.write_text(text, encoding="utf-8")
    load_model()


def _next(prefix: str) -> str:
    global SEQ
    SEQ += 1
    return f"{prefix}{SEQ}"


def _status() -> dict:
    return {
        "ranks": RANKS,
        "katago": "browser",
        "detail": "这一页在浏览器里运行，电脑关机后仍能打开。自对弈会记住在这台浏览器里。18级到9段的 KataGo 模型要在自己的电脑上运行。",
        "trainedGames": trained_games(),
        "training": {
            "running": TRAIN["running"],
            "done": TRAIN["done"],
            "total": TRAIN["total"],
            "log": TRAIN["log"],
            "error": TRAIN["error"],
        },
    }


def _route(method: str, path: str, body: dict) -> tuple[int, dict]:
    if method == "GET" and path in ("/api/boot", "/api/train"):
        return 200, _status()
    if method == "GET" and path == "/api/problems":
        return 200, {"problems": summary()}
    if method == "POST" and path == "/api/games":
        return _new_game(body)
    if method == "POST" and path.startswith("/api/games/") and path.endswith("/move"):
        return _game_move(path.split("/")[3], body)
    if method == "POST" and path.startswith("/api/games/") and path.endswith("/undo"):
        game = _game(path.split("/")[3])
        err = game.undo(None)
        return 200, {"ok": err is None, "error": err, "state": game.public()}
    if method == "POST" and path.startswith("/api/games/") and path.endswith("/resign"):
        game = _game(path.split("/")[3])
        game.resign()
        return 200, {"ok": True, "state": game.public()}
    if method == "POST" and path.startswith("/api/games/") and path.endswith("/dead"):
        game = _game(path.split("/")[3])
        err = game.toggle_dead(int(body["x"]), int(body["y"]))
        return 200, {"ok": err is None, "error": err, "state": game.public()}
    if method == "POST" and path.startswith("/api/games/") and path.endswith("/finish"):
        game = _game(path.split("/")[3])
        if game.phase != "scoring":
            return 200, {"ok": False, "error": "还没到数子", "state": game.public()}
        game.finish()
        return 200, {"ok": True, "state": game.public()}
    if method == "POST" and path == "/api/practice":
        practice = Practice(body["id"])
        pid = _next("p")
        PRACTICE[pid] = practice
        return 200, {"ok": True, "id": pid, "state": practice.public()}
    if method == "POST" and path.startswith("/api/practice/") and path.endswith("/move"):
        item = _practice(path.split("/")[3])
        err = item.move(int(body["x"]), int(body["y"]))
        return 200, {"ok": err is None, "error": err, "id": path.split("/")[3], "state": item.public()}
    if method == "POST" and path.startswith("/api/practice/") and path.endswith("/undo"):
        item = _practice(path.split("/")[3])
        err = item.undo()
        return 200, {"ok": err is None, "error": err, "state": item.public()}
    if method == "POST" and path.startswith("/api/practice/") and path.endswith("/hint"):
        item = _practice(path.split("/")[3])
        return 200, {"ok": True, "hint": item.hint(), "state": item.public()}
    if method == "POST" and path.startswith("/api/practice/") and path.endswith("/solve"):
        item = _practice(path.split("/")[3])
        item.solve()
        return 200, {"ok": True, "state": item.public()}
    if method == "POST" and path == "/api/train/step":
        return 200, _train_step()
    return 404, {"error": "没有这个地址"}


def _game(gid: str) -> Game:
    game = GAMES.get(gid)
    if game is None:
        raise KeyError(gid)
    return game


def _practice(pid: str) -> Practice:
    item = PRACTICE.get(pid)
    if item is None:
        raise KeyError(pid)
    return item


def _new_game(body: dict) -> tuple[int, dict]:
    size = int(body.get("size") or 19)
    if size not in (9, 13, 19):
        return 400, {"error": "对局棋盘只开 9、13、19 路"}
    rank = body.get("rank") or "8级"
    if rank not in RANKS:
        return 400, {"error": "没有这个段位"}
    human = body.get("color") or "B"
    if human not in ("B", "W"):
        return 400, {"error": "执子颜色只能是黑或白"}
    game = Game(size, rank, human, "builtin")
    game.message = "在线对局使用自对弈模型。级别越高，它越少下错。"
    game.start(None)
    gid = _next("g")
    GAMES[gid] = game
    return 200, {"ok": True, "id": gid, "state": game.public()}


def _game_move(gid: str, body: dict) -> tuple[int, dict]:
    game = _game(gid)
    if body.get("pass"):
        err = game.move(None, None, None)
    else:
        err = game.move(int(body["x"]), int(body["y"]), None)
    return 200, {"ok": err is None, "error": err, "id": gid, "state": game.public()}


def _train_step() -> dict:
    result = play_training_game()
    TRAIN["done"] = trained_games()
    TRAIN["total"] = max(TRAIN["total"], TRAIN["done"])
    label = "黑胜" if result > 0 else "白胜" if result < 0 else "和棋"
    TRAIN["log"].append(f"第 {trained_games()} 局：{label}")
    TRAIN["log"] = TRAIN["log"][-20:]
    return _status()


def handle(method: str, path: str, body_json: str) -> str:
    try:
        body = json.loads(body_json or "{}")
        status, payload = _route(method, path, body)
    except KeyError:
        status, payload = 404, {"error": "这盘棋或这道题不存在，请重新开始"}
    except Exception as exc:
        status, payload = 500, {"error": str(exc)}
    return json.dumps({"status": status, "body": payload, "model": export_model()}, ensure_ascii=False)
