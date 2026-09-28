# CelestJux Editors

A room editor and character editor for designing a pixel room and its cast. Build a layout by hand, make characters, and export the files for your agent or game. The room editor also exposes `window.cjx`, a tile-coordinate API that an agent can use to collaborate with you on the same canvas.

**Editor:** https://celestjux-editors.vercel.app/ — ask the project owner for the password. Do not put it in a config file or issue.

## Use the editors

1. Open the editor and enter the password.
2. In **Room**, start with a blank room or select **sample room** for an example. Place furniture, paint tiles, and name your room and agents. Your own room and the sample are separate slots; edits to the sample do not replace your draft.
3. In **Character**, choose a body and layers, customize the cast, and export it. The character frame loads only when you first open its tab.
4. Download your room JSON from the Room editor and `cast.json` plus the character sprite sheets from the Character editor. Keep those files together when handing them to an agent or integrating them elsewhere.

Room drafts are saved in this browser's local storage; they are **not** synced between devices or backed up to a server. Export a JSON file to keep a portable copy. The character editor's export buttons download a single character and sheet or the whole cast and its sheets.

## Work with an agent

The room editor's `window.cjx` API reads and changes the **same room and undo history** as the human UI. Coordinates are tiles, with the origin at the top left. Start with `cjx.help()` for the live API, then use `cjx.describe()`, `cjx.at(x, y)`, `cjx.search(query)` and `cjx.themes()` to explore. Mutation verbs include `place`, `move`, `remove`, `paint`, `desk`, `undo` and `redo`.

For an MCP client, see [pixel-room-mcp](pixel-room-mcp/README.md). It launches a separate browser profile for the editor rather than exposing your everyday browser's tabs to a debugging port. With [uv](https://docs.astral.sh/uv/) and a Chrome-family browser installed, clone this repository and configure your client's MCP server like this (replace the path with your clone's absolute path):

```json
{
  "mcpServers": {
    "pixelroom": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/celestjux-editors/pixel-room-mcp/pixel_room_mcp.py"]
    }
  }
}
```

Open the editor through the MCP tool, enter the password **in the browser**, and ask your agent to check readiness. See the MCP README for its tools and environment settings. The API is in the room frame (`/room/`), not on the top-level tab shell.

## Repository layout

| Path | Purpose |
| --- | --- |
| `public/index.html` | Tab shell for the two editors |
| `public/room/` | Room editor, sprites, and sample room |
| `public/char/` | Character editor and sprite atlas |
| `middleware.ts` | Vercel password gate for pages and assets |
| `vercel.json` | Static `public/` deployment and no-index header |
| `pixel-room-mcp/` | Optional local MCP bridge to the editor |
| `tools/` | Local art, room, and inspection utilities |
| `MANIFEST.md` | Design decisions, behavior, and implementation notes |

## Deployment and access

This is a static `public/` site deployed on Vercel with edge middleware. Set `EDITOR_PASSWORD` as a Vercel environment variable for the deployment, then deploy the repository. There is no default password: without that variable, middleware returns an error instead of serving the site. Changing the variable requires a new deployment. The production URL above is the link intended for members; preview deployment access may additionally be restricted by Vercel Authentication.

**Artwork and distribution:** The sprite assets are derived from LimeZu's Modern Interiors. A password protects the *deployed site*, not the files in a public Git repository: this repository contains tracked sprite assets that anyone with repository access can download. Do not assume the site gate grants redistribution rights. Confirm the asset licence and repository visibility before sharing or mirroring this project; replace/remove assets if you do not have permission to publish them. Do not remove the deployed site's asset gate as a shortcut.

For deeper implementation and deployment notes, read [MANIFEST.md](MANIFEST.md). Local development's `tools/local/serve.sh` is bound to a specific private WireGuard address and serves assets **without** the password gate; do not expose that server on a public interface.
