-- The distribution queries behind every class break in catalog/**/styles/.
--
--   cd ../geoboundaries-staging/publish && duckdb < ../../geoboundaries/tools/distributions.sql
--
-- Or against the published bucket, which needs no credentials:
--
--   duckdb -c "INSTALL httpfs; LOAD httpfs;
--     SELECT shapeType, count(*) FROM
--     'https://data.source.coop/portolan-mirrors/geoboundaries/adm2/cgaz_adm2.parquet'
--     GROUP BY 1;"
--
-- Load the spatial extension first (LOAD spatial;) for the vertex query.
-- Every number quoted in tools/make_styles.py, in the collection agent guides
-- and in the collection descriptions comes from a query below. Rerun this
-- file after any rebuild. If a count moved, the styles and the prose that
-- cite it are now wrong.

CREATE VIEW a0 AS SELECT * FROM 'adm0/cgaz_adm0.parquet';
CREATE VIEW a1 AS SELECT * FROM 'adm1/cgaz_adm1.parquet';
CREATE VIEW a2 AS SELECT * FROM 'adm2/cgaz_adm2.parquet';
CREATE VIEW nm AS SELECT * FROM 'names/cgaz_names.parquet';

.print ===== row counts
SELECT 'adm0' f, count(*) n FROM a0
UNION ALL SELECT 'adm1', count(*) FROM a1
UNION ALL SELECT 'adm2', count(*) FROM a2
UNION ALL SELECT 'names', count(*) FROM nm;

.print ===== shapeType composition  (the "What each polygon really is" styles)
SELECT 'adm0' f, shapeType, count(*) n FROM a0 GROUP BY 1, 2
UNION ALL SELECT 'adm1', shapeType, count(*) FROM a1 GROUP BY 1, 2
UNION ALL SELECT 'adm2', shapeType, count(*) FROM a2 GROUP BY 1, 2
ORDER BY 1, 3 DESC;

.print ===== ADM0 area bands  (adm0/styles/default.json)
SELECT CASE
         WHEN area_km2 < 1000 THEN '1 <1k'
         WHEN area_km2 < 25000 THEN '2 1k-25k'
         WHEN area_km2 < 150000 THEN '3 25k-150k'
         WHEN area_km2 < 600000 THEN '4 150k-600k'
         WHEN area_km2 < 2500000 THEN '5 600k-2.5M'
         ELSE '6 >=2.5M' END AS band,
       count(*) AS n
FROM a0 GROUP BY 1 ORDER BY 1;

.print ===== ADM1 area bands  (adm1/styles/default.json)
SELECT CASE
         WHEN area_km2 < 500 THEN '1 <500'
         WHEN area_km2 < 3000 THEN '2 500-3k'
         WHEN area_km2 < 12000 THEN '3 3k-12k'
         WHEN area_km2 < 50000 THEN '4 12k-50k'
         WHEN area_km2 < 200000 THEN '5 50k-200k'
         ELSE '6 >=200k' END AS band,
       count(*) AS n
FROM a1 GROUP BY 1 ORDER BY 1;

.print ===== ADM2 area bands  (adm2/styles/default.json)
SELECT CASE
         WHEN area_km2 < 50 THEN '1 <50'
         WHEN area_km2 < 250 THEN '2 50-250'
         WHEN area_km2 < 1000 THEN '3 250-1k'
         WHEN area_km2 < 5000 THEN '4 1k-5k'
         WHEN area_km2 < 25000 THEN '5 5k-25k'
         ELSE '6 >=25k' END AS band,
       count(*) AS n
FROM a2 GROUP BY 1 ORDER BY 1;

.print ===== ADM0 first-level units per country  (adm0/styles/adm1-units.json)
SELECT CASE
         WHEN adm1_units = 1 THEN '1 sole unit'
         WHEN adm1_units <= 10 THEN '2 2-10'
         WHEN adm1_units <= 25 THEN '3 11-25'
         WHEN adm1_units <= 50 THEN '4 26-50'
         ELSE '5 >50' END AS band,
       count(*) AS n
FROM a0 GROUP BY 1 ORDER BY 1;

.print ===== ADM1 units per country  (adm1/styles/units-per-country.json)
SELECT CASE
         WHEN country_units = 1 THEN '1 sole unit'
         WHEN country_units <= 10 THEN '2 2-10'
         WHEN country_units <= 20 THEN '3 11-20'
         WHEN country_units <= 35 THEN '4 21-35'
         ELSE '5 >35' END AS band,
       count(*) AS n, count(DISTINCT shapeGroup) AS countries
FROM a1 GROUP BY 1 ORDER BY 1;

.print ===== ADM2 units per country  (adm2/styles/units-per-country.json)
SELECT CASE
         WHEN country_units <= 10 THEN '1 <=10'
         WHEN country_units <= 100 THEN '2 11-100'
         WHEN country_units <= 500 THEN '3 101-500'
         WHEN country_units <= 2000 THEN '4 501-2000'
         ELSE '5 >2000' END AS band,
       count(*) AS n, count(DISTINCT shapeGroup) AS countries
FROM a2 GROUP BY 1 ORDER BY 1;

.print ===== compactness bands  (the three compactness styles)
SELECT 'adm0' f,
       count(*) FILTER (WHERE compactness < 0.05) AS b_lt005,
       count(*) FILTER (WHERE compactness >= 0.05 AND compactness < 0.15) AS b_005_015,
       count(*) FILTER (WHERE compactness >= 0.15 AND compactness < 0.30) AS b_015_030,
       count(*) FILTER (WHERE compactness >= 0.30 AND compactness < 0.50) AS b_030_050,
       count(*) FILTER (WHERE compactness >= 0.50) AS b_ge050
FROM a0
UNION ALL SELECT 'adm1',
       count(*) FILTER (WHERE compactness < 0.05),
       count(*) FILTER (WHERE compactness >= 0.05 AND compactness < 0.15),
       count(*) FILTER (WHERE compactness >= 0.15 AND compactness < 0.30),
       count(*) FILTER (WHERE compactness >= 0.30 AND compactness < 0.50),
       count(*) FILTER (WHERE compactness >= 0.50)
FROM a1
UNION ALL SELECT 'adm2',
       count(*) FILTER (WHERE compactness < 0.05),
       count(*) FILTER (WHERE compactness >= 0.05 AND compactness < 0.15),
       count(*) FILTER (WHERE compactness >= 0.15 AND compactness < 0.30),
       count(*) FILTER (WHERE compactness >= 0.30 AND compactness < 0.50),
       count(*) FILTER (WHERE compactness >= 0.50)
FROM a2;

.print ===== names index: level  (names/styles/default.json)
SELECT level, shape_type, count(*) AS n FROM nm GROUP BY 1, 2 ORDER BY 1, 3 DESC;

.print ===== names index: shared names  (names/styles/ambiguity.json)
SELECT CASE
         WHEN name_dupes = 1 THEN '1 unique'
         WHEN name_dupes <= 3 THEN '2 2-3'
         WHEN name_dupes <= 9 THEN '3 4-9'
         ELSE '4 >=10' END AS band,
       count(*) AS n
FROM nm GROUP BY 1 ORDER BY 1;

.print ===== names index: unit area  (names/styles/unit-area.json)
SELECT CASE
         WHEN area_km2 < 10 THEN '1 <10'
         WHEN area_km2 < 100 THEN '2 10-100'
         WHEN area_km2 < 1000 THEN '3 100-1k'
         WHEN area_km2 < 10000 THEN '4 1k-10k'
         ELSE '5 >=10k' END AS band,
       count(*) AS n
FROM nm GROUP BY 1 ORDER BY 1;

.print ===== most-shared names
SELECT name, max(name_dupes) AS units FROM nm GROUP BY 1 ORDER BY 2 DESC LIMIT 6;

.print ===== data quality counts cited in known_issues
SELECT
  (SELECT count(*) FROM a2 WHERE shapeName IS NULL) AS adm2_unnamed,
  (SELECT count(DISTINCT shapeGroup) FROM a1 WHERE shapeType = 'ADM0')
    AS countries_without_adm1,
  (SELECT count(DISTINCT shapeGroup) FROM a2 WHERE shapeType IN ('ADM0', 'ADM1'))
    AS countries_without_adm2,
  (SELECT count(*) FROM a1 WHERE shapeName LIKE '%Ã%' OR shapeName LIKE '%Å%'
     OR shapeName LIKE '%Ä%') AS adm1_mojibake_candidates;

.print ===== vertex totals, the simplification evidence
SELECT 'adm0' f, sum(ST_NPoints(geometry)) AS vertices,
       round(avg(ST_NPoints(geometry)), 1) AS mean_per_unit FROM a0
UNION ALL SELECT 'adm1', sum(ST_NPoints(geometry)),
       round(avg(ST_NPoints(geometry)), 1) FROM a1
UNION ALL SELECT 'adm2', sum(ST_NPoints(geometry)),
       round(avg(ST_NPoints(geometry)), 1) FROM a2;
