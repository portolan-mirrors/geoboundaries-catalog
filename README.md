# geoBoundaries CGAZ, mirrored

A git-backed [Portolan](https://www.portolan-sdi.org/) catalog that mirrors
geoBoundaries' **Comprehensive Global Administrative Zones** composite as
cloud-native GeoParquet and PMTiles.

Published at
[source.coop/portolan-mirrors/geoboundaries-catalog](https://source.coop/portolan-mirrors/geoboundaries-catalog).
The catalog metadata lives in this repository; the data lives in object storage
beside it.

[geoBoundaries](https://www.geoboundaries.org/), built by the community and
[William & Mary geoLab](https://geolab.wm.edu/), produces the data and remains
the authoritative source. This repository republishes it; it adds no boundaries
and changes no geometry.

> **This catalog is not a byte-for-byte mirror of geoBoundaries.** It repairs
> faults in the upstream release and adds products geoBoundaries does not
> publish. Every deviation is listed, with how to reproduce it and how to get
> the vanilla behaviour, in
> [docs/changes-from-upstream.md](docs/changes-from-upstream.md).

## What it publishes

| collection | rows | GeoParquet | PMTiles |
|---|---|---|---|
| `adm0` | 218 | 104 MB, 218 row groups of 1 row | 7.1 MB, z0-6 |
| `adm1` | 3,224 | 81 MB, 202 row groups of 16 rows | 17 MB, z0-7 |
| `adm2` | 49,349 | 104 MB, 193 row groups of 256 rows | 101 MB, z0-9 |
| `names` | 52,398 | 3.9 MB, 35 row groups of 1,536 rows | 12 MB, z0-8 |

Every boundary collection carries a second GeoParquet file,
`*_display.parquet`, with the same rows in the same order and the same row
group boundaries, and geometry simplified and buffered outward: 7.5 MB, 13 MB
and 42 MB against 104 MB, 81 MB and 104 MB. ADM2 gained its display file on
2026-11-12, reversing an earlier decision that was right about the wrong
quantity: ADM2 geometry is already simplified upstream, so *decoding* one unit
was never slow, but a browser does not decode one unit from an isolated byte
range — it pulls the whole row group's geometry column chunk, and that was a
median of 1.35 MB and 2.1 s against the live catalog.

The three boundary levels cover the globe seamlessly. `names` is the gazetteer
index: one row per named unit across all three levels, sorted by a folded form
of the name, built so a static browser client can turn a typed name into a
`shapeID`, an extent and a point.

**The row group sizes are the reason this catalog exists.** The CGAZ mirror it
replaces put all 49,349 ADM2 rows in one row group, so fetching a single
municipality's geometry meant reading the whole geometry column chunk.
hyparquet, the reader a browser uses, has no sub-chunk read, so one feature
costs one row group — but shrinking row groups is not free, because the
trailing metadata a client reads before any data carries one record per column
per row group. Each level's size therefore minimizes the sum of the two, which
is what a client's first select costs: `tools/rowgroup_sweep.py` chose 1, 16
and 256 rows. GeoParquet 1.1 bbox covering metadata, a Hilbert row order and a
Parquet page index on every column let a reader find the right group without
decoding any geometry.

## Build it

The data is hundreds of megabytes and never enters git. The pipeline stages it
in a sibling directory, `../geoboundaries-staging`, which
`catalog.publish.yaml` names as `data_dir`. Override the location with
`GB_STAGING`.

```bash
python3 tools/fetch_sources.py      # 547 MB of GeoPackages from upstream
python3 tools/build_boundaries.py   # -> 3 GeoParquet files, ~70 s
python3 tools/build_names.py        # -> the search index, ~5 s
python3 tools/build_display.py      # -> 3 display sidecars
python3 tools/build_pmtiles.py      # -> 4 PMTiles archives, ~12 min
python3 tools/make_styles.py        # -> 15 style JSONs, into catalog/
python3 tools/make_thumbnails.py    # -> 4 thumbnails, into catalog/
python3 tools/make_collections.py   # -> 4 collection.json, into catalog/
python3 tools/make_changes_doc.py   # -> the published deviation record
```

Needs `ogr2ogr` (GDAL 3.10+), `tippecanoe`, `pmtiles`, and Python with
`duckdb`, `pyarrow`, `numpy`, `geopandas` and `matplotlib`.

`make_collections.py` runs last because it reads row counts, bounding boxes,
file sizes and checksums out of the built files, so every number in the
published metadata is measured rather than typed.

`tools/distributions.sql` reruns every distribution behind every style class
break. Run it after any rebuild: if a count moved, the styles and the prose
citing it are now wrong.

| Path | What it is |
|---|---|
| `catalog/` | The published tree, synced 1:1 to object storage |
| `catalog/*/.portolan/metadata.yaml` | Provenance and known issues per collection. Tracked, never published |
| `docs/changes-from-upstream.md` | Every deviation from vanilla geoBoundaries. Copied into `catalog/` by `tools/make_changes_doc.py` |
| `catalog.publish.yaml` | Where it publishes, and under what public URL |
| `tools/` | The pipeline, and the publisher |
| `tests/` | The gates CI runs on every pull request |
| `docs/conformance.md` | Any validator finding this catalog accepts, and why |

**`catalog/` is the published catalog.** Everything in it is published except
dot-directories. Everything outside it never is, and `tools/publish.py` has no
flag that widens that.

## Publish

```bash
python3 tools/publish.py             # dry run: what metadata would change
python3 tools/publish.py --confirm   # upload the catalog; needs AWS credentials
python3 tools/upload_data.py         # dry run: what data would change
python3 tools/upload_data.py --confirm
```

Neither ever deletes. Removing a file from `catalog/` does not unpublish it.

## Test

```bash
CI_LIGHT=1 python3 tests/run_all.py
```

`CI_LIGHT=1` exempts asset and link hrefs with a data suffix from the link
check, because the bytes live in object storage rather than git. CI sets it for
the same reason. Leave it unset only when the staging tree is mounted under
`catalog/`, which it never is here.

| Gate | What it checks |
|---|---|
| `test_links.py` | Every relative link and asset href resolves |
| `test_styles.py` | Every style class exists in the built data. Skips without the staging tree |
| `test_changes_doc.py` | The published deviation record matches its source in `docs/` |
| `test_publish.py` | Nothing outside `catalog/` can be uploaded |
| `test_upload_data.py` | Only staged files with an allowed suffix upload |
| `test_stac_valid.py` | Valid STAC 1.1.0, via `stac-check` |
| `test_conformance.py` | Portolan conformance, via `rashid` |

## License

Apache-2.0 for the tooling in this repository. The data is **CC-BY-4.0** from
geoBoundaries and attribution is required; the terms and the required citation
are in [catalog/README.md](catalog/README.md).
