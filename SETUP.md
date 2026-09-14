# Setup, testing, and publishing

## 1. Local environment

```bash
# from the repo root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies are intentionally minimal — `Pillow` (image loading), `numpy`
(array math), `scipy` (flood-fill background removal, `ndimage.label`).
Nothing else is required; there's no dependency on any stats/card service.

## 2. Generate the portrait (no token needed)

```bash
python scripts/generate_portrait.py --debug
```

`--debug` writes intermediate images to `generated/_debug/` so you can
sanity-check the pipeline instead of tweaking thresholds blind:

- `01_mask.png` — the subject/background flood-fill mask
- `02_isolated_subject.png` — background stripped, subject only
- `03_bg_distance.png` — raw per-pixel color distance from the background
- `04_char_preview.png` — the character grid, quantized (uses a
  light-background convention for the raw preview, so it looks tonally
  inverted compared to the real SVG — that's expected, only the ramp
  *shape* matters here)

Open `generated/portrait.svg` directly in a browser to see the real
typewriter animation (SVG SMIL doesn't run in most image viewers —
`--debug` PNGs and a browser are the two ways to actually check it).

If the portrait doesn't resemble the source:
1. Look at `01_mask.png` first. If the subject is missing chunks, the
   background-distance threshold (`BG_DISTANCE_THRESHOLD` in
   `generate_portrait.py`) is too low for your image's contrast — raise it.
   If background is leaking in as "subject", lower it.
2. Look at `04_char_preview.png` to see if the *shape* is right before
   worrying about character choice.
3. Only then adjust `RAMP` or `GRID_COLS`.

Replace `assets/input/portrait.jpg` with your own image any time — the
pipeline re-analyzes it from scratch, it doesn't assume a specific photo.

## 3. Generate the stats graphics (needs a token)

These call the GitHub GraphQL API, so they need a token even when run
locally. A classic PAT with `read:user` scope is enough (no `repo` scope
needed since we only ever query public data):

```bash
export GITHUB_LOGIN=<your-username>
export GITHUB_TOKEN=<a personal access token, read:user scope>

python scripts/generate_stats.py
python scripts/generate_streak.py
python scripts/generate_languages.py
python scripts/generate_year.py
```

In GitHub Actions this same code runs with the built-in `GITHUB_TOKEN` —
no PAT is stored anywhere in the repo. `GITHUB_LOGIN` is filled in from
`github.repository_owner` automatically in the workflow.

## 4. Preview everything together

```bash
# open the README next to the generated/ folder in a browser-based
# markdown previewer, or just open the SVGs directly:
python -m http.server 8000
# then visit http://localhost:8000/generated/portrait.svg etc.
```

GitHub renders README-embedded SVGs as static `<img>` sources, so what
you see in a plain browser tab is what you'll get on your profile page.

## 5. Publishing checklist

- [ ] Replace `assets/input/portrait.jpg` with your actual photo/art if
      different from the one used during development.
- [ ] Run `generate_portrait.py` locally once and eyeball the animation
      in an actual browser tab (not just the debug PNGs).
- [ ] Fill in the `<YOUR_USERNAME>`, `<YOUR_NAME>`, and other placeholder
      text in `README.md` (identity blurb, current focus, projects table,
      contact links).
- [ ] Create the repository at `github.com/<YOUR_USERNAME>/<YOUR_USERNAME>`
      (the special profile-README repo name) and push this project to it.
- [ ] Confirm the repo's Settings → Actions → General → Workflow
      permissions is set to "Read and write permissions" (needed for the
      workflow's `git push` — `permissions: contents: write` in the
      workflow file requests this, but org-level defaults can still block
      it).
- [ ] Manually trigger the workflow once (Actions tab → Refresh profile →
      Run workflow) instead of waiting for the first schedule, and check
      the generated SVGs it commits actually look right.
- [ ] Confirm `generated/*.svg` and `assets/fonts/*` are committed (not
      gitignored) — they're the whole point of the "no third-party
      service" requirement, unlike a normal generated-output convention.

## Troubleshooting

**Workflow runs but doesn't commit anything.** Expected if nothing
actually changed (e.g. re-running twice the same UTC day with no new
contributions). Check the Action log for "No changes in generated/ --
nothing to commit."

**Workflow fails with a permissions/403 error on push.** Repo Settings →
Actions → General → Workflow permissions → set to "Read and write
permissions".

**GraphQL request fails with a 401.** `secrets.GITHUB_TOKEN` is injected
automatically by Actions — you don't set it yourself in CI. Locally,
double check `GITHUB_TOKEN` is actually exported in your current shell
session (`echo $GITHUB_TOKEN`).

**Portrait looks like solid blocks / lost detail in one region.** That
region's color is likely too close to the background color for the
current `BG_DISTANCE_THRESHOLD` — see the debug workflow above. Note
that if your source image has a region that's genuinely the *same color*
as the background with no enclosing outline (as our sample image's
"shadow half" turned out to be), no algorithm can recover detail that
isn't in the pixels — check `03_bg_distance.png` to see if that's what's
happening before assuming it's a bug.

**Animation doesn't play / portrait appears fully drawn instantly.**
Some SVG viewers and most SVG-to-PNG converters (e.g. `rsvg-convert`,
used for the debug previews in this project) don't execute SMIL
animation and just render the first frame. GitHub's own renderer and
real browsers do run it — test in an actual browser tab.

**Language chart is empty or missing a language you expect.** The query
filters to `privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]`
by design (see the docstring in `generate_languages.py`) — private repos,
forks, and repos you don't own won't show up. This is intentional so the
result doesn't silently depend on token scope.
