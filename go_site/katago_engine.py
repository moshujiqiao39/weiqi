"""KataGo GTP。人类棋力模型按 18 级到 9 段切换。"""

from __future__ import annotations

try:
    import subprocess
except ImportError:
    subprocess = None
import threading
from pathlib import Path

from .engine import BLACK, WHITE, Board, from_gtp, to_gtp
from .ranks import katago_style

ROOT = Path(__file__).resolve().parent.parent
KATA_DIR = ROOT / "models" / "katago"
EXE = KATA_DIR / "katago.exe"
MODEL = ROOT / "models" / "b18c384nbt-humanv0.bin.gz"
CONFIG = KATA_DIR / "salon.cfg"


def model_ready() -> bool:
    return EXE.exists() and MODEL.exists()


def write_config() -> None:
    example = (KATA_DIR / "gtp_human5k_example.cfg").read_text(encoding="utf-8")
    example = example.replace("rules = japanese", "rules = chinese")
    example = example.replace("delayMoveScale = 2.0", "delayMoveScale = 0")
    example = example.replace("delayMoveMax = 10.0", "delayMoveMax = 0")
    example = example.replace("humanSLProfile = preaz_5k", "humanSLProfile = rank_10k")
    example = example.replace("logAllGTPCommunication = true", "logAllGTPCommunication = false")
    example = example.replace("logSearchInfo = true", "logSearchInfo = false")
    example = example.replace("logSearchInfoForChosenMove = false", "logSearchInfoForChosenMove = false")
    example = example.replace("numSearchThreads = 1", "numSearchThreads = 1")
    example = example.replace("maxVisits = 40", "maxVisits = 16")
    if "maxTime" not in example:
        example += "\nmaxTime = 6.0\n"
    example = example.replace("lagBuffer = 1.0", "lagBuffer = 0.0")
    CONFIG.write_text(example, encoding="utf-8")


class KataGo:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.ready = False
        self.error = ""
        self.log: list[str] = []
        self.size = 19
        self._stderr: threading.Thread | None = None

    def start(self) -> None:
        if self.ready:
            return
        if not model_ready():
            raise FileNotFoundError("还没有 KataGo 或人类棋力模型")
        write_config()
        self.proc = subprocess.Popen(
            [
                str(EXE),
                "gtp",
                "-model",
                str(MODEL),
                "-human-model",
                str(MODEL),
                "-config",
                str(CONFIG),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(KATA_DIR),
            bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._stderr = threading.Thread(target=self._drain, daemon=True)
        self._stderr.start()
        try:
            name = self._cmd("name", timeout=180)
        except Exception as exc:
            self.error = str(exc)
            self.close()
            raise
        if "KataGo" not in name and name.strip() == "":
            self.error = "KataGo 没有正常启动"
            self.close()
            raise RuntimeError(self.error)
        try:
            self._cmd("kata-set-rules chinese", timeout=30)
        except Exception:
            pass
        self.ready = True

    def _drain(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            self.log.append(line)
            self.log = self.log[-40:]

    def _cmd(self, text: str, timeout: float = 30) -> str:
        proc = self.proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("KataGo 没有启动")
        if proc.poll() is not None:
            self.ready = False
            tail = "；".join(self.log[-3:])
            raise RuntimeError(f"KataGo 已退出 {tail}")
        with self.lock:
            proc.stdin.write((text.strip() + "\n").encode("utf-8"))
            proc.stdin.flush()
            lines: list[str] = []
            holder: list[str] = []

            def read() -> None:
                assert proc.stdout is not None
                while True:
                    raw = proc.stdout.readline()
                    if not raw:
                        holder.append("__eof__")
                        return
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line == "" and lines:
                        return
                    if line == "":
                        continue
                    lines.append(line)

            worker = threading.Thread(target=read, daemon=True)
            worker.start()
            worker.join(timeout)
            if worker.is_alive():
                self.ready = False
                self.error = f"KataGo 超时：{text}"
                try:
                    proc.kill()
                except Exception:
                    pass
                raise TimeoutError(self.error)
            if holder:
                tail = "；".join(self.log[-4:])
                raise RuntimeError(f"KataGo 中断 {tail}")
        body = "\n".join(lines).strip()
        if body.startswith("?"):
            raise RuntimeError(body[1:].strip() or "KataGo 拒绝了这个指令")
        if body.startswith("="):
            return body[1:].strip()
        return body

    def apply_rank(self, rank: str) -> None:
        style = katago_style(rank)
        kyu = style["profile"].endswith("k")
        lam = style["pikl_lambda"]
        lam_text = str(int(lam)) if lam >= 1000 else str(lam)
        values = {
            "humanSLProfile": style["profile"],
            "maxVisits": int(style["max_visits"]),
            "maxTime": style["max_time"],
            "chosenMoveTemperature": style["temperature"],
            "chosenMoveTemperatureEarly": min(1.1, style["temperature"] + 0.1),
            "chosenMoveTemperatureOnlyBelowProb": 0.01 if kyu else 1,
            "humanSLChosenMoveProp": 1,
            "humanSLChosenMovePiklLambda": lam_text,
            "humanSLRootExploreProbWeightless": 0.0 if kyu else 0.5,
        }
        for key, value in values.items():
            try:
                self._cmd(f"kata-set-param {key} {value}", timeout=15)
            except Exception:
                continue

    def new_game(self, size: int, komi: float, rank: str) -> None:
        self._cmd(f"boardsize {size}", timeout=60)
        self.size = size
        self._cmd("clear_board", timeout=60)
        self._cmd(f"komi {komi}", timeout=15)
        self.apply_rank(rank)

    def play_move(self, color: int, x: int | None, y: int | None) -> None:
        who = "B" if color == BLACK else "W"
        self._cmd(f"play {who} {to_gtp(x, y, self.size)}", timeout=20)

    def genmove(self, color: int) -> tuple[int | None, int | None, str]:
        who = "B" if color == BLACK else "W"
        answer = self._cmd(f"genmove {who}", timeout=40).split()[0]
        if answer.lower() == "resign":
            return None, None, "resign"
        if answer.lower() == "pass":
            return None, None, "停一手"
        x, y = from_gtp(answer, self.size)
        return x, y, ""

    def undo(self, count: int) -> None:
        for _ in range(count):
            self._cmd("undo", timeout=20)

    def sync(self, board: Board, rank: str) -> None:
        """把整盘棋重放进 KataGo，用来在悔棋后对齐。"""
        self.new_game(board.size, board.komi, rank)
        for color, x, y in board.moves:
            self.play_move(color, x, y)

    def close(self) -> None:
        self.ready = False
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                proc.stdin.write(b"quit\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        self.proc = None
