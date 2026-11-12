# geoBoundaries CGAZ Global Administrative Boundaries

Every administrative boundary in the geoBoundaries **Comprehensive Global
Administrative Zones** composite, republished as cloud-native GeoParquet and
PMTiles you can query and draw without downloading anything.

[geoBoundaries](https://www.geoboundaries.org/), built by the community and
[William & Mary geoLab](https://geolab.wm.edu/), produces the data and remains
the authoritative source.

> **This is not a byte-for-byte mirror.** It repairs faults in the upstream
> release — 38 double-encoded names, 1,275 invalid geometries, a missing CRS —
> and adds products geoBoundaries does not publish: a name search index and
> simplified display geometry. Every deviation, with how to reproduce it and
> how to get the vanilla behaviour instead, is in
> **[changes-from-upstream.md](changes-from-upstream.md)**.

## What is here

Four collections.

| collection | rows | full | display | what it is |
|---|---|---|---|---|
| `adm0` | 218 | 104 MB | 7.5 MB | Country outlines, plus 20 disputed areas |
| `adm1` | 3,224 | 81 MB | 13 MB | States, provinces, regions, governorates |
| `adm2` | 49,349 | 104 MB | 42 MB | Counties, districts, municipalities, communes |
| `names` | 52,398 | 3.9 MB | — | A name search index across all three levels |

The three boundary levels cover the globe seamlessly: every one of the 218
country codes appears at every level, because where a country has no
first- or second-level data CGAZ carries its coarser polygon up instead. The
`shapeType` column says which you are actually looking at.

Each boundary collection is GeoParquet 1.1 with bbox covering metadata, sorted
along a Hilbert curve, and cut into small row groups — 218, 202 and 193 of
them, holding 1, 16 and 256 rows — so a client fetches one unit's geometry in
a single range request of 250 to 325 KB instead of pulling the whole file. At
ADM0 that is one row group per country.

`names` is the piece built for autocomplete: one row per named unit, sorted by
a folded form of the name, 3.9 MB in total. Load it whole in about a quarter of
a second, or resolve a typed prefix from one or two 109 KiB row groups by range
request. It carries the `shapeID` that joins back to the geometry, the extent
to fly a map to, a `geometry_ref` pointer straight at the row group holding the
geometry, and a count of how many other units share the same name.

A PMTiles archive accompanies every collection, for drawing many units at once.

**Every** boundary collection carries a **display** file: the same rows in the
same order in the same row groups, with simplified geometry, for drawing one
unit's outline without fetching the full-resolution row group. One country's
outline is about 10 KB there against 250 KB in the full file, one ADM1 unit
37 KB against 220 KB, one ADM2 unit 151 KB against 325 KB. Canada is 528,021
coordinates at full resolution and 68,973 in the display file.

ADM2 gained its display file on 2026-11-12, reversing an earlier decision that
was right about the wrong quantity. ADM2 geometry is already simplified
upstream — its median unit is 82 coordinates — so *decoding* one was never
slow. But a browser does not decode one unit from an isolated byte range:
hyparquet has no sub-chunk read, so fetching one ADM2 feature pulls that row
group's entire geometry column chunk, and against the live catalog that was a
median of 1.35 MB and 2.1 seconds, worst case 3.5 MB and 4.3 seconds. The cost
was bytes per row group, and it is the tail that fills a row group — the 99th
percentile at 2,837 coordinates and the 14 units above 20,000 — not the median
82.

**The display geometry is buffered outward** by the distance it was simplified
by, so it contains the true boundary rather than cutting inside it. That makes
it safe to use as a spatial filter for downloading some *other* dataset: you
over-fetch a little rather than silently dropping features along the edge.
Every feature at every level retains at least 99% of its original area — worst
cases 99.95% at ADM0, 99.87% at ADM1 and 99.15% at ADM2. The cost is that
neighbouring units overlap in the margin, so it is a display and filter shape,
not a cartographic boundary. Do not measure area from it.

Per-country geoBoundaries releases (`gbOpen`, `gbHumanitarian`,
`gbAuthoritative`) are **not** mirrored here. Those are full-resolution and
represent each country as it represents itself; CGAZ is a different product.

## The upstream data vs our optimized files — why both exist and when to use which

Every collection here links the **upstream GeoPackage** it was built from, as
a `source-gpkg` asset pointing at
`github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/`, with the size
and SHA-256 of the exact bytes this build consumed. The `names` collection
links all three, because it is derived from all three levels. Nothing here
asks you to take this mirror's word for its own contents.

**Use the upstream GeoPackages when** you want the authoritative bytes, a
whole level at once for analysis in QGIS or GDAL or DuckDB, a format this
catalog does not publish, or a second opinion on anything this catalog claims.
They are the product of record: geoBoundaries publishes them, cites them, and
is who you should credit.

**Use the files here when** a browser is doing the reading. That is the only
thing they are better at, and they are much better at it:

| | upstream CGAZ GeoPackage | this catalog |
|---|---|---|
| format | GeoPackage (SQLite) | GeoParquet 1.1, zstd, with bbox covering |
| one unit's geometry | read the whole file | one range request, 10–325 KB |
| find a place by name | scan the layer | sorted name index, 3.9 MB or one 109 KiB row group |
| row groups | n/a | 1, 16 and 256 rows, sized by what one select costs |
| footer read | n/a | exact `footer_bytes` in `names/index.json`, one request |
| simplified outlines | none | a display file per level, buffered outward |
| tiles | none | PMTiles per collection |
| CRS | declared `srs_id = 0` | EPSG:4326 assigned |
| names | 38 rows double-encoded | repaired |
| geometry | 843 invalid polygons | repaired with `ST_MakeValid` |

A GeoPackage is a SQLite database. It has no HTTP range story at all: a
browser cannot ask it for one country without downloading all 155 MB, and
there is no column-chunk layout to ask with. That — not reachability, and not
anything wrong with the upstream files — is why these exist.

The repairs in the last three rows are the one place this catalog is *not* a
faithful mirror, and they are why you should read
[changes-from-upstream.md](changes-from-upstream.md) before you treat anything
here as vanilla geoBoundaries. Each one is recorded there with how to
reproduce it and how to get the upstream behaviour back.

## License

**CC-BY-4.0.** geoBoundaries states:

> the geoBoundaries Global Database of Political Administrative Boundaries
> Database is an online, open license (CC BY 4.0) resource of information on
> administrative boundaries (i.e., state, county) for every country in the
> world. [...] All boundaries are available to view or download in common file
> formats; the only requirement for use is acknowledgement.

— [geoboundaries.org](https://www.geoboundaries.org/), which also links the
[CC BY 4.0 license text](https://creativecommons.org/licenses/by/4.0/).

**Attribution is required.** geoBoundaries asks for it in three forms, and this
is their wording:

- In written work: cite the PLoS ONE paper.

  > Runfola, D. et al. (2020) geoBoundaries: A global database of political
  > administrative boundaries. PLoS ONE 15(4): e0231866.
  > [https://doi.org/10.1371/journal.pone.0231866](https://doi.org/10.1371/journal.pone.0231866)

- On the web: "we ask that you put the name 'geoBoundaries' with a link back to
  this website, [www.geoboundaries.org](https://www.geoboundaries.org/),
  somewhere prominent on the page that uses the boundaries."
- In other products: "we ask that you put the name 'geoBoundaries' somewhere
  prominent in the product, for example in the credits or as a link in the help
  menu."

One inconsistency is worth recording: the
[geoBoundaries repository README](https://github.com/wmgeolab/geoBoundaries)
describes the project as "open license (CC BY 4.0 / ODbL)", where the website
says CC BY 4.0 throughout. The website is treated as authoritative here, and
CGAZ is built from `gbOpen`, which geoBoundaries describes as "CC-BY 4.0
compliant". Individual source boundaries carry their own upstream licenses,
which the geoBoundaries API reports per boundary; CGAZ does not carry that
field, so per-unit license provenance is not recoverable from these files.

## Provenance

Built from the three CGAZ GeoPackages in the geoBoundaries core repository:

- [geoBoundariesCGAZ_ADM0.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM0.gpkg) (162 MB)
- [geoBoundariesCGAZ_ADM1.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM1.gpkg) (144 MB)
- [geoBoundariesCGAZ_ADM2.gpkg](https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM2.gpkg) (241 MB)

downloaded 2026-11-12. CGAZ is served from the default branch through git-lfs,
so a URL does not pin a version. The release mirrored here is commit
[`4004e96`](https://github.com/wmgeolab/geoBoundaries/commit/4004e96433a2bdc54cac2b88d7d2e694c89cb818)
of 2024-04-20, the last commit that changed any file under
`releaseData/CGAZ`. The newest tagged geoBoundaries release, v6.0.0, is older
than that.

geoBoundaries describes CGAZ as:

> A global composite of the SSC ADM0, ADM1 and ADM2, clipped to international
> boundaries (US Department of State), with gaps filled between borders.

— [geoBoundaries README](https://github.com/wmgeolab/geoBoundaries), and on the
[download page](https://www.geoboundaries.org/globalDownloads.html):
"extensive simplification is performed [...] disputed areas are removed and
replaced with polygons following US Department of State definitions."

Nothing is filtered, reclassified or reprojected here. Every row and every
attribute geoBoundaries publishes is carried, except one column that is NULL in
every row of every file. The additions are measured: geodesic area and
perimeter, a shape-compactness ratio, unit counts per country, and a bbox
covering struct. Each collection's `.portolan/metadata.yaml` in the
[repository](https://github.com/portolan-mirrors/geoboundaries-catalog) records the
complete transform list and the known issues.

The pipeline is five scripts, each runnable on its own:
[fetch_sources.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/fetch_sources.py),
[build_boundaries.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_boundaries.py),
[build_names.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_names.py),
[build_pmtiles.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/build_pmtiles.py)
and
[make_styles.py](https://github.com/portolan-mirrors/geoboundaries-catalog/blob/main/tools/make_styles.py).

## Using it from a browser

This catalog is shaped for a static client with no server — the search half of
a geocoder, running entirely on range requests. End to end:

0. **Fetch [`names/index.json`](names/index.json) first.** It is a few
   kilobytes and it carries every number the rest of this list needs: the URL,
   size, row count, row group count and `row_group_rows` of every file, and
   two exact metadata sizes per file. `footer_bytes` is the whole trailing
   span, thrift footer plus page index, so one range request of exactly that
   many bytes from the end of a file leaves you holding all its metadata.
   `footer_metadata_bytes` is the thrift footer alone, which is the minimum a
   reader needs to locate row groups, and it is what a hyparquet client should
   ask for — hyparquet has no sub-chunk read, so it never touches the page
   index. Pass one of them as `initialFetchSize`. Without it hyparquet
   speculates a 512 KiB tail on the first read of every file, which measured
   against this catalog is 524,288 bytes fetched where ADM0 needs 90,369.
1. **Load the name index** when the search box takes focus. `names` is 3.9 MB
   and reads in about 120 ms for the columns a search needs. Below about 5 MB
   that is the right call; above it, the file is sorted so a typed prefix maps
   to one or two 109 KiB row groups you can range-request instead.
2. **Match the prefix** on `name_norm`, which is case-folded and
   accent-stripped, so `zurich` finds `Zürich`. Rank on `area_km2`,
   disambiguate with `name_dupes` and `country_name`.
3. **Take `shape_id`, `level` and `geometry_ref`** from the hit. `geometry_ref`
   names the file, the row group and the row — so there is no search to do,
   only a read. It is advisory: verify the `shapeID` (or `shapeGroup` at level
   0) of the row you decode before you trust its geometry.
4. **Draw the outline from the display file** at once — one range request of
   10 KB at ADM0, 37 KB at ADM1, 151 KB at ADM2 — or move the camera from the
   index's own `bbox` while it arrives.
5. **Fetch full resolution in the background** when the user is going to
   export, clip or measure — one range request of 250 to 325 KB.
6. **Use the boundary to filter another dataset.** This is what the outward
   buffer is for.

The runnable version of all of that, with the measured numbers and the join
recipe, is in [AGENTS.md](AGENTS.md) and
[names/AGENTS.md](names/AGENTS.md).

## A sibling catalog

[cn-gazetteer-overture](https://github.com/portolan-mirrors/cn-gazetteer-overture)
is an **experimental** sibling built to the same shape from Overture Maps
divisions. It goes below the second administrative level to cities and
localities, and carries names in many languages where geoBoundaries carries
one. A widget can be pointed at either index.

**The deciding factor is the license.** This catalog is CC BY 4.0: attribution
only, usable in a closed product as long as you credit geoBoundaries. Overture
divisions carry ODbL, which is share-alike — a derived database has to be
released under the same terms. Choose this one when attribution is the only
obligation you want; choose Overture when you need the coverage and can live
with share-alike.

## Future work

A global **ADM3/ADM4** composite is under evaluation. CGAZ stops at ADM2, but
geoBoundaries' per-country `gbOpen` releases go deeper for some countries; a
coverage survey is in progress. It would not be CGAZ, because there is no
upstream composite at those levels, so the clipping and gap-filling would have
to happen here. Nothing is promised.

## Read this before querying

Four things will give you wrong answers if you skip them, all covered in
[AGENTS.md](AGENTS.md):

- `shapeType` is not the level of the file you opened.
- `shapeGroup` is a geoBoundaries code, not an ISO code, for the 20 disputed
  areas.
- The ADM0 file has no `shapeID` column at all.
- Nothing in CGAZ links a second-level unit to the first-level unit containing
  it.

## Access

```sql
INSTALL httpfs; LOAD httpfs;

-- The ten countries the composite divides most finely
SELECT shapeName, shapeGroup, adm1_units, adm2_units
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/adm0/cgaz_adm0.parquet'
WHERE shapeType = 'ADM0'
ORDER BY adm2_units DESC
LIMIT 10;
```

```sql
-- Autocomplete, from the 3.9 MB index
SELECT name, country_name, level, name_dupes
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/names/cgaz_names.parquet'
WHERE name_norm LIKE 'zurich%'
ORDER BY level;
```
