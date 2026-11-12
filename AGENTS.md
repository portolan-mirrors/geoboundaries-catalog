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
works in `../geoboundaries-staging`, outside the repository: 4.1 GB in all,
of which `publish/` is the 471 MB that `tools/upload_data.py` carries to the
bucket and the rest is the upstream GeoPackages and the intermediate files. Git keeps every version of a
binary forever and deleting it later reclaims nothing.

### Edit the generator, not the generated file

Two kinds of file under `catalog/` are generated and will be overwritten:

| generated | by |
|---|---|
| `catalog/*/collection.json` | `tools/make_collections.py` |
| `catalog/*/styles/*.json` | `tools/make_styles.py` |
| `catalog/*/*.thumb.png` | `tools/make_thumbnails.py` |
| `catalog/changes-from-upstream.md` | `tools/make_changes_doc.py`, from `docs/changes-from-upstream.md` |

Everything else under `catalog/` is hand-written: `catalog.json`, every
`README.md`, every `AGENTS.md`, `llms.txt`. The collection READMEs are *not*
produced by `portolan readme`; this repository publishes with its own
`tools/publish.py` and does not run the Portolan CLI, so running
`portolan readme` here would replace hand-written prose with a generated
skeleton.

### This catalog repairs its source, and says so everywhere

It is not a byte-for-byte mirror. It repairs double-encoded names and invalid
geometry, assigns the CRS the upstream files omit, and adds products
geoBoundaries does not publish. That is a policy, not an accident, and it only
works if it is stated loudly: a consumer who assumes they have vanilla
geoBoundaries and does not is worse off than one who has vanilla data.

`docs/changes-from-upstream.md` is the complete record and is **authoritative**.
Every entry needs what changed, why, how to reproduce it, and how to get the
vanilla behaviour. `tools/make_changes_doc.py` copies it into `catalog/` so it
reaches object storage, where most readers meet this catalog, and
`tests/test_changes_doc.py` fails when the copy drifts.

**Any new deviation goes in that file in the same commit that introduces it.**
A repair nobody documented is indistinguishable from a bug.

### Provenance lives in metadata.yaml first

`catalog/*/.portolan/metadata.yaml` is the canonical home for `source_url`,
`attribution`, `processing_notes` and `known_issues`. Edit it first, then
bring the collection's `README.md` into line. The READMEs here are
hand-written rather than produced by `portolan readme`, because that command
would replace this prose with a generated skeleton; the rule that metadata.yaml
leads still holds.

### Numbers in prose must be measured

Every count, size and class break in the published documentation came from a
query. `tools/distributions.sql` reruns all of them. After any rebuild, run it
and check the prose that cites it: a style whose legend lists a class the data
no longer holds is the most common visible defect in a catalog, and nothing in
CI catches it.

### Row group sizes are deliberately small

`gpio check` warns that 1, 16, 256 and 1,536 rows per group are "very low".
That guidance is written for scan-heavy analytics. This catalog is built for
single-feature lookups from a browser, and each size comes from a measured
sweep rather than from convention. hyparquet has no sub-chunk read, so one
feature costs one whole row group; but the thrift footer and the page index
both carry a record per column per row group, and a range client reads them
before any data. `tools/rowgroup_sweep.py` minimizes the sum — trailing bytes
plus one row group — which is what a client's first select costs. See
`docs/conformance.md`. Do not "fix" them.

In the boundary and display files, row group statistics are written only for
the columns a client can prune on: `shapeID`, `shapeGroup` and the four `bbox`
struct leaves. The list is `PRUNABLE_STATS` in `tools/gbcommon.py`, and the
comment there explains why `bbox` has to be named by its leaf paths. Do not
widen it, and do not apply it to the names index, which needs `name_norm`
statistics for prefix pruning. The boundary files are
Hilbert-sorted, so `shapeName`, `shapeType`, `country_units`, `area_km2`,
`perimeter_km` and `compactness` have min/max ranges that overlap across
essentially every row group and prune nothing, while a min and a max of
`shapeName` is two strings per group per file.

The `*_display.parquet` files deliberately repeat the full-resolution file's
row group sizes rather than picking their own. Alignment is the feature: row
*i* and row group *g* have to mean the same unit in both files, or a client
cannot reuse one byte-range plan across them. All three boundary levels now
carry one.

### The Hilbert order needs its tiebreaker

`tools/build_boundaries.py`'s `ORDER BY ST_Hilbert(...)` carries a
`shapeGroup, shapeName, shapeID` tiebreaker and forces
`preserve_insertion_order = true`. The Hilbert key alone is not a total order,
so without a tiebreaker a rebuild can reorder rows arbitrarily — and a rebuild
that reorders rows stales every display file and every `geometry_ref` in the
names index at once. The sibling Overture catalog hit exactly this on 4,724
locality rows. Do not remove either.

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
