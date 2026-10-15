"""本地对局网站。"""

from __future__ import annotations

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .ai import play_training_game, trained_games
from .katago_engine import KataGo, model_ready
from .play import Game, Practice
from .problems import summary
from .ranks import RANKS

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

KATA = KataGo()
KATA_STATE = {"status": "missing", "detail": ""}
GAMES: dict[str, Game] = {}
PRACTICE: dict[str, Practice] = {}
TRAIN = {"running": False, "done": 0, "total": 0, "log": [], "error": ""}
LOCK = threading.Lock()
SEQ = 0


def next_id(prefix: str) -> str:
    global SEQ
    with LOCK:
        SEQ += 1
        return f"{prefix}{SEQ}"


def boot_katago() -> None:
    if not model_ready():
        KATA_STATE["status"] = "missing"
        KATA_STATE["detail"] = "没有找到 KataGo 或人类棋力模型"
        return
    KATA_STATE["status"] = "loading"
    KATA_STATE["detail"] = "正在加载人类棋力模型，第一次大约要一分钟"
    try:
        KATA.start()
    except Exception as exc:
        KATA_STATE["status"] = "error"
        KATA_STATE["detail"] = str(exc)
        return
    KATA_STATE["status"] = "ready"
    KATA_STATE["detail"] = "KataGo 人类棋力模型已就绪"


def status() -> dict:
    return {
        "ranks": RANKS,
        "katago": KATA_STATE["status"],
        "detail": KATA_STATE["detail"],
        "trainedGames": trained_games(),
        "training": {
            "running": TRAIN["running"],
            "done": TRAIN["done"],
            "total": TRAIN["total"],
            "log": TRAIN["log"],
            "error": TRAIN["error"],
        },
    }


def start_training(games: int) -> dict:
    if TRAIN["running"]:
        return {"ok": False, "error": "训练已经在进行"}
    games = max(1, min(30, int(games)))

    def work() -> None:
        TRAIN["running"] = True
        TRAIN["done"] = 0
        TRAIN["total"] = games
        TRAIN["error"] = ""
        TRAIN["log"] = ["开始 9 路自对弈"]
        try:
            for i in range(games):
                result = play_training_game()
                TRAIN["done"] = i + 1
                label = "黑胜" if result > 0 else "白胜" if result < 0 else "和棋"
                TRAIN["log"].append(f"第 {i + 1} 局：{label}")
                TRAIN["log"] = TRAIN["log"][-20:]
            TRAIN["log"].append("权重已保存，之后的自对弈对局会用上")
        except Exception as exc:
            TRAIN["error"] = str(exc)
            TRAIN["log"].append(f"训练中断：{exc}")
        finally:
            TRAIN["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "games": games}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._json(404, {"error": "没有这个文件"})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._file(WEB / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api/boot" or path == "/api/train":
            self._json(200, status())
            return
        if path == "/api/problems":
            self._json(200, {"problems": summary()})
            return
        if path.startswith("/static/"):
            name = path[len("/static/") :]
            self._asset(name)
            return
        if path in ("/style.css", "/app.js"):
            self._asset(path[1:])
            return
        if path.startswith("/go_site/") and path.endswith(".py"):
            name = path[len("/go_site/") :]
            if not name or "/" in name or ".." in name:
                self._json(404, {"error": "没有这个文件"})
                return
            self._file(ROOT / "go_site" / name, "text/plain; charset=utf-8")
            return
        self._json(404, {"error": "没有这个地址"})

    def _asset(self, name: str) -> None:
        if not name or "/" in name or ".." in name:
            self._json(404, {"error": "没有这个文件"})
            return
        if name.endswith(".css"):
            kind = "text/css; charset=utf-8"
        elif name.endswith(".js"):
            kind = "text/javascript; charset=utf-8"
        else:
            kind = "application/octet-stream"
        self._file(WEB / name, kind)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._body()
        except json.JSONDecodeError:
            self._json(400, {"error": "请求不是合法的 JSON"})
            return
        try:
            if path == "/api/games":
                self._new_game(body)
            elif path.startswith("/api/games/") and path.endswith("/move"):
                self._game_move(path.split("/")[3], body)
            elif path.startswith("/api/games/") and path.endswith("/undo"):
                self._game_undo(path.split("/")[3])
            elif path.startswith("/api/games/") and path.endswith("/resign"):
                self._game_resign(path.split("/")[3])
            elif path.startswith("/api/games/") and path.endswith("/dead"):
                self._game_dead(path.split("/")[3], body)
            elif path.startswith("/api/games/") and path.endswith("/finish"):
                self._game_finish(path.split("/")[3])
            elif path == "/api/practice":
                self._new_practice(body)
            elif path.startswith("/api/practice/") and path.endswith("/move"):
                self._practice_move(path.split("/")[3], body)
            elif path.startswith("/api/practice/") and path.endswith("/undo"):
                self._practice_undo(path.split("/")[3])
            elif path.startswith("/api/practice/") and path.endswith("/hint"):
                self._practice_hint(path.split("/")[3])
            elif path.startswith("/api/practice/") and path.endswith("/solve"):
                self._practice_solve(path.split("/")[3])
            elif path == "/api/train":
                self._json(200, start_training(body.get("games") or 10))
            else:
                self._json(404, {"error": "没有这个地址"})
        except KeyError:
            self._json(404, {"error": "这盘棋或这道题不存在，请重新开始"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _new_game(self, body: dict) -> None:
        size = int(body.get("size") or 19)
        if size not in (9, 13, 19):
            self._json(400, {"error": "对局棋盘只开 9、13、19 路"})
            return
        rank = body.get("rank") or "8级"
        if rank not in RANKS:
            self._json(400, {"error": "没有这个段位"})
            return
        human = body.get("color") or "B"
        if human not in ("B", "W"):
            self._json(400, {"error": "执子颜色只能是黑或白"})
            return
        want = body.get("engine") or "auto"
        engine = "builtin" if want == "builtin" else "katago"
        if engine == "katago" and KATA_STATE["status"] != "ready":
            engine = "builtin"
        game = Game(size, rank, human, engine)
        if engine == "builtin" and want != "builtin":
            if KATA_STATE["status"] == "loading":
                game.message = "棋力模型还在加载，这一盘先用自对弈引擎。"
            elif KATA_STATE["status"] != "ready":
                game.message = "KataGo 不可用，这一盘用自对弈引擎。级别越高越少失误，高段棋力要等模型就绪。"
        game.start(KATA if engine == "katago" else None)
        gid = next_id("g")
        GAMES[gid] = game
        self._json(200, {"ok": True, "id": gid, "state": game.public()})

    def _game(self, gid: str) -> Game:
        game = GAMES.get(gid)
        if game is None:
            raise KeyError(gid)
        return game

    def _game_move(self, gid: str, body: dict) -> None:
        game = self._game(gid)
        if body.get("pass"):
            err = game.move(None, None, KATA if game.engine == "katago" else None)
        else:
            err = game.move(int(body["x"]), int(body["y"]), KATA if game.engine == "katago" else None)
        self._json(200, {"ok": err is None, "error": err, "id": gid, "state": game.public()})

    def _game_undo(self, gid: str) -> None:
        game = self._game(gid)
        err = game.undo(KATA if game.engine == "katago" else None)
        self._json(200, {"ok": err is None, "error": err, "state": game.public()})

    def _game_resign(self, gid: str) -> None:
        game = self._game(gid)
        game.resign()
        self._json(200, {"ok": True, "state": game.public()})

    def _game_dead(self, gid: str, body: dict) -> None:
        game = self._game(gid)
        err = game.toggle_dead(int(body["x"]), int(body["y"]))
        self._json(200, {"ok": err is None, "error": err, "state": game.public()})

    def _game_finish(self, gid: str) -> None:
        game = self._game(gid)
        if game.phase != "scoring":
            self._json(200, {"ok": False, "error": "还没到数子", "state": game.public()})
            return
        game.finish()
        self._json(200, {"ok": True, "state": game.public()})

    def _new_practice(self, body: dict) -> None:
        practice = Practice(body["id"])
        pid = next_id("p")
        PRACTICE[pid] = practice
        self._json(200, {"ok": True, "id": pid, "state": practice.public()})

    def _practice(self, pid: str) -> Practice:
        item = PRACTICE.get(pid)
        if item is None:
            raise KeyError(pid)
        return item

    def _practice_move(self, pid: str, body: dict) -> None:
        item = self._practice(pid)
        err = item.move(int(body["x"]), int(body["y"]))
        self._json(200, {"ok": err is None, "error": err, "id": pid, "state": item.public()})

    def _practice_undo(self, pid: str) -> None:
        item = self._practice(pid)
        err = item.undo()
        self._json(200, {"ok": err is None, "error": err, "state": item.public()})

    def _practice_hint(self, pid: str) -> None:
        item = self._practice(pid)
        hint = item.hint()
        self._json(200, {"ok": True, "hint": hint, "state": item.public()})

    def _practice_solve(self, pid: str) -> None:
        item = self._practice(pid)
        item.solve()
        self._json(200, {"ok": True, "state": item.public()})


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    threading.Thread(target=boot_katago, daemon=True).start()
    server = None
    port = 8765
    for candidate in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("8765 到 8775 端口都被占用了")
    url = f"http://127.0.0.1:{port}"
    print(f"围棋对局已打开：{url}")
    print("关掉这个窗口就会停止网站。")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止")
    finally:
        KATA.close()
        server.server_close()
