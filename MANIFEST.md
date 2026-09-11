# CelestJux Editors — the shipped bundle

The two editors from `room-editor/` and `char-editor/`, behind one password, on one link,
for abang's Discord members to draft their own N-agent room and their own cast.

**Live:** https://celestjux-editors.vercel.app/ · **Password:** ask abang — spoken, never written here
**Vercel project:** `celestjux-editors` (team `juxtapo9090`, `prj_U8PvP97XlHC7sCg86EZQDHBRDmVs`)

Nothing in `room-editor/`, `char-editor/` or `kraked-arena/` was modified. This tree is a
copy plus three new files.

---

## What a member does

Opens the link, types the password, gets two tabs. **Room** opens **blank** — a member is
here to build their own room, not to inherit ours, and booting into someone else's office
makes their layout look like the thing to edit. **sample room** loads the CelestJux office
if they want to see a finished one. **Character** boots into a walking body with the full
432-layer palette. They hand their agent `room.json` + `cast.json` + the exported
`*-sheet.png` files.

---

## Layout

| Path | What |
|---|---|
| `middleware.ts` | The gate. Runs at the edge before the CDN cache, so it covers the art too |
| `vercel.json` | `framework: null`, `outputDirectory: public`, `X-Robots-Tag: noindex` |
| `public/index.html` | Tab shell — two iframes, one per editor |
| `public/room/` | `room-editor/editor.html` as `index.html`, its `sprites/`, and `sample-office.json` |
| `public/char/` | `char-editor/editor.html` as `index.html`, plus its `sprites/` |

5.3 MB total. Both editors reference their art relatively (`sprites/pack.png`,
`sprites/char-atlas.js`), so dropping each into its own folder needed **no edit to either
file**.

**The one change to a copied editor** — `public/room/index.html` only, upstream untouched:
the boot path no longer fetches `room.json`, it calls `blankRoom(30, 22)`. The office ships
as `sample-office.json` behind a **two-slot switch**.

### The two slots

A pair of buttons under Save/Load: the member's own room on the left (labelled with its
name, `untitled` until they rename it) and **sample room** on the right in amber. The active
one is filled.

Switching **keeps both**. Going to the sample parks a deep copy of their room in `mineHeld`;
coming back restores it. The sample is deep-copied on every open, so editing it and
returning gives a clean office next time, not a vandalised one.

🔴 **`saveDraft()` refuses to write while `viewing === "sample"`.** Without that guard the
2-second autosave overwrites the member's own draft with our office the moment they nudge
anything while looking at it — and they find the CelestJux office waiting for them on their
next open, with their own room gone. This is the reason the two slots exist at all, not a
nicety on top of them.

---

## `window.cjx` — the API a collaborating agent talks to

An agent driving a generic page can only click pixels. This is our page, so it gets verbs.
**Everything crossing this boundary is a tile coordinate or a piece name** — no pixels in
either direction.

| Read | |
|---|---|
| `cjx.help()` | the verbs and their shapes, so an agent can find its own way |
| `cjx.describe()` | the room as objects, plus counts and the agent names in it |
| `cjx.at(x, y)` | what is on one tile, and the floor under it |
| `cjx.search(q)` | pieces by name across all 5537 |
| `cjx.themes()` | the 7 arena types and the 24 pack themes with their counts |

| Write | |
|---|---|
| `cjx.place(piece, x, y, {owner})` | returns the new id |
| `cjx.move(id, x, y)` · `cjx.remove(id)` | |
| `cjx.paint(x, y, kind)` | `floor` \| `wall` \| `door` \| `grass` \| `water` |
| `cjx.desk(x, y, owner)` | a whole pod — desk, 3 blockers, pc, chair |
| `cjx.undo()` · `cjx.redo()` | |

### Two rules it never breaks

🔴 **Nothing throws.** Every call returns an object; a failed one carries `error` and a
`hint` naming the way out. An exception through CDP reaches the agent as a stack trace with
no advice in it, and a confused agent is worse than no agent.

🔴 **Every mutation calls `snapshot()` first**, exactly as a mouse click does. `snapshot()`
serialises the whole `{map, objects}` and knows nothing about who is changing it, so the
agent's work lands on the **same undo stack as the human's**. Measured: 7 objects → the
human clicks the undo *button* → 1 → 0 → redo → 1, and a 6-piece desk pod undoes as **one
step**, not six.

### Objects gained an id

A `room.json` object had no identity — it was found by position in an array, which shifts
the moment anything is removed, so `cjx.move()` would silently move the wrong chair. Ids are
minted on placement and stamped onto older objects the first time anything looks at them.

**This changes the file format, additively.** Checked before committing to it: the arena
reads objects by named field (`o.type`, `o.art`, `o.owner`) and never enumerates keys, so
the extra field is inert there.

### Fired through bravemag, as a friend's agent would

| Call | Result |
|---|---|
| `cjx.search("plant")` | `plant_small 1x2`, `plant_large 2x2`, `plant_palm 2x2` |
| `cjx.place("plant_palm", 11, 12)` | `{id: "o1", type: "prop", art: "plant_palm"}` |
| `cjx.at(11, 12)` | now `empty: false`, the palm listed |
| `cjx.desk(4, 5, "Ali")` | 6 pieces — and **"Ali" appeared in the human's AGENTS roster** unprompted |
| `cjx.place("plnat", …)` | `no piece named "plnat"` + hint |
| `cjx.place("desk", 99, 99)` | `(99, 99) is outside the room` + `the room is 30 x 22` |
| `cjx.paint(2, 2, "lava")` | `no tile kind "lava"` + `one of: floor, wall, door, grass, water` |
| `cjx.search("no-such-thing")` | `[]` **plus a note** that pack pieces are numbered, not named |

That last row is the one worth keeping. Most themes name pieces by number (`bedroom/136`),
so a word search returns nothing for an honest reason — a bare `[]` would send an agent
looking for a bug that isn't there.

⚠️ **`cjx` is defined last in the script**, after everything it closes over. Moving it
earlier breaks it silently at load.

### Wide furniture blocks its whole footprint

A sprite is anchored by its **bottom-left** tile and grows up and right (`blit()` draws at
`py + TILE - s.h`). So a three-tile sofa placed at `x` used to block only `x`, leaving two
walk-through tiles under visible furniture — a room that looks right while being wrong.

`place()` now lays `blocker` objects across the rest of the piece's bottom row, using the
same `footprint()` the editor draws the drag preview with, so the two cannot drift.
`remove()` takes them away again.

🔴 **`remove()` clearing its own blockers is the important half.** A blocker outliving its
piece is an invisible solid tile in open floor — the exact bug that put a ghost wall in
front of Pak Abu in the arena for weeks, and it is unfindable by looking at the room.

Fired:

| Case | Result |
|---|---|
| `place("sofa_3", 10, 10)` | blockers at `(11,10)` and `(12,10)`; `(13,10)` clear |
| `place("mug", 20, 10)` | one tile wide → no blockers |
| `place("rug", 5, 18)` | non-solid → no blockers |
| `place("sofa_3", 29, 3)` | overhangs the right wall → stops at the edge, none off-grid |
| `remove(sofa)` | 6 objects → 3, both blockers gone, their tiles clear |
| then the human's undo button | 6 back **in one step**, sofa restored |

And by pixel, sampling the canvas with the `B` overlay on and off — `(11,10)` and `(12,10)`
change `162,169,191` → `170,145,160`, while `(13,10)` is identical either way. The overlay
is `rgba(200,60,60,0.22)`, faint enough that eyeballing a screenshot proves nothing.

`{blockers: false}` opts out for anything decorative that should stay walk-through.

---

## The character editor's "colour" field was lying

Abang changed `colour` to a dark red and the hair did not change, and reported a broken
tint. The tint was never broken. There are **two** colours and only one of them touches a
pixel:

| Control | Sets | Changes the sprite? |
|---|---|---|
| `colour` in the character form | `ch.color` — the agent's own colour in the room, for labels and status | **no** |
| tint, in the LAYERS panel | `ch.look.tints[layer]` | yes |

The tint control only appears on a **tintable** tab (`outfit`, `hair`, `accessory`). From
the default `body` tab the panel says *"body is not tinted"*, so there is nothing on screen
to find — and the thing that *looks* like the colour control does nothing visible.

🔴 **A swatch that changes nothing you can see is the editor lying.** The bug was the
affordance, not the maths. Fixed with an **apply to · hair · outfit · accessory** row under
the swatch: press one and the colour lands on the sprite, press a lit one again to take it
off. The line under it says which layers are painted.

### What a tint actually does — the part that surprises

```js
// tintCanvas()
var out = hsv2rgb(theirHue, Math.min(1, ourSat * satMul), ourValue);
```

**Only the hue travels.** The sprite keeps its own saturation curve and its own
value, so:

- `#0a0000` — near-black — lands as **red**, because red is its hue. Not black.
- Black and white hair are impossible this way, by design.
- Pixels below `0.12` saturation are skipped entirely: near-greys carry the shading and the
  white trim, and recolouring them flattens the garment into a blob.

The note under the buttons says this in one line, because the first thing anyone does is
pick a very dark colour and expect dark hair.

Fired on the live page: set `#0a0000` → press **hair** → `{hair:{color:"#0a0000",sat:1.4}}`,
button lit, hair visibly red. Set `#2255dd` → press **hair** → hair visibly blue. Press a lit
button with the same colour → tint removed, button unlit.

---

## The gate

A password screen drawn inside the page would be theatre: `pack.png` has its own URL and
a member could skip the whole menu by typing it. Vercel **Routing Middleware** is a
platform feature, not a framework one — it runs before the cache on every matched request,
so the art is behind it as well as the HTML.

- Password lives in the `EDITOR_PASSWORD` environment variable, production scope. It is
  never shipped to the browser.
- **No default.** A deployment without that variable returns 500 and serves nothing —
  measured, see below. A gate that falls open when its config is missing is worse than no
  gate.
- The cookie is `sha256("cjx:" + password)`, `HttpOnly; Secure; SameSite=Lax`, 30 days.
- The login page is rendered *by* the middleware, so it has no URL of its own to bypass.

**What this does not do, said once:** it stops strangers and search engines. It does not
stop a member who is already through the door from saving `pack.png`. Nothing can — a
browser has to download what it draws. What protects the pack is the word *trusted* in
"trusted members".

🔴 **The art is LimeZu's Modern Interiors and is behind that gate for a licence reason**,
not a vanity one. If the password ever goes public, this becomes a redistribution of a
paid pack from abang's own Vercel account. Rotating the password is a real fix; removing
the gate is not a cleanup.

---

## Fired, not assumed

Every line below is a real response from `https://celestjux-editors.vercel.app`.

| Probe | Result |
|---|---|
| `/` with no cookie | **401** gate page |
| `/room/sprites/pack.png` with no cookie | **401**, 1395 bytes (the gate, not the art) |
| `/char/sprites/char-atlas.js` with no cookie | **401** |
| `POST /__gate` wrong password | **401**, "Wrong password." — rendered live in Brave |
| `POST /__gate` correct password | **303** → `/`, sets cookie |
| `/room/sprites/pack.png` with cookie | **200**, 1 898 797 bytes |
| `/char/sprites/char-atlas.js` with cookie | **200**, 1 433 264 bytes |
| Forged cookie `cjx=deadbeef` | **401** |
| No `EDITOR_PASSWORD` set | **500**, serves nothing |

And by eye, in abang's own browser: the Room tab renders the palette, the loaded office and
the agent roster; the Character tab renders the atlas ("local pack"), a running walk cycle
and both export buttons.

**The two slots, attacked rather than reviewed.** Built a room (`aizat-room`, 2 objects, one
agent "Ali"), then:

| Step | Result |
|---|---|
| Press **sample room** | `office` / 102 objects, `viewing: "sample"`, sample button lit |
| The other button's label | reads **`aizat-room`** — it names their parked room, not "mine" |
| Vandalise the sample (rename, add an object), wait 6s = 3 autosave ticks | draft still holds **`aizat-room` / 2** — untouched |
| Press **`aizat-room`** | `aizat-room` / 2 objects, agent "Ali" intact, buttons flipped |
| Press **sample room** again | `office` / **102** — clean, not the vandalised 103 |

---

## Landmines paid for here

🔴 **Vercel Authentication is on by default and gates *before* middleware.** A fresh project
returns 302 to `vercel.com/sso-api` on its generated deployment URLs, which admits only team
members — the opposite of what a shared link needs. The **production alias**
(`celestjux-editors.vercel.app`) is exempt, which is why that is the URL to hand out.
`ssoProtection: {deploymentType: "all_except_custom_domains"}` is the setting; it is left on,
because protecting the preview URLs costs nothing.

⚠️ **Middleware returning `undefined` continues the request.** Verified by the 200s above,
so `@vercel/functions` and its `next()` are not needed and there is no `package.json`. Do
not add one to "fix" a problem that does not exist.

⚠️ **Do not set `X-Frame-Options: DENY` on this project.** The shell is two same-origin
iframes; that header would blank both tabs. `vercel.json` sets only `X-Robots-Tag`.

⚠️ **The character frame loads on first click, not on page load.** It carries a 1.4 MB
atlas. Once loaded it stays mounted, so switching tabs never discards work.

✅ **No `localStorage` collision.** The two editors now share an origin, which would matter —
but the room editor namespaces its key (`celestjux.room.draft`) and the character editor
does not use storage at all.

⚠️ **The draft outranks the blank default, by design.** The room editor mirrors your work
into `localStorage` every 2s and restores it on open. So "it still opens the office" after
the blank-default change usually means a saved draft, not a regression — **discard draft**,
or clear storage, to see what a first-time visitor gets.

---

## Redeploying

```sh
cd /mnt/playground/Playground_V2/celestjux-editors
export VERCEL_TOKEN=$(tr -d '\n\r ' < /home/juxtapo/Documents/vercel_taken_liam_neeson.md)
npx --yes vercel@latest deploy --prod --yes
```

Pass the token as an **environment variable**, never as `--token` — npx echoes its argv,
so the flag form prints the secret into the terminal.

To change the password:

```sh
npx --yes vercel@latest env rm  EDITOR_PASSWORD production --yes
printf 'newpassword' | npx --yes vercel@latest env add EDITOR_PASSWORD production
npx --yes vercel@latest deploy --prod --yes    # env changes need a redeploy
```

---

## Open

- **Art is a copy, not a link.** A re-cut of `pack.png` or `char-atlas.js` upstream does not
  reach this tree. Re-copy `public/room/sprites/` and `public/char/sprites/` and redeploy.
- **One password for everyone.** No per-member accounts, no revoking one person. Rotating
  the password rotates it for all of them. Right size for a Discord group; wrong size the
  day it is not.
- **Saving is local.** `saveRoom()` / `loadRoom()` still download a file. Binding them to a
  server replaces those two functions and nothing else — that seam is unchanged.
