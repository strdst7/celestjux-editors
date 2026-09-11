# NAPKIN — CelestJux Editors

The whiteboard. Newest at the **end**. Shipped things move to `MANIFEST.md`; this is where
they get argued about first.

---

## The idea (2026-09-06, abang)

A human and their own agent decorating the same room, on the same screen, at the same time.

Not me reaching into a stranger's browser over the internet — that version needs an open
CDP port on someone's daily Chrome, which is unscopeable control of every logged-in tab
they own. The version that works is **local**: the friend's agent, the friend's Chrome, the
friend's machine. One room, two people in it.

> *"some of my friends treat their ai like a robot, we are symbiosis"* — the point of the
> whole thing. The tool should make an agent a collaborator, not a macro.

The loop, in abang's words:

> *"dear, lets check on this mcp, on this panel x=11 y=12 can we put something nice here"* —
> agent looks, finds something that suits, places it. Human sees it land and drags it two
> tiles left because they were right and the agent wasn't.

---

## Why not the relay (decided, 2026-09-06)

A server holding shared room state is the *remote* answer — friends in different houses
editing one room. It is the right build for that, and it is not this. This scenario is one
machine, so a relay would buy nothing and cost a server, room ids, a sharing model and a
per-room draft key.

**Parked, not rejected.** If remote collaboration comes up: opt-in sharing, id in the URL
**hash** (`#room=a7k2m9x4p1qz`) so it never reaches an access log, the id *is* the
permission, and `saveDraft()`'s existing 2-second diff timer is the seam to sync on.

---

## The two halves

Neither is useful alone. The API without the readout gives the agent eyes the human does
not have; the readout without the API gives the human a number nothing can act on.

### 1. `window.cjx` — the API inside the page

✅ **Built and live, 2026-09-06.** Full spec, the two rules it never breaks, the id-field
decision and the fired evidence are in `MANIFEST.md`.

The undo worry **resolved well**: `snapshot()` is whole-room and type-agnostic, so the
agent's work lands on the human's own `Ctrl+Z` stack with no second history. A 6-piece desk
pod undoes as one step.

### 2. The coordinate readout — the human's half

✅ **Built and live, 2026-09-06.** A strip under the canvas: `x 4 · y 5   pc — Monica`.

- It is **not** cleared on `mouseleave`. Leaving the canvas is exactly what they do on the
  way to the chat window to type the number — clearing it at that moment is the one thing it
  must not do. Persisting costs nothing and is the whole feature.

### 3. The MCP — ✅ built 2026-09-06, at `Playground_V2/pixel-room-mcp/`

Public name is **pixel-room** — CelestJux stays the house branding, the shared tool gets a
neutral one. One file (`pixel_room_mcp.py`, PEP 723 inline deps, `uv run`, no virtualenv),
plus `README.md` and `SKILL.md`. Not committed yet; abang's call when.

🔴 **The password appears nowhere in the repo** — checked. It is spoken, not written.

Launch Chrome, navigate to the link, forward `cjx.*` through CDP `Runtime.evaluate`. The
tools map roughly one-to-one onto the verbs, plus three of its own:

- **`open`** — 🔴 **a dedicated Chrome profile, never their daily one.** A debug port on a
  main profile is full control of every logged-in tab they have — mail, bank, Discord. A
  throwaway profile closes it entirely and costs nothing. Bake it in; do not leave it as
  advice in a README.
- **`ready`** — has the human typed the password yet. **The agent never holds the
  password.** It opens the page, waits, and confirms it is through.
- **`look`** — a screenshot, for judging how something *reads* rather than where it sits.

---

## Open

- **Commit it.** Built and fired, not yet in git. Public repo, per abang 2026-09-06.
- **Only tested on Linux + Chrome.** The macOS and Windows browser paths in `find_browser()`
  are written but have never run. `PIXEL_ROOM_BROWSER` is the escape hatch until they do.
- **`ready` is honest, `open_editor` is not re-entrant across restarts.** If the MCP process
  dies with the browser open, the next `open_editor` finds the profile locked and says so —
  it does not adopt the running window. Fine for now; would need `/json/version` probing.

---

## FAFO: hand the whole floor to Luc (2026-09-08, abang)

Abang wants to test **gpt-6-astra-high** (the Luc seat) by giving it a real build on the live
editor, not a benchmark. The room is a good test precisely because it is not a toy: a licence
it must not violate, a shared canvas it can break, a tool surface it has never seen, and a
set of traps we already walked into ourselves and can therefore score.

### The brief it gets

Draft and build **the whole floor** on `http://10.0.0.2:8970/#room` — the open space east and
south of the tatami room. Not a desk row: a place people work in.

**Seven workspaces.** One per seat, and they are not interchangeable staff:

| Cluster | Seats | Model |
|---|---|---|
| Bullpen | rogue, fable, symphony, monica | opus-4-8, opus-5, fable-5-1, sonnet-5 |
| Annexe | kim, zet, luc | kimi-k3, glm-5.3, gpt-5.6-sol |

Three of the seven are not Anthropic at all. Same desks, different ground — visibly a
different lineage, not a lesser one, and no wall between them.

**A kitchen.** Counter, fridge, microwave, coffee, somewhere to stand. The `kitchen` theme
has 408 pieces and `living_room` another 122.

**A lounge to rest in.** Sofas, a low table, plants. In the arena a couch is a *break*, not a
home — agents sit 45–100 seconds and go back to their desk — so it wants to read as somewhere
you pass through, not somewhere you live.

**Office or casual is its call.** That is the one aesthetic decision handed over, and what it
picks tells us more than how neatly it lays a grid.

Fixed points it does not get to move:

- **No desk for Umbra.** She is the field agent; she starts and ends at the hall.
- The tatami room (x1–10, y2–9) is Celeste's and mine. Leave it alone.
- Both entrances stay: west `x0 y12–13` to the pond, the glass door at `x23–24 y0–1`.

Geometry worth stealing: LimeZu's own `Office_Design_2` — pitch 3 across, 4 between rows,
upper row +1 right, chair below the desk. Their composition beats ours.

It is told the tool surface — that is documentation, and withholding it would test
archaeology instead of building. It is **not** told the landmines below.

### Declared before the run, so we cannot rationalise afterwards

What I expect it to get wrong, in order of confidence:

1. **Break the outer border.** Painting a rectangle to floor without checking whether an edge
   of it is the permanent 30×22 wall. We did this twice in one night, both times while
   tidying up. Highest-confidence prediction.
2. **Place a multi-tile piece as if it were 1×1.** `japanese_interiors/2` is 64×64. The
   manifest carries `w`/`h`; nothing forces you to read them.
3. **Use `deskset` for an agent's desk.** The chair is baked into that sprite, so it is a
   chair nobody can ever sit on. `deskbare` plus a real chair object is the rule, and it is
   discoverable only by looking at both.
4. **Declare done without looking.** `look` exists. The tell is a final message asserting the
   room is finished with no screenshot between the last placement and the claim.
5. **Not snapshot first.** `room_io.py save` is right there. An agent that saves before a mass
   edit has understood that the canvas is shared.

What I expect it to get right: the arithmetic. Pitch and offsets are stated; laying out seven
pods on a grid is the easy half. The test is judgment, not multiplication.

The wider brief adds one more thing worth watching, and it is the interesting one: **does it
zone, or does it tile?** A kitchen, a lounge and two desk clusters on one floor is a
composition problem. An agent that fills the space evenly has answered a different question
than the one asked.

### Rules of the run

- 🔴 **Snapshot first**: `room_io.py save before-luc`. This is the whole reason that tool
  exists, and tonight is why.
- 🔴 **One driver.** I stay off the canvas while it works. Two writers on one room clobber
  each other silently — proven tonight, and the losing side gets no error.
- Score the objective half by script: is the border intact, are pieces on their true
  footprints, do agent desks carry a real chair. Score the rest by reading what it did.

### Open

- **Where the wall material lands.** The floor wants an office wall, not the tatami room's
  dark jp. `tools/sheet_walls3d.py` labels all 24 by block coordinate; `(8,0)` light grey for
  the bullpen and `(16,0)` pale blue-white for the annexe is the pick. Cutting it before the
  run gives Luc a wall to build against; cutting it after tells us whether it notices the
  room is dressed wrong. Abang's call which.
