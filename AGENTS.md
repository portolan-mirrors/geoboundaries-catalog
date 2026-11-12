## This Repository

A git-backed Portolan catalog mirroring the geoBoundaries CGAZ composite. The
catalog metadata is tracked here; the data is built by `tools/` and lives in
object storage. Read `README.md` for the layout and the build commands.

### The publish boundary

`catalog/` is the published catalog. Everything in it is published except
dot-directories, and nothing outside it ever is. Do not move a file into
`catalog/` to make it publish, and do not add a path outside `publish_dir` to
`tools/publish.py`. The boundary is the only thing standing between a scratch
file and a public bucket, and it holds because it is structural rather than a
list of exclusions.

### Data never enters git

Never commit a GeoParquet, PMTiles, GeoPackage or Zarr file. The pipeline
stages 1.1 GB in `../geoboundaries-staging`, outside the repository, and
`tools/upload_data.py` carries it to the bucket. Git keeps every version of a
binary forever and deleting it later reclaims nothing.

### Edit the generator, not the generated file

Two kinds of file under `catalog/` are generated and will be overwritten:

| generated | by |
|---|---|
| `catalog/*/collection.json` | `tools/make_collections.py` |
| `catalog/*/styles/*.json` | `tools/make_styles.py` |

Everything else under `catalog/` is hand-written: `catalog.json`, every
`README.md`, every `AGENTS.md`, `llms.txt`. The collection READMEs are *not*
produced by `portolan readme`; this repository publishes with its own
`tools/publish.py` and does not run the Portolan CLI, so running
`portolan readme` here would replace hand-written prose with a generated
skeleton.

### Numbers in prose must be measured

Every count, size and class break in the published documentation came from a
query. `tools/distributions.sql` reruns all of them. After any rebuild, run it
and check the prose that cites it: a style whose legend lists a class the data
no longer holds is the most common visible defect in a catalog, and nothing in
CI catches it.

### Row group sizes are deliberately small

`gpio check` warns that 4, 64, 512 and 1,536 rows per group are "very low".
That guidance is written for scan-heavy analytics. This catalog is built for
single-feature lookups from a browser, and each size comes from measured
compressed bytes per row. See `docs/conformance.md`. Do not "fix" them.

### The conformance allow-list

`ACCEPTED` in `tests/test_conformance.py` ships empty. Never add an entry
without a matching row in `docs/conformance.md` giving the rule, where it
fires, why it is accepted, and the issue tracking its removal.

### Published agent guides

Every claim in a `catalog/**/AGENTS.md` is either quoted from a source or
measured from the data, and each one is tagged `[attested]`, `[researched]` or
`[derived]`. Every query in those files was run against the built data before
being written down. An invented join key or column name produces a confident
wrong answer that nothing downstream catches.

The per-collection `.portolan/metadata.yaml` files are the canonical home for
provenance and known issues. They are tracked and never published, and each
collection's `README.md` carries the human-facing rendering. Keep the two in
step.

### The links back to this repository

`catalog/catalog.json` carries a `vcs` link and an `issues` link, both absolute
and both pointing at `https://github.com/portolan-mirrors/geoboundaries-catalog`. The
repository sits outside the published catalog, so a relative href would resolve
against the public base URL and point at a bucket path that holds nothing.
