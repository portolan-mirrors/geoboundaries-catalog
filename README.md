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

## What it publishes

| collection | rows | GeoParquet | PMTiles |
|---|---|---|---|
| `adm0` | 218 | 97 MB, 55 row groups of 4 rows | 7.1 MB, z0-6 |
| `adm1` | 3,224 | 76 MB, 51 row groups of 64 rows | 17 MB, z0-7 |
| `adm2` | 49,349 | 101 MB, 97 row groups of 512 rows | 101 MB, z0-9 |
| `names` | 52,398 | 3.6 MB, 35 row groups of 1,536 rows | 12 MB, z0-8 |

The three boundary levels cover the globe seamlessly. `names` is a search
sidecar: one row per named unit across all three levels, sorted by a folded
form of the name, built so a static browser client can turn a typed name into a
`shapeID`, an extent and a point.

**The row group sizes are the reason this catalog exists.** The CGAZ mirror it
replaces put all 49,349 ADM2 rows in one row group, so fetching a single
municipality's geometry meant reading the whole geometry column chunk. Each
level here gets a row group size measured from its own compressed bytes per
row, landing every group between 1.0 and 1.8 MB, with GeoParquet 1.1 bbox
covering metadata, a Hilbert row order and a Parquet page index on every
column so a reader can find the right group without decoding any geometry.

## Build it

The data is hundreds of megabytes and never enters git. The pipeline stages it
in a sibling directory, `../geoboundaries-staging`, which
`catalog.publish.yaml` names as `data_dir`. Override the location with
`GB_STAGING`.

```bash
python3 tools/fetch_sources.py      # 547 MB of GeoPackages from upstream
python3 tools/build_boundaries.py   # -> 3 GeoParquet files, ~70 s
python3 tools/build_names.py        # -> the search index, ~5 s
python3 tools/build_pmtiles.py      # -> 4 PMTiles archives, ~12 min
python3 tools/make_styles.py        # -> 15 style JSONs, into catalog/
python3 tools/make_thumbnails.py    # -> 4 thumbnails, into catalog/
python3 tools/make_collections.py   # -> 4 collection.json, into catalog/
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
| `test_publish.py` | Nothing outside `catalog/` can be uploaded |
| `test_upload_data.py` | Only staged files with an allowed suffix upload |
| `test_stac_valid.py` | Valid STAC 1.1.0, via `stac-check` |
| `test_conformance.py` | Portolan conformance, via `rashid` |

## License

Apache-2.0 for the tooling in this repository. The data is **CC-BY-4.0** from
geoBoundaries and attribution is required; the terms and the required citation
are in [catalog/README.md](catalog/README.md).
