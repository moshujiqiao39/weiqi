const COLS = "ABCDEFGHJKLMNOPQRST";
const state = {
  view: "play",
  boot: null,
  form: { rank: "8级", color: "B", size: 19, engine: "auto" },
  game: null,
  gameId: null,
  practice: null,
  practiceId: null,
  problems: [],
  hint: null,
  thinking: false,
  hover: null,
};

let backend = "http";
let pyHandle = null;

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const panel = document.getElementById("panel");
const banner = document.getElementById("banner");
const engineEl = document.getElementById("engine");

function coordName(x, y, size) {
  if (x == null || y == null) return "停一手";
  return COLS[x] + (size - y);
}

async function api(path, options) {
  if (backend === "py") {
    const body = options && options.body ? JSON.parse(options.body) : {};
    const method = (options && options.method) || "GET";
    const raw = pyHandle(method, path, JSON.stringify(body));
    const text = typeof raw === "string" ? raw : String(raw);
    const wrapped = JSON.parse(text);
    if (wrapped.model) localStorage.setItem("weiqi-rl", wrapped.model);
    if (wrapped.status >= 400) throw new Error((wrapped.body && wrapped.body.error) || "请求失败");
    return wrapped.body;
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function setBanner(text, kind) {
  banner.textContent = text || "";
  banner.className = "banner" + (kind ? " " + kind : "");
}

function stars(size) {
  if (size === 19) return [3, 9, 15].flatMap((x) => [3, 9, 15].map((y) => [x, y]));
  if (size === 13) return [3, 6, 9].flatMap((x) => [3, 6, 9].map((y) => [x, y]));
  if (size === 9) return [[2, 2], [2, 6], [4, 4], [6, 2], [6, 6]];
  return [];
}

function metrics() {
  const css = canvas.clientWidth || 640;
  const dpr = window.devicePixelRatio || 1;
  const boardSize = currentBoard().size;
  const pad = Math.max(26, css * 0.075);
  const grid = (css - pad * 2) / (boardSize - 1);
  return { css, dpr, pad, grid, boardSize };
}

function currentBoard() {
  if (state.view === "play" && state.game) return { size: state.game.size, grid: state.game.board, last: state.game.last, dead: state.game.dead };
  if ((state.view === "life" || state.view === "tesuji") && state.practice) {
    return { size: state.practice.size, grid: state.practice.board, last: state.practice.last, dead: [] };
  }
  return { size: 19, grid: Array(361).fill(0), last: null, dead: [] };
}

function draw() {
  const board = currentBoard();
  const { css, dpr, pad, grid, boardSize } = metrics();
  canvas.width = Math.round(css * dpr);
  canvas.height = Math.round(css * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const wood = ctx.createLinearGradient(0, 0, css, css);
  wood.addColorStop(0, "#f2c778");
  wood.addColorStop(0.45, "#e3b15c");
  wood.addColorStop(1, "#d09a42");
  ctx.fillStyle = wood;
  ctx.fillRect(0, 0, css, css);
  ctx.strokeStyle = "rgba(120, 72, 24, 0.08)";
  for (let i = 0; i < 18; i++) {
    ctx.beginPath();
    ctx.moveTo(0, (css / 18) * i);
    ctx.lineTo(css, (css / 18) * i + 8);
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(48, 28, 12, 0.86)";
  ctx.lineWidth = 1.2;
  for (let i = 0; i < boardSize; i++) {
    const p = pad + i * grid;
    ctx.beginPath();
    ctx.moveTo(pad, p);
    ctx.lineTo(pad + (boardSize - 1) * grid, p);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(p, pad);
    ctx.lineTo(p, pad + (boardSize - 1) * grid);
    ctx.stroke();
  }
  ctx.fillStyle = "rgba(48, 28, 12, 0.9)";
  stars(boardSize).forEach(([x, y]) => {
    ctx.beginPath();
    ctx.arc(pad + x * grid, pad + y * grid, Math.max(2.5, grid * 0.08), 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.fillStyle = "rgba(70, 42, 16, 0.72)";
  ctx.font = `${Math.max(11, grid * 0.34)}px "Microsoft YaHei", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let i = 0; i < boardSize; i++) {
    ctx.fillText(COLS[i], pad + i * grid, pad * 0.42);
    ctx.fillText(String(boardSize - i), pad * 0.38, pad + i * grid);
  }
  const dead = new Set((board.dead || []).map(([x, y]) => y * boardSize + x));
  for (let y = 0; y < boardSize; y++) {
    for (let x = 0; x < boardSize; x++) {
      const v = board.grid[y * boardSize + x];
      if (!v) continue;
      drawStone(pad + x * grid, pad + y * grid, grid * 0.47, v, dead.has(y * boardSize + x));
    }
  }
  if (board.last) {
    const [x, y] = board.last;
    const v = board.grid[y * boardSize + x];
    ctx.fillStyle = v === 1 ? "#f4d7a2" : "#b6402c";
    ctx.beginPath();
    ctx.arc(pad + x * grid, pad + y * grid, grid * 0.16, 0, Math.PI * 2);
    ctx.fill();
  }
  if (state.hint) {
    ctx.strokeStyle = "#b6402c";
    ctx.lineWidth = 2;
    const x = pad + state.hint.x * grid;
    const y = pad + state.hint.y * grid;
    const r = grid * 0.22;
    ctx.beginPath();
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y + r * 0.7);
    ctx.lineTo(x - r, y + r * 0.7);
    ctx.closePath();
    ctx.stroke();
  }
  if (state.hover && canPlay()) {
    const { x, y } = state.hover;
    if (board.grid[y * boardSize + x] === 0) {
      ctx.globalAlpha = 0.45;
      const color = state.view === "play" ? (state.game.human === "B" ? 1 : 2) : 1;
      drawStone(pad + x * grid, pad + y * grid, grid * 0.47, color, false);
      ctx.globalAlpha = 1;
    }
  }
}

function drawStone(x, y, r, color, dead) {
  ctx.save();
  if (dead) ctx.globalAlpha = 0.35;
  ctx.beginPath();
  ctx.arc(x + 1.2, y + 2, r, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(40, 24, 8, 0.28)";
  ctx.fill();
  const g = ctx.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.2, x, y, r);
  if (color === 1) {
    g.addColorStop(0, "#5c5c5c");
    g.addColorStop(1, "#161616");
  } else {
    g.addColorStop(0, "#ffffff");
    g.addColorStop(1, "#d9d1c3");
  }
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = g;
  ctx.fill();
  if (dead) {
    ctx.globalAlpha = 0.9;
    ctx.strokeStyle = "#b6402c";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x - r * 0.4, y - r * 0.4);
    ctx.lineTo(x + r * 0.4, y + r * 0.4);
    ctx.moveTo(x + r * 0.4, y - r * 0.4);
    ctx.lineTo(x - r * 0.4, y + r * 0.4);
    ctx.stroke();
  }
  ctx.restore();
}

function eventPoint(event) {
  const rect = canvas.getBoundingClientRect();
  const { pad, grid, boardSize } = metrics();
  const x = Math.round((event.clientX - rect.left - pad) / grid);
  const y = Math.round((event.clientY - rect.top - pad) / grid);
  if (x < 0 || y < 0 || x >= boardSize || y >= boardSize) return null;
  return { x, y };
}

function canPlay() {
  if (state.thinking) return false;
  if (state.view === "play") return state.game && state.game.phase === "play" && state.game.yourTurn;
  if (state.view === "life" || state.view === "tesuji") return state.practice && !state.practice.done;
  return false;
}

canvas.addEventListener("mousemove", (event) => {
  state.hover = eventPoint(event);
  draw();
});
canvas.addEventListener("mouseleave", () => {
  state.hover = null;
  draw();
});
canvas.addEventListener("click", async (event) => {
  const point = eventPoint(event);
  if (!point) return;
  if (state.view === "play" && state.game && state.game.phase === "scoring") {
    await act(`/api/games/${state.gameId}/dead`, point);
    return;
  }
  if (!canPlay()) return;
  state.hint = null;
  if (state.view === "play") await act(`/api/games/${state.gameId}/move`, point);
  else await act(`/api/practice/${state.practiceId}/move`, point);
});

async function act(path, body) {
  state.thinking = true;
  draw();
  render();
  try {
    const data = await post(path, body);
    if (path.startsWith("/api/games/")) {
      state.game = data.state;
      const idle = data.state.yourTurn ? "轮到你了。" : "";
      setBanner(data.error || data.state.message || idle, data.error ? "bad" : data.state.phase === "over" ? "good" : "");
    } else {
      state.practice = data.state;
      setBanner(data.state.message, data.state.success ? "good" : data.error ? "bad" : "");
    }
  } catch (error) {
    setBanner(error.message, "bad");
  } finally {
    state.thinking = false;
    render();
    draw();
  }
}

function render() {
  if (state.view === "play") renderPlay();
  else if (state.view === "train") renderTrain();
  else renderProblems();
}

function renderPlay() {
  const game = state.game;
  if (!game) {
    const ranks = (state.boot && state.boot.ranks) || [];
    panel.innerHTML = `
      <h2>对局</h2>
      <p class="sub">选一个级别。模型就绪时，黑白都按这个级别的人类着法来下；还在加载时，先用自对弈引擎。</p>
      <label>段位</label>
      <select id="rank">${ranks.map((rank) => `<option ${rank === state.form.rank ? "selected" : ""}>${rank}</option>`).join("")}</select>
      <label>我方</label>
      <div class="choice">
        <button type="button" data-act="color" data-value="B" class="${state.form.color === "B" ? "on" : ""}">执黑</button>
        <button type="button" data-act="color" data-value="W" class="${state.form.color === "W" ? "on" : ""}">执白</button>
      </div>
      <label>棋盘</label>
      <div class="choice">
        ${[19, 13, 9].map((size) => `<button type="button" data-act="size" data-value="${size}" class="${state.form.size === size ? "on" : ""}">${size}路</button>`).join("")}
      </div>
      <label>引擎</label>
      <div class="choice">
        <button type="button" data-act="engine" data-value="auto" class="${state.form.engine === "auto" ? "on" : ""}">按段位</button>
        <button type="button" data-act="engine" data-value="builtin" class="${state.form.engine === "builtin" ? "on" : ""}">自对弈</button>
      </div>
      <button class="primary" id="start" type="button" ${state.thinking ? "disabled" : ""}>开始对局</button>`;
    return;
  }
  const who = game.human === "B" ? "黑" : "白";
  const engine = game.engine === "katago" ? "KataGo 人类棋力" : "自对弈模型";
  panel.innerHTML = `
    <h2>${game.rank}</h2>
    <p class="sub">你执${who} · ${game.size} 路 · ${engine}</p>
    <div class="stats">
      <div class="stat">黑提子<b>${game.captures.B}</b></div>
      <div class="stat">白提子<b>${game.captures.W}</b></div>
    </div>
    <div class="actions">
      <button type="button" data-act="pass" ${game.phase === "play" && game.yourTurn && !state.thinking ? "" : "disabled"}>停一手</button>
      <button type="button" data-act="undo" ${state.thinking ? "disabled" : ""}>悔棋</button>
      <button type="button" data-act="resign" ${game.phase === "over" ? "disabled" : ""}>认输</button>
      ${game.phase === "scoring" ? '<button type="button" data-act="finish">确认数子</button>' : ""}
      <button type="button" data-act="reset">新对局</button>
    </div>
    ${game.score ? `<p class="sub">${game.score.text}</p>` : ""}
    <ol class="moves">${game.moves.map((move) => `<li><span>${move.n}. ${move.color === "B" ? "黑" : "白"}</span><span>${move.coord}</span></li>`).join("")}</ol>`;
}

function renderProblems() {
  const category = state.view === "life" ? "死活" : "手筋";
  if (!state.practice || state.practice.category !== category) {
    const list = state.problems.filter((item) => item.category === category);
    panel.innerHTML = `
      <h2>${category}</h2>
      <p class="sub">${category === "死活" ? "黑先做活，或把白棋杀死。" : "黑先，走出吃子、连接或征子。"} 点错可以重来。</p>
      <div class="problem-list">${list.map((item) => `<button type="button" data-act="open" data-id="${item.id}"><span>${item.title}</span><span class="level">${item.level}</span></button>`).join("")}</div>`;
    return;
  }
  const item = state.practice;
  panel.innerHTML = `
    <h2>${item.title}</h2>
    <p class="sub">${item.level} · 黑先 · ${item.size} 路</p>
    <p class="sub">${item.intro}</p>
    <div class="actions">
      <button type="button" data-act="hint" ${item.done ? "disabled" : ""}>提示</button>
      <button type="button" data-act="pundo">重来一步</button>
      <button type="button" data-act="solve">看正解</button>
      <button type="button" data-act="plist">题目列表</button>
    </div>
    <ol class="log">${item.log.map((line) => `<li>${line}</li>`).join("")}</ol>`;
}

function renderTrain() {
  const train = (state.boot && state.boot.training) || { running: false, log: [], done: 0, total: 0 };
  const games = state.boot ? state.boot.trainedGames : 0;
  const online = state.boot && state.boot.katago === "browser";
  const explain = online
    ? `在网页里自己跟自己下，用胜负改正着法。已经训练 ${games} 局，记在这台浏览器里，关机再打开还在。它会少送吃，但练不成 9 段。真实的 18 级到 9 段要在自己电脑上运行。`
    : `9 路棋盘上自己跟自己下，用胜负改正着法。已经训练 ${games} 局。19 路、从 18 级到 9 段的分档用 KataGo 的人类棋力模型。`;
  panel.innerHTML = `
    <h2>自对弈</h2>
    <p class="sub">${explain}</p>
    <button class="primary" type="button" data-act="train" ${train.running || state.thinking ? "disabled" : ""}>${train.running || state.thinking ? `正在下 ${train.done || 0}/${train.total || 10}` : "训练 10 局"}</button>
    <div class="train-log">${(train.log || []).join("\n") || "还没有开始。"}</div>`;
}

panel.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const actName = button.dataset.act;
  if (button.id === "start") {
    state.thinking = true;
    render();
    try {
      const data = await post("/api/games", state.form);
      state.game = data.state;
      state.gameId = data.id;
      setBanner(data.state.message || `对局开始，你执${state.form.color === "B" ? "黑" : "白"}。`, "");
    } catch (error) {
      setBanner(error.message, "bad");
    } finally {
      state.thinking = false;
      render();
      draw();
    }
    return;
  }
  if (actName === "color") state.form.color = button.dataset.value;
  if (actName === "size") state.form.size = Number(button.dataset.value);
  if (actName === "engine") state.form.engine = button.dataset.value;
  if (actName === "color" || actName === "size" || actName === "engine") {
    render();
    return;
  }
  if (actName === "reset") {
    state.game = null;
    state.gameId = null;
    setBanner("选段位，开始一盘。", "");
    render();
    draw();
    return;
  }
  if (actName === "pass") return act(`/api/games/${state.gameId}/move`, { pass: true });
  if (actName === "undo") return act(`/api/games/${state.gameId}/undo`);
  if (actName === "resign") return act(`/api/games/${state.gameId}/resign`);
  if (actName === "finish") return act(`/api/games/${state.gameId}/finish`);
  if (actName === "open") {
    state.hint = null;
    state.thinking = true;
    try {
      const data = await post("/api/practice", { id: button.dataset.id });
      state.practice = data.state;
      state.practiceId = data.id;
      setBanner(data.state.intro, "");
    } catch (error) {
      setBanner(error.message, "bad");
    } finally {
      state.thinking = false;
      render();
      draw();
    }
    return;
  }
  if (actName === "plist") {
    state.practice = null;
    state.hint = null;
    setBanner(state.view === "life" ? "选一道死活。" : "选一道手筋。", "");
    render();
    draw();
    return;
  }
  if (actName === "hint") {
    const data = await post(`/api/practice/${state.practiceId}/hint`);
    state.hint = data.hint;
    setBanner(data.hint.text || "看棋盘上的三角。", "");
    draw();
    return;
  }
  if (actName === "pundo") return act(`/api/practice/${state.practiceId}/undo`);
  if (actName === "solve") {
    state.hint = null;
    return act(`/api/practice/${state.practiceId}/solve`);
  }
  if (actName === "train") {
    if (backend === "py") {
      state.thinking = true;
      render();
      try {
        for (let i = 0; i < 10; i++) {
          state.boot = await post("/api/train/step", {});
          render();
        }
        setBanner("这 10 局已经记在浏览器里。", "good");
      } catch (error) {
        setBanner(error.message, "bad");
      } finally {
        state.thinking = false;
        render();
      }
    } else {
      await post("/api/train", { games: 10 });
      await refreshBoot();
    }
  }
});

panel.addEventListener("change", (event) => {
  if (event.target.id === "rank") state.form.rank = event.target.value;
});

document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((item) => item.classList.remove("on"));
    button.classList.add("on");
    state.view = button.dataset.view;
    state.hint = null;
    if (state.view === "life") setBanner("选一道死活。", "");
    if (state.view === "tesuji") setBanner("选一道手筋。", "");
    if (state.view === "play") setBanner(state.game ? state.game.message : "选段位，开始一盘。", "");
    if (state.view === "train") setBanner("自对弈会更新内置引擎的权重。", "");
    render();
    draw();
  });
});

async function refreshBoot() {
  try {
    state.boot = await api("/api/boot");
    const chip = engineEl;
    if (state.boot.katago === "ready") {
      chip.textContent = "KataGo 已就绪 · 18级到9段";
      chip.className = "engine ready";
    } else if (state.boot.katago === "loading") {
      chip.textContent = "正在加载棋力模型";
      chip.className = "engine";
    } else if (state.boot.katago === "browser") {
      chip.textContent = "在线对局 · 关机也能打开";
      chip.className = "engine ready";
      chip.title = state.boot.detail || "";
    } else {
      chip.textContent = "自对弈引擎";
      chip.className = "engine bad";
      chip.title = state.boot.detail || "";
    }
    if (state.view === "train") render();
  } catch (error) {
    engineEl.textContent = "网站没有连上";
    engineEl.className = "engine bad";
  }
}

new ResizeObserver(() => draw()).observe(canvas.parentElement);

async function bootBrowser() {
  engineEl.textContent = "正在把棋盘装进浏览器";
  setBanner("第一次打开要加载一会儿。加载完就可以对局、做题、自对弈。", "");
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";
    script.onload = resolve;
    script.onerror = () => reject(new Error("在线棋盘没有加载成功"));
    document.head.appendChild(script);
  });
  const pyodide = await loadPyodide();
  const names = ["__init__.py", "engine.py", "ranks.py", "ai.py", "problems.py", "play.py", "katago_engine.py", "browser_api.py"];
  pyodide.FS.mkdirTree("/go_site");
  for (const name of names) {
    const response = await fetch(new URL("go_site/" + name, document.baseURI));
    if (!response.ok) throw new Error("缺少 " + name);
    pyodide.FS.writeFile("/go_site/" + name, await response.text());
  }
  await pyodide.runPythonAsync("import sys\nsys.path.insert(0, '/')\nfrom go_site.browser_api import handle, import_model\n");
  pyHandle = pyodide.globals.get("handle");
  const saved = localStorage.getItem("weiqi-rl");
  if (saved) pyodide.globals.get("import_model")(saved);
  backend = "py";
  state.boot = await api("/api/boot");
  setBanner("选段位，开始一盘。这一页关机也能打开。", "");
}

async function init() {
  let online = false;
  try {
    const response = await fetch("/api/boot");
    if (!response.ok) throw new Error("no api");
    state.boot = await response.json();
    online = true;
  } catch (error) {
    try {
      await bootBrowser();
    } catch (err) {
      engineEl.textContent = "网页没有连上";
      setBanner(err.message, "bad");
      return;
    }
  }
  paintEngine();
  const data = await api("/api/problems");
  state.problems = data.problems;
  render();
  draw();
  if (online) setInterval(refreshBoot, 3000);
}

function paintEngine() {
  refreshBoot().catch(() => {});
}

init();
