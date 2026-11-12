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

| collection | rows | size | what it is |
|---|---|---|---|
| `adm0` | 218 | 97 MB | Country outlines, plus 20 disputed areas |
| `adm1` | 3,224 | 76 MB | States, provinces, regions, governorates |
| `adm2` | 49,349 | 101 MB | Counties, districts, municipalities, communes |
| `names` | 52,398 | 3.6 MB | A name search index across all three levels |

The three boundary levels cover the globe seamlessly: every one of the 218
country codes appears at every level, because where a country has no
first- or second-level data CGAZ carries its coarser polygon up instead. The
`shapeType` column says which you are actually looking at.

Each boundary collection is GeoParquet 1.1 with bbox covering metadata, sorted
along a Hilbert curve, and cut into small row groups — 55, 51 and 97 of them —
so a client can fetch one unit's geometry in a range request of about 1 to
1.8 MB instead of pulling the whole file.

`names` is the piece built for autocomplete: one row per named unit, sorted by
a folded form of the name, 3.6 MB in total. Load it whole in about a quarter of
a second, or resolve a typed prefix from one or two 101 KiB row groups by range
request. It carries the `shapeID` that joins back to the geometry, the extent
to fly a map to, and a count of how many other units share the same name.

A PMTiles archive accompanies every collection, for drawing many units at once.

The `adm0` and `adm1` collections also carry a **display** file: the same rows
in the same order with simplified geometry, for drawing one unit's outline
without decoding a quarter of a megabyte of coordinates. Canada is 528,021
coordinates at full resolution and 68,973 in the display file. There is no
ADM2 display file, because ADM2 geometry is already simplified upstream — its
median unit is 82 coordinates — and nothing there was slow.

**The display geometry is buffered outward** by the distance it was simplified
by, so it contains the true boundary rather than cutting inside it. That makes
it safe to use as a spatial filter for downloading some *other* dataset: you
over-fetch a little rather than silently dropping features along the edge.
Every feature retains at least 99.87% of its original area. The cost is that
neighbouring units overlap in the margin, so it is a display and filter shape,
not a cartographic boundary. Do not measure area from it.

Per-country geoBoundaries releases (`gbOpen`, `gbHumanitarian`,
`gbAuthoritative`) are **not** mirrored here. Those are full-resolution and
represent each country as it represents itself; CGAZ is a different product.

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

1. **Load the name index** when the search box takes focus. `names` is 3.6 MB
   and reads in about 120 ms for the columns a search needs. Below about 5 MB
   that is the right call; above it, the file is sorted so a typed prefix maps
   to one or two 101 KiB row groups you can range-request instead.
2. **Match the prefix** on `name_norm`, which is case-folded and
   accent-stripped, so `zurich` finds `Zürich`. Rank on `area_km2`,
   disambiguate with `name_dupes` and `country_name`.
3. **Take `shape_id` and `level`** from the hit.
4. **Draw the outline from the display file** at once, or move the camera from
   the index's own `bbox`.
5. **Fetch full resolution in the background** when the user is going to
   export, clip or measure — one range request of 1 to 1.8 MB.
6. **Use the boundary to filter another dataset.** This is what the outward
   buffer is for.

The runnable version of all of that, with the measured numbers and the join
recipe, is in [AGENTS.md](AGENTS.md) and
[names/AGENTS.md](names/AGENTS.md).

## A sibling catalog

[cn-geocoder-overture](https://github.com/portolan-mirrors/cn-geocoder-overture)
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
-- Autocomplete, from the 3.6 MB index
SELECT name, country_name, level, name_dupes
FROM 'https://data.source.coop/portolan-mirrors/geoboundaries-catalog/names/cgaz_names.parquet'
WHERE name_norm LIKE 'zurich%'
ORDER BY level;
```
