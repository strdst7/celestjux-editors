#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=2", "websockets>=12.0"]
# ///
"""
pixel-room — decorate a room together with your agent.

It opens a browser on the editor, waits for *you* to type the password, and then
forwards your agent's requests to `window.cjx` inside the page. Everything that
crosses that boundary is a tile coordinate or a piece name, never a pixel — so
your agent is a collaborator with verbs, not a mouse on a leash.

Run it with `uv run pixel_room_mcp.py`. The dependencies install themselves;
there is no virtualenv to make and nothing to pip install.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets
from mcp.server.mcpserver import MCPServer

EDITOR_URL = os.environ.get("PIXEL_ROOM_URL", "https://celestjux-editors.vercel.app/")

# A profile of our own, never the one you browse with. A debug port on your
# everyday profile hands any process on this machine every tab you are signed
# into — mail, bank, chat. This one starts empty and knows nothing.
PROFILE_DIR = Path(os.environ.get(
    "PIXEL_ROOM_PROFILE", Path(tempfile.gettempdir()) / "pixel-room-profile"))


def _attach_port() -> int | None:
    """PIXEL_ROOM_PORT — attach to a browser that is already running.

    This deliberately gives up the protection above, so it is opt-in and never a
    default: the port you name belongs to a browser someone is already using,
    and every tab on it becomes reachable from here. Set it only for a browser
    you are willing to hand over.

    What it buys is that the agent works on the editor YOU are looking at.
    Without it the server can only talk to a browser it launched itself, so with
    your editor open on screen it opens a second, empty one on its own profile,
    back at the password screen.
    """
    raw = os.environ.get("PIXEL_ROOM_PORT")
    if raw is None:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SystemExit(
            f"PIXEL_ROOM_PORT is {raw!r}, which is not a port number. It wants the "
            "--remote-debugging-port of a browser that is already running.")
    return int(raw)


ATTACH_PORT = _attach_port()

BROWSERS = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "brave-browser", "brave", "microsoft-edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# Where cjx actually lives.
#
# The landing page is a shell with the two editors in iframes, so `cjx` is NOT on
# the top window — evaluating `typeof cjx` there says undefined forever, and the
# agent waits for a login that already happened. The frame is same-origin, so the
# parent can reach straight into it. Opening /room/ directly is also supported,
# and then cjx is on the window as usual; this handles both.
CJX_HANDLE = (
    "(function(){"
    "  if (typeof cjx !== 'undefined') return cjx;"
    "  try {"
    "    var f = document.getElementById('frame-room');"
    "    return (f && f.contentWindow && f.contentWindow.cjx) || null;"
    "  } catch (e) { return null; }"
    "})()"
)

# The character editor's surface, reached the same two ways. Its own comment
# calls it a test hook rather than an agent surface: the verbs return raw values
# and throw on bad input, where cjx answers {error, hint}. `call` tags the
# outcome either way, so a throw arrives as data rather than as a CDP error.
CHAR_HANDLE = (
    "(function(){"
    "  if (typeof __editor !== 'undefined') return __editor;"
    "  try {"
    "    var f = document.getElementById('frame-char');"
    "    return (f && f.contentWindow && f.contentWindow.__editor) || null;"
    "  } catch (e) { return null; }"
    "})()"
)

# The character frame carries a 1.4 MB atlas, so the shell leaves it with no src
# until someone clicks its tab. An agent never clicks, and would find that frame
# empty forever -- so ask the shell to show the tab. False on a page that is not
# the shell, and the caller moves on to the next tab.
WAKE_CHAR = (
    "(function(){"
    "  if (typeof show !== 'function') return false;"
    "  if (!document.getElementById('frame-char')) return false;"
    "  show('char'); return true;"
    "})()"
)

# What each editor is, in the one place that has to know. `name` is the handle
# the editor's own docs print in front of its verbs, and so the one prefix a
# caller may harmlessly type. `marks` only orders which tabs to try first; which
# page is really the editor is settled by asking the page.
SURFACES = {
    "room": {"name": "cjx", "handle": CJX_HANDLE, "wake": None,
             "marks": ("celestjux", "pixel-room", "/room/")},
    "char": {"name": "__editor", "handle": CHAR_HANDLE, "wake": WAKE_CHAR,
             "marks": ("celestjux", "pixel-room", "/char/")},
}

# A verb is one plain identifier. Anything else is a caller mistake, and building
# JavaScript out of it would report a syntax error instead of the real problem.
VERB_NAME = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def find_browser() -> str | None:
    override = os.environ.get("PIXEL_ROOM_BROWSER")
    if override:
        return override if (shutil.which(override) or Path(override).exists()) else None
    for name in BROWSERS:
        found = shutil.which(name) or (name if Path(name).exists() else None)
        if found:
            return found
    return None


class Browser:
    """One browser, one page, one CDP conversation."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port: int | None = ATTACH_PORT
        self._msg_id = 0
        # One remembered tab per surface: the two editors can be one shell page
        # or two tabs, and finding one says nothing about where the other is.
        self._ws_url: dict[str, str] = {}

    def launch(self, url: str) -> dict[str, Any]:
        if ATTACH_PORT is not None:
            # Attached to someone else's browser. Launching a second one here
            # would be the confusing failure: two windows, and the agent working
            # in the one nobody is looking at.
            return {"attached": ATTACH_PORT,
                    "note": "PIXEL_ROOM_PORT is set, so this is using the browser "
                            "already running on that port. Nothing was launched. "
                            "Open the editor in it yourself if it is not open."}
        if self.proc and self.proc.poll() is None:
            return {"already_open": True, "port": self.port}

        binary = find_browser()
        if not binary:
            raise RuntimeError(
                "No Chrome, Chromium, Brave or Edge found on this machine. Install "
                "one, or set PIXEL_ROOM_BROWSER to the full path of the binary.")

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        port_file = PROFILE_DIR / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)

        # Port 0 means "pick a free one". A fixed port collides with whatever is
        # already debugging on this machine, and that failure reads like a bug
        # in here rather than a busy port.
        # Chrome's stderr is kept, not sent to /dev/null. When it refuses to
        # start it says exactly why on there, and swallowing that leaves you
        # holding "it exited" with nowhere to go.
        self._log = tempfile.NamedTemporaryFile(
            prefix="pixel-room-browser-", suffix=".log", delete=False)
        self.proc = subprocess.Popen(
            [binary, "--remote-debugging-port=0", f"--user-data-dir={PROFILE_DIR}",
             "--no-first-run", "--no-default-browser-check", url],
            stdout=subprocess.DEVNULL, stderr=self._log)

        for _ in range(100):  # 10 seconds
            if port_file.exists():
                first = port_file.read_text().splitlines()[0].strip()
                if first.isdigit():
                    self.port = int(first)
                    return {"browser": Path(binary).name, "port": self.port, "url": url}
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"{Path(binary).name} exited before opening a port. "
                    f"It said: {self._why()}")
            time.sleep(0.1)
        raise RuntimeError(
            f"{Path(binary).name} started but never wrote a debugging port. If it was "
            "already running on this profile, close that window and try again.")

    def _why(self) -> str:
        """Whatever the browser printed on its way out, plus the two causes that
        account for nearly all of it."""
        try:
            self._log.flush()
            said = Path(self._log.name).read_text(errors="replace").strip()
        except Exception:
            said = ""
        tail = " | ".join(said.splitlines()[-3:]) if said else "(nothing)"
        if "root" in said and "sandbox" in said:
            tail += ("  — Chrome will not run as root. Run this server as your "
                     "normal user, which is how it is meant to be used anyway.")
        elif "cannot open display" in said.lower() or "DISPLAY" in said:
            tail += ("  — no desktop to open a window on. This needs the machine "
                     "you are actually sitting at.")
        return tail

    async def _ask(self, ws_url: str, expression: str) -> dict[str, Any]:
        """One evaluate against one named page, with no page-picking of its own.

        Separate from `evaluate` so that picking the page can itself ask a page a
        question without calling back into the picker.
        """
        self._msg_id += 1
        want = self._msg_id
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            await ws.send(json.dumps({
                "id": want, "method": "Runtime.evaluate",
                "params": {"expression": expression,
                           "returnByValue": True, "awaitPromise": True}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if msg.get("id") == want:
                    return msg.get("result", {})

    async def _page_ws(self, surface: str = "room") -> str:
        """The tab that actually has this surface's object on it.

        Matching the URL was wrong, and wrong in the quiet way: a GitHub page
        named celestjux-editors contains "celestjux" exactly as surely as the
        editor does, and it sorted first, so every call answered "the editor is
        not open yet" while the editor sat two tabs along. Ask each page whether
        the object is there instead. The URL marks stay on as an ordering hint
        only, so the likely tab is asked first and the usual case is one trip.

        Each surface is remembered separately. The two editors can be one shell
        page carrying both frames or two tabs opened directly, and neither
        arrangement should have to be declared anywhere.
        """
        if surface not in SURFACES:
            raise RuntimeError("No surface called %r — there is %s."
                               % (surface, " and ".join(SURFACES)))
        spec = SURFACES[surface]
        if self._ws_url.get(surface):
            return self._ws_url[surface]
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json", timeout=5) as r:
                targets = json.load(r)
        except OSError as exc:
            if ATTACH_PORT is not None:
                raise RuntimeError(
                    f"Nothing is answering on port {self.port}, which is where "
                    f"PIXEL_ROOM_PORT points. Start the browser with "
                    f"--remote-debugging-port={self.port}, or unset the variable to "
                    f"let this server launch its own.") from exc
            raise
        pages = [t for t in targets
                 if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if not pages:
            raise RuntimeError("The browser is open but has no page to talk to.")
        pages.sort(key=lambda t: not any(m in t.get("url", "")
                                         for m in spec["marks"]))
        present = f"!!({spec['handle']})"
        for t in pages:
            ws = t["webSocketDebuggerUrl"]
            try:
                if await self._truthy(ws, present):
                    self._ws_url[surface] = ws
                    return ws
                if spec["wake"] and await self._truthy(ws, spec["wake"]):
                    # The shell was asked to show the tab. The frame has to
                    # fetch and run before its object exists, so give it a
                    # moment rather than declaring the editor absent.
                    for _ in range(40):  # 4 seconds
                        await asyncio.sleep(0.1)
                        if await self._truthy(ws, present):
                            self._ws_url[surface] = ws
                            return ws
            except Exception:
                continue
        raise RuntimeError(
            "None of the %d open tabs has the %s editor loaded (looking for %s). "
            "Open it, or if it is open, it may still be on the password screen — "
            "type the password, then call `ready`."
            % (len(pages), surface, spec["name"]))

    async def _truthy(self, ws_url: str, expression: str) -> bool:
        r = await self._ask(ws_url, expression)
        return bool(r.get("result", {}).get("value"))

    async def _send(self, method: str, params: dict[str, Any],
                    surface: str = "room") -> dict[str, Any]:
        if not self.port:
            raise RuntimeError("Nothing is open yet — call `open` first.")
        self._msg_id += 1
        want = self._msg_id
        try:
            ws_url = await self._page_ws(surface)
            conn = await websockets.connect(ws_url, max_size=64 * 1024 * 1024)
        except Exception:
            # The remembered tab may have been closed or navigated away from.
            # Forget it and let the next call look again, rather than failing
            # for the rest of the session on a tab that is gone.
            self._ws_url.pop(surface, None)
            raise
        async with conn as ws:
            await ws.send(json.dumps({"id": want, "method": method, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if msg.get("id") == want:
                    return msg.get("result", {})

    async def evaluate(self, expression: str, surface: str = "room") -> Any:
        result = await self._send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True},
            surface=surface)
        if "exceptionDetails" in result:
            d = result["exceptionDetails"]
            raise RuntimeError(
                f"{d.get('text', '')} {(d.get('exception') or {}).get('description', '')}".strip())
        return result.get("result", {}).get("value")

    async def call(self, verb: str, args: list[Any], surface: str = "room") -> Any:
        if surface not in SURFACES:
            return {"error": f"no surface called {surface!r}",
                    "hint": "there is " + " and ".join(SURFACES)}
        spec = SURFACES[surface]
        # `help` prints every verb with its handle attached -- "cjx.floor" -- so a
        # caller who passes back exactly what they read builds cjx.cjx.floor here,
        # which is undefined. Take the prefix off rather than expecting the caller
        # to know the one name they must not type.
        if verb.startswith(f"{spec['name']}."):
            verb = verb[len(spec["name"]) + 1:]
        if not VERB_NAME.match(verb):
            return {"error": f"not a verb name: {verb!r}",
                    "hint": "pass the bare name, e.g. \"floor\" -- `help` lists them"}
        inner = json.dumps(args)[1:-1]
        # Every outcome comes back as data, tagged. Before this the page's own
        # exception arrived as a bare CDP error naming no verb, and a verb that
        # legitimately returns undefined -- draw() is one -- was indistinguishable
        # from cjx being missing, so a call that worked reported the password
        # screen instead. The character editor throws on bad input where cjx
        # answers {error, hint}, so tagging is what makes the two behave alike.
        out = await self.evaluate(
            f"(function(){{var c={spec['handle']};"
            f"if (!c) return {{gone: true}};"
            f"if (typeof c[{json.dumps(verb)}] !== 'function')"
            f"  return {{unknown: true, have: Object.keys(c)}};"
            f"try {{ return {{ok: true, value: c.{verb}({inner})}}; }}"
            f"catch (e) {{ return {{threw: String(e)}}; }}}})()", surface=surface)
        if out is None or out.get("gone"):
            return {"error": "the editor is not open yet",
                    "hint": "the page is still on the password screen — ask the human "
                            "to type it, then call `ready`. Do not retry in a loop."}
        if out.get("unknown"):
            return {"error": f"no such verb: {verb!r}",
                    "hint": "this editor has: " + ", ".join(out.get("have", []))}
        if "threw" in out:
            return {"error": f"{verb} threw: {out['threw']}",
                    "hint": "check the argument count and types against `help`"}
        return out.get("value")

    async def has_surface(self, surface: str = "room") -> bool:
        spec = SURFACES[surface]
        return bool(await self.evaluate(f"!!({spec['handle']})", surface=surface))

    async def verbs(self, surface: str = "room") -> Any:
        """What this surface actually has on it, asked rather than written down.

        The room editor has `help`; the character editor has no such thing, and
        its verb list is whatever the page happens to expose today.
        """
        spec = SURFACES[surface]
        out = await self.evaluate(
            f"(function(){{var c={spec['handle']};"
            f"return c ? Object.keys(c) : null;}})()", surface=surface)
        if out is None:
            return {"error": f"the {surface} editor is not open yet",
                    "hint": "open it, or type the password if it is waiting on one"}
        return {"surface": surface, "handle": spec["name"], "verbs": out}

    async def screenshot(self) -> bytes:
        r = await self._send("Page.captureScreenshot", {"format": "png"})
        return base64.b64decode(r.get("data", ""))

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.port = ATTACH_PORT
        self._ws_url = {}


browser = Browser()
server = MCPServer(
    "pixelroom",
    instructions=(
        "Decorate a pixel room alongside the human at the keyboard.\n\n"
        "Start with `open_editor`. If the human gives you the password, `login` "
        "types it in for them; if they do not offer it, do not ask — say you will "
        "wait, and let them type it in the browser window. Either way `ready` "
        "tells you when you are through.\n\n"
        "Then call `help` before anything else: the editor is deployed separately "
        "from this server, so the page is the source of truth for what it can do, "
        "not this tool list.\n\n"
        "Work in tile coordinates. The human has a live x/y readout under their "
        "canvas, so a coordinate they say out loud is one you can pass straight in. "
        "Place one thing and stop — they are looking at the same screen and will "
        "move it if you were wrong."),
)


def j(value: Any) -> str:
    return json.dumps(value, indent=2)


@server.tool()
def open_editor(url: str = "") -> str:
    """Open the editor in a browser, using a dedicated profile — never the human's
    everyday one. It lands on a password screen: use `login` if the human gave you
    the password, otherwise wait for them to type it and call `ready`."""
    try:
        return j(browser.launch(url or EDITOR_URL))
    except Exception as exc:
        return j({"error": str(exc)})


@server.tool()
async def ready() -> str:
    """Is the editor open and past the password screen? `waiting: true` means the
    human is still logging in. That is not an error — wait for them, do not retry
    in a loop."""
    try:
        if not browser.port:
            return j({"open": False, "hint": "call `open_editor` first"})
        if not await browser.has_surface():
            return j({"open": True, "waiting": True,
                      "hint": "the human has not typed the password yet"})
        return j({"open": True, "waiting": False,
                  "room": await browser.call("describe", [])})
    except Exception as exc:
        return j({"error": str(exc)})


@server.tool()
async def help() -> str:
    """The live list of verbs the page supports, straight from the page itself.
    Call this first — it, not this tool list, is the contract."""
    return j(await browser.call("help", []))


@server.tool()
async def describe() -> str:
    """The whole room as objects, with counts and the agent names living in it."""
    return j(await browser.call("describe", []))


@server.tool()
async def at(x: int, y: int) -> str:
    """What is on one tile, and the floor under it."""
    return j(await browser.call("at", [x, y]))


@server.tool()
async def search(q: str, limit: int = 40) -> str:
    """Find pieces by name across the whole pack. Most pack pieces are numbered
    rather than named (`bedroom/136`), so when a word finds nothing that is the
    pack, not a bug — browse a theme instead."""
    return j(await browser.call("search", [q, limit]))


@server.tool()
async def themes() -> str:
    """The built-in types, and every pack theme with how many pieces it holds."""
    return j(await browser.call("themes", []))


@server.tool()
async def place(piece: str, x: int, y: int, owner: str = "", blockers: bool = True) -> str:
    """Place a piece at a tile. Wide furniture gets its collision tiles laid for
    you. Pass `owner` to make it an agent's machine; `blockers=false` to leave it
    walk-through. Returns the new id."""
    opts: dict[str, Any] = {}
    if owner:
        opts["owner"] = owner
    if not blockers:
        opts["blockers"] = False
    return j(await browser.call("place", [piece, x, y, opts]))


@server.tool()
async def move(id: str, x: int, y: int) -> str:
    """Move a piece to another tile, by the id `place` or `describe` gave you."""
    return j(await browser.call("move", [id, x, y]))


@server.tool()
async def remove(id: str) -> str:
    """Remove a piece. Its collision tiles go with it — never clean those up
    yourself, and never leave one behind: an orphaned blocker is an invisible wall
    standing in open floor that nobody can find by looking at the room."""
    return j(await browser.call("remove", [id]))


@server.tool()
async def paint(x: int, y: int, kind: str) -> str:
    """Paint one tile: floor, wall, door, grass or water."""
    return j(await browser.call("paint", [x, y, kind]))


@server.tool()
async def desk(x: int, y: int, owner: str = "") -> str:
    """Stamp a whole agent pod at once: desk, collision tiles, monitor and chair.
    This is how a room says how many agents it has."""
    return j(await browser.call("desk", [x, y, owner]))


@server.tool()
async def undo() -> str:
    """Undo one step — the same stack as the human's Ctrl+Z. Prefer letting them
    undo their own way; use this to take back something you just did."""
    return j(await browser.call("undo", []))


@server.tool()
async def login(password: str) -> str:
    """Type the password into the gate for the human, when they have given it to
    you. Fills the form and submits it, then reports whether you are through.

    Never repeat the password back in your own text, and never write it into a
    file, a note or a config. If the human has not offered it, do not ask — say
    you will wait, and let them type it in the browser window themselves."""
    try:
        if not browser.port:
            return j({"error": "nothing is open", "hint": "call `open_editor` first"})
        if await browser.has_surface():
            return j({"open": True, "waiting": False, "note": "already through"})

        filled = await browser.evaluate(
            "(function(){var f=document.querySelector('input[name=password]');"
            "if(!f) return 'no-form';"
            f"f.value={json.dumps(password)};f.form.submit();return 'submitted';}})()")
        if filled == "no-form":
            return j({"error": "no password box on this page",
                      "hint": "the browser may not be on the editor — call "
                              "`open_editor`, or check what page is showing"})

        # The submit is a round trip; give it a moment before judging it.
        for _ in range(20):
            await asyncio.sleep(0.5)
            if await browser.has_surface():
                return j({"open": True, "waiting": False,
                          "room": await browser.call("describe", [])})
            if await browser.evaluate(
                    "document.body.textContent.indexOf('Wrong password') >= 0"):
                return j({"error": "wrong password",
                          "hint": "ask the human to check it — do not guess, and "
                                  "do not try variations"})
        return j({"open": True, "waiting": True,
                  "hint": "submitted, but the editor has not appeared. The room "
                          "editor lives at the /room/ path — try `ready` again."})
    except Exception as exc:
        return j({"error": str(exc)})


@server.tool()
async def look() -> str:
    """Screenshot the page to a file, for judging how something reads rather than
    where it sits. Returns the path — open it with your own file reader. `describe`
    is cheaper and usually enough."""
    try:
        png = await browser.screenshot()
        out = Path(tempfile.gettempdir()) / "pixel-room-look.png"
        out.write_bytes(png)
        return j({"path": str(out), "bytes": len(png)})
    except Exception as exc:
        return j({"error": str(exc)})


@server.tool()
async def call(verb: str, args: list[Any] | None = None) -> str:
    """Call any cjx verb by name, including ones newer than this server. The editor
    is deployed separately, so `help` may list verbs that have no tool here — this
    is how you reach them without reinstalling anything."""
    return j(await browser.call(verb, args or []))


@server.tool()
async def char(verb: str = "", args: list[Any] | None = None) -> str:
    """The character editor, the same way `call` is the room editor. Call with no
    verb to list what it has.

    Its verbs are a test hook rather than a designed agent surface, so they take
    raw values and throw where cjx would answer {error, hint} — the throw comes
    back here as data either way. The useful ones:

      ready()            is the sprite pack loaded yet
      cast()             every character in the cast; select(i) picks one
      set(key, value)    change one part of the current look
      json()             the selected character as a character file
      load(character)    put one back
      compose()          re-render the sheet after changes
      state() history()  which way it faces and whether undo has anything

    The character tab is loaded lazily by the shell page, so the first call here
    asks the shell to show it and waits for it — no clicking needed."""
    if not verb:
        return j(await browser.verbs("char"))
    return j(await browser.call(verb, args or [], surface="char"))


if __name__ == "__main__":
    try:
        server.run("stdio")
    finally:
        browser.close()
