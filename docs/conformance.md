# Portolan Conformance

Conformance means passing [rashid](https://github.com/portolan-sdi/rashid),
not claiming to conform, so it runs in CI:

```bash
python3 tests/test_conformance.py
```

That gate fails on any error-severity finding whose rule is not listed below.
The list starts empty and it must never grow without a row here. A known
deviation with an issue number is a debt someone can pay off. A silently
widened allow-list is a false claim about what this catalog conforms to.

## The rashid version floor

The gate needs rashid `>=0.1.5,<0.2.0`. It reads `rashid --version` and fails
outside that range. It also fails when rashid is absent, and prints the install
command. A skip would report a green run for a catalog that no validator read.

The floor is 0.1.5 because rules PTL-LNK-007, PTL-LNK-008, PTL-LNK-009 and
PTL-AST-006 do not exist below it. The gate asserts all four. An older rashid
reports a pass for a catalog that it never checked against them. The same range
is in `portolan-cli/pyproject.toml` and in the CI install step.

The upper bound stops an unreviewed 0.2 rule set from changing what this gate
means. Raise both bounds together when you move to 0.2, and read the new rules
first.

This file also records workarounds for the other validator CI runs. Those are
not conformance debts, because the catalog is correct and the validator is not.
They live here so nobody has to read CI code to find out why a gate skips
something.

## Accepted deviations

None.

<!--
When you accept one, add a row and a section explaining it, like this:

| Rule | Where | Why accepted | Tracking |
|---|---|---|---|
| PTL-VIZ-001 | all thumbnails | WebP is not yet permitted; the size saving is 4x | portolan-spec#121 |

Then add the rule id to ACCEPTED in tests/test_conformance.py. Both, or
neither.
-->

## Advisory findings this catalog does not act on

These are not deviations. `rashid` reports no error-severity finding against
this catalog, and the `ACCEPTED` list above is empty. The entries below are
advisory output from `portolan check` and from `gpio check`, recorded here so
nobody has to rediscover the reasoning.

### PTL-PRO-002: no `canonical` link on the mirror collections

`portolan check` suggests a `rel: canonical` link on every mirror collection,
"if the upstream publishes its own STAC catalog". geoBoundaries publishes
GeoJSON, Shapefile, GeoPackage and a JSON metadata API, and no STAC. There is
therefore no canonical STAC object to point at, and the `via` link to
[the CGAZ download page](https://www.geoboundaries.org/globalDownloads.html)
plus the `source-gpkg` asset carry the provenance instead. Add a `canonical`
link if geoBoundaries ever publishes STAC.

### `portolan check`: "8 registered asset(s) are missing from disk"

The GeoParquet and PMTiles assets are not in the repository, by design. They
are built into `../geoboundaries-staging/publish` and uploaded by
`tools/upload_data.py`. `portolan check` walks the metadata tree and cannot
see them. The same split is why `tests/test_links.py` takes `CI_LIGHT=1`.

### `gpio check`: "row count per group is very low"

`gpio check` wants 10,000 to 200,000 rows per row group and warns about all
four files here, which use 4, 64, 512 and 1,536. That guidance is written for
scan-heavy analytics, where a large row group amortizes per-group overhead
across a full-table read.

This catalog exists because the CGAZ mirror it replaces followed that
guidance: all 49,349 ADM2 rows in one row group, so fetching one
municipality's geometry meant reading the whole geometry column chunk. Each
size here was set from the file's measured compressed bytes per row so that a
row group is 1.0 to 1.8 MB, which is what one single-feature range request
costs. The search index targets 100-150 KiB per group instead, measured
against prefix-lookup latency.

The tradeoff is real and accepted: a full-table scan of these files reads more
footer metadata than it would at 50,000 rows per group. The ADM2 footer is
226,817 bytes, which is 0.2% of the file.

### The `display` assets use the `overview` role

Each boundary collection with a display sidecar publishes it as
`"roles": ["data", "overview"]`. `overview` is STAC's common role for a
reduced-resolution version of the data asset, which is what a simplified
geometry file is; the Portolan profile does not define a role of its own for
this case. The plain `data` role stays on the verbatim full-resolution file,
so a client that only understands `data` gets the real geometry rather than a
buffered approximation. If the Portolan spec later defines a better role, move
to it and record the change in docs/changes-from-upstream.md.

### Thumbnails are not chiitiler renders

The canonical thumbnail path renders `styles/default.json` through MapLibre GL
Native with chiitiler. That needs a clone of the chiitiler repository, which
was not available in the environment this catalog was built in.
`tools/make_thumbnails.py` instead parses the `step` or `match` expression out
of each collection's own `styles/default.json` and colours the features by it,
so the thumbnail and the legend the browser derives agree. What is missing is
the basemap and MapLibre's line rendering. Regenerate with chiitiler when it
is available; the asset hrefs and types do not change.

## Validator workarounds

### stac-check reports a dialect crash on every collection

`tests/test_stac_valid.py` exempts one stac-check failure:

```
'list' object has no attribute 'get'
[Schema: https://schemas.portolan-sdi.org/portolan/vX.Y.Z/schema.json]. Error in Extensions.
```

The Portolan schema is valid draft-07, and rashid validates catalogs against it
cleanly. `stac-validator`, which stac-check uses, hardcodes the JSON Schema
2020-12 dialect and ignores the `$schema` a schema declares. The profile schema
uses the draft-07 tuple form of `items` in `valid_bbox`, which means something
different under 2020-12, so the library raises instead of validating.

Tracked upstream at <https://github.com/stac-utils/stac-check/issues/159>,
and on the Portolan side at
<https://github.com/portolan-sdi/portolan-spec/issues/157>.

The exemption matches that exact message, and only when the failing schema is a
Portolan profile schema. Every other stac-check error still fails the build,
and the gate prints how many objects took the exemption.

The exemption expires on its own. The gate fails once stac-check stops emitting
the crash on a collection or item that declares the profile schema, and tells
you to delete both the exemption and this section. CI installs stac-check
unpinned, so the next release triggers that without anyone watching for it.

`tests/test_stac_valid.py` also fails when stac-check is absent, and prints the
install command. It takes no version floor and no pin. The rashid floor exists
because that gate asserts four named rules. This gate asserts no stac-check
rule. It needs the opposite property. A pin holds the exemption open after the
upstream fix ships.
