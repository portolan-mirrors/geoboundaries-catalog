# AGENTS.md — geoBoundaries CGAZ Global Administrative Boundaries

Guidance for AI agents and automated clients working with this catalog.

**One rule survives every edit to this file.** Every claim here is either quoted
from a source or measured from the data. If you cannot point at where a fact
came from, it does not belong in this file. An agent acting on an invented join
key or an invented column name produces a confident wrong answer, and nothing
downstream catches it.

Each factual claim is tagged with how it was established:
**[attested]** the publisher states it, with a link;
**[researched]** found outside the source's own metadata, with a link;
**[derived]** computed from the published data, with the query that computed it.

## What this catalog holds

Public root:
`https://data.source.coop/portolan-mirrors/geoboundaries-catalog/catalog.json`

| collection | rows | holds |
|---|---|---|
| [`adm0`](adm0/collection.json) | 218 | Country-level polygons, plus 20 disputed areas |
| [`adm1`](adm1/collection.json) | 3,224 | First-level units: states, provinces, regions |
| [`adm2`](adm2/collection.json) | 49,349 | Second-level units: counties, districts, municipalities |
| [`names`](names/collection.json) | 52,398 | Name search index across all three levels, one point per unit |

[geoBoundaries](https://www.geoboundaries.org/), built by the community and
[William & Mary geoLab](https://geolab.wm.edu/), produces the data and is the
authoritative source. Only the CGAZ global composite is carried here; the
per-country `gbOpen`, `gbHumanitarian` and `gbAuthoritative` releases are not.

**This is not a byte-for-byte mirror.** It repairs faults in the upstream
release and adds products geoBoundaries does not publish. Every deviation is
listed, with how to reproduce it and how to get the vanilla behaviour, in
[changes-from-upstream.md](changes-from-upstream.md). The short version:

- 38 double-encoded names are **repaired** in `shapeName` and `name`.
- 1,275 of 1,276 invalid geometries are **repaired** with `ST_MakeValid`.
- One all-NULL column, `id`, is **dropped**.
- The CRS is **assigned**: the upstream GeoPackages declare none.
- Measured columns, a bbox covering column, a Hilbert row order and small row
  groups are **added**.
- The `names` and `*_display` collections and assets are **ours**, with no
  upstream equivalent.

Nothing is filtered out. Every row and every attribute of the upstream release
is here, including the 20 disputed areas, the backfilled coarser-level rows
and the 37 rows with no name.

## Which geometry file to use

Three ways to get a shape out of this catalog, and picking the wrong one is
the difference between a map that feels instant and a browser tab that stops
responding.

| you want | read | why |
|---|---|---|
| To draw one unit's outline, now | `adm0/cgaz_adm0_display.parquet`, `adm1/cgaz_adm1_display.parquet` | Simplified. Canada is 528,021 coordinates at full resolution and 7,000-odd here |
| To draw thousands of units, or a basemap layer | the PMTiles archive | Tiled, so the browser only fetches what is on screen |
| To clip, measure, export, or analyse | `cgaz_adm{N}.parquet` | The real geometry. 1 to 1.8 MB per range request |
| To filter *another* dataset to a unit | the display file | Outward-biased on purpose; see below |

**ADM2 has no display file**, and that is a measurement rather than an
omission. Its geometry is already simplified upstream: the median unit is 82
coordinates, the 90th percentile 560, the 99th 2,837, and only 14 rows of
49,349 exceed 20,000 **[derived]**. Reading one unit from the full-resolution
ADM2 file is already sub-millisecond work. ADM0 is the opposite case: its
median unit is 21,583 coordinates, because CGAZ does not simplify that level
at all.

### The display files are outward-biased, and that matters

Geometry in a `*_display.parquet` is
`ST_Buffer(ST_SimplifyPreserveTopology(geom, tol), tol, 2)` with `tol` of 0.01
degrees. Simplification alone cuts corners *inward*, and a shape used as a
spatial filter that sits inside the true boundary silently drops features near
the edge. Buffering outward by the same distance makes the result contain the
original instead. Over-fetching is cheap; a missing edge feature is a wrong
answer.

So:

- **Neighbouring units overlap** in the margin. A point near a border can fall
  inside two display polygons.
- **Do not measure area** from them, **do not decide which side of a border a
  point is on** with them, and **do not publish a map** that claims they show
  a boundary.
- The buffer is **in degrees, so it is not isotropic on the ground**. One
  degree of latitude is about 111 km everywhere; one degree of longitude is
  111·cos(latitude) km. The 0.01 degree margin is about 1.1 km north-south
  everywhere, about 1.1 km east-west at the equator, and about 0.55 km
  east-west at 60° north. It is outward everywhere, which is the property that
  matters.

**Row *i* is the same unit in both files**, and so is row group *g*: the
display file is written with the same row count, the same row order and the
same row group boundaries as the full-resolution file. One byte-range plan
serves either.

## How a browser geocoder consumes this catalog

End to end, with no server. The mechanics, with runnable code, are in
[`names/AGENTS.md`](names/AGENTS.md); this is the shape of it.

1. **At focus, load the index.** `names/cgaz_names.parquet` is 3.9 MB.
   Measured on Node 22: the seven columns a search needs load in **117 ms**,
   all twelve in **250 ms** **[derived]**. Below about 5 MB this is the right
   call — one request, then every keystroke is local. Above that, or on a
   connection you do not trust, use the range-request path instead: the file
   is sorted by `name_norm`, so a typed prefix maps to a contiguous run of row
   groups. Over all 676 two-letter prefixes a prefix touches a **median of 1
   and at most 3** of the 35 row groups, each about 109 KiB **[derived]**. The
   footer plus page index is ~107,000 bytes, inside hyparquet's 512 KiB default
   prefetch, so one request plans the rest.
2. **Search the prefix.** Match on `name_norm`, which is case-folded and
   accent-stripped, so `zurich` finds `Zürich`. Rank with `area_km2` and
   disambiguate with `name_dupes` and `country_name`: 32 units are called
   Washington.
3. **Take `shape_id` and `level` from the hit.** Branch on `level`: levels 1
   and 2 join on `shape_id`, level 0 joins on `country`, because CGAZ ADM0
   publishes no `shapeID`.
4. **Draw the outline immediately from the display file**, at the row index
   the index gave you, or from its `bbox` if all you need is a camera move.
5. **Fetch full resolution in the background** if the user is going to export,
   clip or measure. It is one range request of 1 to 1.8 MB against the same
   row group number.
6. **Use the boundary as a spatial filter** for downloading some *other*
   dataset. This is where the outward bias earns its keep: the display polygon
   contains the true boundary, so a bbox or polygon filter built from it
   over-fetches slightly rather than silently dropping features along the
   edge.

## Start here

Column meanings, the traps, and worked queries live in the collection guides.
Read the one for the level you are querying:
[`adm0/AGENTS.md`](adm0/AGENTS.md),
[`adm1/AGENTS.md`](adm1/AGENTS.md),
[`adm2/AGENTS.md`](adm2/AGENTS.md),
[`names/AGENTS.md`](names/AGENTS.md).

Four traps account for most wrong answers against this catalog.

- **`shapeType` is not the level of the file.** CGAZ fills gaps with the next
  coarser level it has, so the ADM2 file holds 312 first-level units and 2
  whole countries, and all three files hold the same 20 disputed areas. Filter
  on `shapeType` when you want one kind of thing **[derived]**.
- **`shapeGroup` is not always an ISO code.** The 20 disputed-area rows carry
  `111` through `129` instead, except Western Sahara which uses `ESH`
  **[derived]**.
- **ADM0 has no `shapeID`.** The column does not exist in that file. Join at
  level 0 on `shapeGroup` **[derived]**.
- **Nothing links a unit to its parent subdivision.** See
  [join keys](#join-keys).

## Join keys

| from | to | on | uniqueness |
|---|---|---|---|
| `names` level 0 | `adm0` | `names.country = adm0.shapeGroup` | 1:1, 218 rows both sides |
| `names` level 1 | `adm1` | `names.shape_id = adm1.shapeID` | 1:1, `shapeID` unique in `adm1` |
| `names` level 2 | `adm2` | `names.shape_id = adm2.shapeID` | 1:1, `shapeID` unique in `adm2` |
| any boundary level | `adm0` | `shapeGroup` | many:1 |

`names.shape_id` is **NULL for every level-0 row**, so a single join on
`shape_id` silently drops all 218 countries and disputed areas. Branch on
`level` **[derived]**.

**There is no parent key between levels.** `shapeID` prefixes are per country
*and* per level: Afghanistan's ADM1 units all carry the prefix `12653393` and
its ADM2 units carry `17698898`, which are the two separate geoBoundaries
boundary IDs `AFG-ADM1-12653393` and `AFG-ADM2-17698898`
**[attested, [API documentation](https://www.geoboundaries.org/api.html);
derived, verified against that API]**. So an ADM2 row cannot be matched to the
ADM1 row containing it by any published column. Reconstructing the hierarchy
means a spatial join, and on simplified clipped geometry that will misassign
units along shared edges. This is the largest gap in the dataset for anyone
building a hierarchical gazetteer.

`shapeGroup` is the only key that works across all four collections, and all
218 values appear in all three boundary files **[derived]**:

```sql
SELECT count(*) FROM 'adm0/cgaz_adm0.parquet' a
WHERE a.shapeGroup NOT IN (SELECT shapeGroup FROM 'adm1/cgaz_adm1.parquet');
-- 0
```

## How to read it

Everything is readable in place over HTTPS, with no credentials.

```sql
INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;

SELECT shapeType, count(*) AS n
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm2/cgaz_adm2.parquet'
GROUP BY 1 ORDER BY 2 DESC;
```
```
ADM2  49015
ADM1    312
DISP     20
ADM0      2
```

The PMTiles archives are for drawing, one per boundary level plus one for the
index points. The GeoParquet files are for querying. Do not download a
GeoParquet file to draw a map: the ADM0 file is 97 MB and its PMTiles archive
is 7 MB.

## How this catalog was built

Five scripts in the
[source repository](https://github.com/portolan-mirrors/geoboundaries-catalog/tree/main/tools),
each runnable on its own, with no step hidden in a notebook:

```bash
python3 tools/fetch_sources.py      # 547 MB of GeoPackages from upstream
python3 tools/build_boundaries.py   # -> 3 GeoParquet files, ~70 s
python3 tools/build_names.py        # -> the search index, ~5 s
python3 tools/build_display.py      # -> 2 display sidecars, ~30 s
python3 tools/build_pmtiles.py      # -> 4 PMTiles archives, ~12 min
python3 tools/make_styles.py        # -> 15 style JSONs
python3 tools/make_thumbnails.py    # -> 4 thumbnails
python3 tools/make_collections.py   # -> 4 collection.json
python3 tools/make_changes_doc.py   # -> this catalog's deviation record
```

The tool chosen at each step, and why:

| step | tool | why that one |
|---|---|---|
| GeoPackage to Parquet | `ogr2ogr -f Parquet -a_srs EPSG:4326` | About a second per level, against minutes for a DuckDB spatial scan of the same file. `-a_srs` is what repairs the missing CRS. |
| Measures, Hilbert order | DuckDB 1.4 with `spatial` | `ST_Hilbert` over a fixed whole-globe envelope, so all four files sit on one comparable curve. |
| The Parquet write | PyArrow | The only writer here that honours an exact small row group size and writes the page index. `gpio sort hilbert` snaps row groups up to a 2,048-row writer vector, which would put all 218 ADM0 rows in one group. |
| Vector tiles | `ogr2ogr -f GeoJSONSeq` piped to `tippecanoe` | No intermediate GeoJSON on disk. `--detect-shared-borders` keeps a shared edge between neighbours simplified identically, so the composite does not open hairline gaps. |
| Geometry repair | DuckDB `ST_MakeValid` + `ST_CollectionExtract(..., 3)` | Applied only where `ST_IsValid` is false, so valid rows pass through byte for byte. |
| Display geometry | DuckDB `ST_SimplifyPreserveTopology` then `ST_Buffer` | Buffering outward is what makes the result safe as a spatial filter. 2 quadrant segments, or the buffer puts back the coordinates simplification removed. |
| Validation | `gpq validate`, `rashid`, `stac-check` | `gpq validate` passes 20 of 20 checks on all six GeoParquet files. |

`tools/distributions.sql` reruns every distribution behind every style class
break and every count quoted in this catalog's prose.

## Quirks that produce silently wrong answers

**The GeoParquet covering column is named `bbox`, and GDAL would have named it
`geometry_bbox`.** This catalog writes `bbox`. Read the name out of the `geo`
metadata rather than assuming either.

**Every file is CRS84 and nothing was reprojected.** The upstream GeoPackages
declare `srs_id = 0`, "Undefined geographic SRS", for coordinates that are
plainly degrees of longitude and latitude **[derived]**, so the build *assigns*
EPSG:4326. Lengths and areas computed in degrees are meaningless; the files
carry `area_km2` and `perimeter_km` computed geodesically so you do not have to
reproject.

**`area_km2` is measured on simplified geometry at ADM1 and ADM2.** It is
reproducible, not official. ADM0 is unsimplified, so its areas land close to
published figures.

**The source `id` column is gone.** All three upstream GeoPackages carry an
`id` column that is NULL in every row, and the upstream build script lists `id`
among the fields it drops, so the surviving empty column is a conversion
artifact **[derived; attested, the `-drop fields=` list in
[gbCGAZBuild.py](https://github.com/wmgeolab/geoBoundaryBot/blob/main/gbCGAZBuild.py)]**.
It is not carried here. Nothing else was dropped.

**These are not self-represented boundaries.** CGAZ clips every outline to US
Department of State international boundaries and replaces contested ground with
20 separate polygons **[attested,
[globalDownloads.html](https://www.geoboundaries.org/globalDownloads.html)]**.
geoBoundaries' per-country releases represent each nation "as they would
represent themselves" and are a different product.

## Structure

Assets and structural links resolve relative to the object that carries them.

## A sibling catalog, and what it trades

[cn-geocoder-overture](https://github.com/portolan-mirrors/cn-geocoder-overture)
is a sibling catalog built to the same shape from Overture Maps divisions. It
is **experimental**, and it exists because this catalog stops at the second
administrative level: Overture carries cities and localities below that, and
carries names in many languages where geoBoundaries carries one. Its future
home is the unlisted Source Cooperative repository
`portolan-mirrors/cn-geocoder-overture`.

A widget can be pointed at either index; they are built to the same column
contract. **The deciding factor is the license, not the coverage.** This
catalog is CC BY 4.0: attribution only, and you can put it in a closed product
as long as you credit geoBoundaries. Overture divisions carry ODbL, which is
share-alike: a derived database has to be released under the same terms. Pick
this catalog when attribution is the only obligation you want to take on, and
the Overture one when you need the richer coverage and can live with
share-alike.

## Future work

**ADM3 and ADM4.** CGAZ stops at ADM2, but geoBoundaries' per-country `gbOpen`
releases go to ADM5 for some countries. A global ADM3/ADM4 composite built
from those is under evaluation; a coverage survey is in progress. It would not
be CGAZ — there is no upstream composite at those levels, so the clipping and
gap-filling CGAZ does would have to be done here, which changes what the data
is. Nothing is promised.

## Citation

Using this data requires attribution **[attested,
[geoboundaries.org](https://www.geoboundaries.org/)]**. In written work, cite:

> Runfola, D. et al. (2020) geoBoundaries: A global database of political
> administrative boundaries. PLoS ONE 15(4): e0231866.
> [https://doi.org/10.1371/journal.pone.0231866](https://doi.org/10.1371/journal.pone.0231866)

On the web, show the name "geoBoundaries" linked to
[www.geoboundaries.org](https://www.geoboundaries.org/) somewhere prominent on
the page that uses the boundaries.
