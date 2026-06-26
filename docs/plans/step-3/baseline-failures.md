# BIRD baseline — failure analysis

**pass@1 0.420 (21/50)** (strict multiset default) · model `anthropic/claude-sonnet-4-6` · prompt `generate/v3` · single-shot, naive schema dump.

## Scorer artifact vs genuine model error

Our comparator defaults to **strict multiset** semantics; BIRD's official evaluator de-dupes (`set(...)`). Re-scoring the failures under `BIRD_RULES` separates the two:

- **pass@1 under BIRD set-semantics: 0.460 (23/50)** — `+2` vs the strict default.
- **2** failures are **scorer-strictness false-negatives** (BIRD would accept them); **27** are **genuine model errors** — the real target.

## Genuine-error taxonomy (the biggest bucket is what to fix first)

Deterministic sqlglot-AST diffs of gold vs candidate, over the genuine errors only (a query may carry several tags).

| root-cause tag | genuine failures |
| --- | --- |
| distinct_mismatch | 10 |
| table_mismatch | 9 |
| projection_count_mismatch | 7 |
| join_mismatch | 7 |
| aggregate_mismatch | 4 |
| where_mismatch | 4 |
| limit_mismatch | 2 |
| shape_matches_value_level | 2 |
| group_by_mismatch | 1 |
| candidate_unparseable | 1 |

## pass@1 by difficulty

| difficulty | pass@1 |
| --- | --- |
| challenging | 0.429 |
| moderate | 0.263 |
| simple | 0.542 |

## pass@1 by db

| db | pass@1 |
| --- | --- |
| california_schools | 0.308 |
| debit_card_specializing | 0.333 |
| thrombosis_prediction | 0.450 |
| toxicology | 0.500 |

## terminal states

| state | count |
| --- | --- |
| success | 21 |
| wrong_answer | 28 |
| guardrail_rejected | 1 |

## Failures (gold vs candidate)

### `6` · california_schools · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Among the schools with the SAT test takers of over 500, please list the schools that are magnet schools or offer a magnet program.

```sql
-- gold
SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500
-- candidate
SELECT s.School, s.CDSCode
FROM schools s
JOIN satscores sat ON s.CDSCode = sat.cds
WHERE sat.NumTstTakr > 500
  AND s.Magnet = 1
```
comparator: result sets differ

### `10` · california_schools · simple · _wrong_answer_ · tags: aggregate_mismatch, where_mismatch, limit_mismatch

**Q:** For the school with the highest average score in Reading in the SAT test, what is its FRPM count for students aged 5-17?

```sql
-- gold
SELECT T2.`FRPM Count (Ages 5-17)` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.AvgScrRead DESC LIMIT 1
-- candidate
SELECT f.`FRPM Count (Ages 5-17)`
FROM satscores s
JOIN frpm f ON s.cds = f.CDSCode
WHERE s.AvgScrRead = (SELECT MAX(AvgScrRead) FROM satscores)
```
comparator: result sets differ

### `19` · california_schools · simple · _wrong_answer_ · tags: aggregate_mismatch, where_mismatch, limit_mismatch

**Q:** What is the phone number of the school that has the highest average score in Math?

```sql
-- gold
SELECT T1.Phone FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds ORDER BY T2.AvgScrMath DESC LIMIT 1
-- candidate
SELECT s.Phone
FROM schools s
JOIN satscores sat ON s.CDSCode = sat.cds
WHERE sat.AvgScrMath = (SELECT MAX(AvgScrMath) FROM satscores)
```
comparator: result sets differ

### `25` · california_schools · moderate · _wrong_answer_ · tags: table_mismatch, aggregate_mismatch

**Q:** Name schools in Riverside which the average of average math score for SAT is grater than 400, what is the funding type of these schools?

```sql
-- gold
SELECT T1.sname, T2.`Charter Funding Type` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T2.`District Name` LIKE 'Riverside%' GROUP BY T1.sname, T2.`Charter Funding Type` HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > 400
-- candidate
SELECT s.School, s.FundingType
FROM schools s
JOIN satscores sat ON s.CDSCode = sat.cds
WHERE s.County = 'Riverside'
GROUP BY s.CDSCode, s.School, s.FundingType
HAVING AVG(sat.AvgScrMath) > 400
```
comparator: result sets differ

### `32` · california_schools · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** What is the eligible free or reduced price meal rate for the top 5 schools in grades 1-12 with the highest free or reduced price meal count of the schools with the ownership code 66?

```sql
-- gold
SELECT CAST(T1.`FRPM Count (K-12)` AS REAL) / T1.`Enrollment (K-12)` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.SOC = 66 ORDER BY T1.`FRPM Count (K-12)` DESC LIMIT 5
-- candidate
SELECT f.`School Name`, 
       f.`FRPM Count (K-12)` / f.`Enrollment (K-12)` AS frpm_rate
FROM frpm f
JOIN schools s ON f.CDSCode = s.CDSCode
WHERE s.DOC = '66'
  AND f.`Enrollment (K-12)` > 0
ORDER BY f.`FRPM Count (K-12)` DESC
LIMIT 5
```
comparator: result sets differ

### `37` · california_schools · moderate · _wrong_answer_ · tags: where_mismatch

**Q:** What is the complete address of the school with the lowest excellence rate? Indicate the Street, City, Zip and State.

```sql
-- gold
SELECT T2.Street, T2.City, T2.State, T2.Zip FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC LIMIT 1
-- candidate
SELECT s.Street, s.City, s.Zip, s.State
FROM schools s
JOIN satscores sat ON s.CDSCode = sat.cds
WHERE sat.NumTstTakr > 0 AND sat.NumGE1500 IS NOT NULL
ORDER BY CAST(sat.NumGE1500 AS REAL) / sat.NumTstTakr ASC
LIMIT 1
```
comparator: result sets differ

### `59` · california_schools · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** What is the website for the schools under the administrations of Mike Larson and Dante Alvarez?

```sql
-- gold
SELECT Website FROM schools WHERE (AdmFName1 = 'Mike' AND AdmLName1 = 'Larson') OR (AdmFName1 = 'Dante' AND AdmLName1 = 'Alvarez')
-- candidate
SELECT CDSCode, School, Website, AdmFName1, AdmLName1, AdmFName2, AdmLName2
FROM schools
WHERE (AdmFName1 = 'Mike' AND AdmLName1 = 'Larson')
   OR (AdmFName2 = 'Mike' AND AdmLName2 = 'Larson')
   OR (AdmFName1 = 'Dante' AND AdmLName1 = 'Alvarez')
   OR (AdmFName2 = 'Dante' AND AdmLName2 = 'Alvarez')
```
comparator: result sets differ

### `70` · california_schools · simple · _wrong_answer_ · tags: group_by_mismatch, projection_count_mismatch

**Q:** How many active and closed District Community Day Schools are there in the county of Alpine?

```sql
-- gold
SELECT COUNT(School) FROM schools WHERE (StatusType = 'Closed' OR StatusType = 'Active') AND SOC = 69 AND County = 'Alpine'
-- candidate
SELECT StatusType, COUNT(*) AS count
FROM schools
WHERE County = 'Alpine'
  AND DOCType = 'District Community Day School'
  AND StatusType IN ('Active', 'Closed')
GROUP BY StatusType
```
comparator: result sets differ

### `84` · california_schools · simple · _wrong_answer_ · tags: table_mismatch, distinct_mismatch, where_mismatch

**Q:** What are the two most common first names among the school administrators? Indicate the district to which they administer.

```sql
-- gold
SELECT DISTINCT T1.AdmFName1, T1.District FROM schools AS T1 INNER JOIN ( SELECT admfname1 FROM schools GROUP BY admfname1 ORDER BY COUNT(admfname1) DESC LIMIT 2 ) AS T2 ON T1.AdmFName1 = T2.admfname1
-- candidate
WITH all_names AS (
    SELECT AdmFName1 AS FirstName, District FROM schools WHERE AdmFName1 IS NOT NULL
    UNION ALL
    SELECT AdmFName2 AS FirstName, District FROM schools WHERE AdmFName2 IS NOT NULL
    UNION ALL
    SELECT AdmFName3 AS FirstName, District FROM schools WHERE AdmFName3 IS NOT NULL
),
name_counts AS (
    SELECT FirstName, COUNT(*) AS cnt
    FROM all_names
    GROUP BY FirstName
    ORDER BY cnt DESC
    LIMIT 2
),
top_names AS (
    SELECT FirstName FROM name_counts
),
districts AS (
    SELECT an.FirstName, an.District
    FROM all_names an
    WHERE an.FirstName IN (SELECT FirstName FROM top_names)
    GROUP BY an.FirstName, an.District
)
SELECT d.FirstName, d.District
FROM districts d
JOIN name_counts nc ON d.FirstName = nc.FirstName
ORDER BY nc.cnt DESC, d.FirstName, d.District
```
comparator: result sets differ

### `205` · toxicology · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Identify by their ID the molecules in which there is carbon.

```sql
-- gold
SELECT T.molecule_id FROM atom AS T WHERE T.element = 'c'
-- candidate
SELECT DISTINCT molecule_id
FROM atom
WHERE element = 'c'
```
comparator: result sets differ

### `234` · toxicology · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** How many bonds which involved atom 12 does molecule TR009 have?

```sql
-- gold
SELECT COUNT(T2.bond_id) FROM bond AS T1 INNER JOIN connected AS T2 ON T1.bond_id = T2.bond_id WHERE T1.molecule_id = 'TR009' AND T2.atom_id = T1.molecule_id || '_1' AND T2.atom_id2 = T1.molecule_id || '_2'
-- candidate
SELECT COUNT(DISTINCT c.bond_id)
FROM connected c
WHERE c.atom_id = 'TR009_12' OR c.atom_id2 = 'TR009_12'
```
comparator: result sets differ

### `247` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch

**Q:** List all the elements of atoms that can not bond with any other atoms.

```sql
-- gold
SELECT DISTINCT T.element FROM atom AS T WHERE T.element NOT IN ( SELECT DISTINCT T1.element FROM atom AS T1 INNER JOIN connected AS T2 ON T1.atom_id = T2.atom_id )
-- candidate
SELECT DISTINCT a.element
FROM atom a
WHERE a.atom_id NOT IN (
    SELECT atom_id FROM connected
    UNION
    SELECT atom_id2 FROM connected
)
```
comparator: result sets differ

### `280` · toxicology · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** Enumerate the bond ID of triple bond type molecules and tell me if they are carcinogenic or not.

```sql
-- gold
SELECT DISTINCT T1.bond_id, T2.label FROM bond AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.bond_type = '#'
-- candidate
SELECT b.bond_id, b.molecule_id, m.label,
  CASE WHEN m.label = '+' THEN 'Carcinogenic' ELSE 'Non-Carcinogenic' END AS carcinogenic_status
FROM bond b
JOIN molecule m ON b.molecule_id = m.molecule_id
WHERE b.bond_type = '#'
```
comparator: result sets differ

### `296` · toxicology · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Indicate the molecule id is belonging to the TR000_1_2 bond that has the first atom named TR000_1.

```sql
-- gold
SELECT T2.molecule_id, T2.bond_id, T1.atom_id FROM connected AS T1 INNER JOIN bond AS T2 ON T1.bond_id = T2.bond_id WHERE T1.atom_id = 'TR000_1' AND T2.bond_id = 'TR000_1_2'
-- candidate
SELECT b.molecule_id
FROM bond b
JOIN connected c ON b.bond_id = c.bond_id
WHERE b.bond_id = 'TR000_1_2'
  AND c.atom_id = 'TR000_1'
```
comparator: result sets differ

### `311` · toxicology · simple · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** How many molecules without sulphur element is not having double bond?

```sql
-- gold
SELECT COUNT(DISTINCT T1.molecule_id) FROM atom AS T1 INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.element <> 's' AND T2.bond_type <> '='
-- candidate
SELECT COUNT(DISTINCT m.molecule_id)
FROM molecule m
WHERE m.molecule_id NOT IN (
    SELECT DISTINCT a.molecule_id
    FROM atom a
    WHERE a.element = 's'
)
AND m.molecule_id NOT IN (
    SELECT DISTINCT b.molecule_id
    FROM bond b
    WHERE b.bond_type = ' = '
)
```
comparator: result sets differ

### `337` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** List the element and bond type included in the molecule with molecule ID of TR002.

```sql
-- gold
SELECT DISTINCT T1.element, T2.bond_type FROM atom AS T1 INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.molecule_id = 'TR002'
-- candidate
SELECT DISTINCT a.element, b.bond_type
FROM atom a
JOIN connected c ON a.atom_id = c.atom_id
JOIN bond b ON c.bond_id = b.bond_id
WHERE a.molecule_id = 'TR002'
```
comparator: result sets differ

### `1186` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Lists all patients by ID who were diagnosed with Behcet's and had their exams between 01/01/197 and 12/31/1997.

```sql
-- gold
SELECT ID FROM Examination WHERE `Examination Date` BETWEEN '1997-01-01' AND '1997-12-31' AND Diagnosis = 'Behcet'
-- candidate
SELECT DISTINCT p.ID
FROM Patient p
JOIN Examination e ON p.ID = e.ID
WHERE p.Diagnosis LIKE '%Behcet%'
  AND e.`Examination Date` >= '1997-01-01'
  AND e.`Examination Date` < '1998-01-01'
```
comparator: result sets differ

### `1189` · thrombosis_prediction · challenging · _wrong_answer_ · tags: distinct_mismatch

**Q:** What number of patients with a degree of thrombosis level 2 and ANA pattern of only S, have a level of anti-Cardiolip in antibody (IgM) 20% higher than average?

```sql
-- gold
SELECT COUNT(*) FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S' AND `aCL IgM` > (SELECT AVG(`aCL IgM`) * 1.2 FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S')
-- candidate
SELECT COUNT(DISTINCT e.ID)
FROM Examination e
WHERE e.Thrombosis = 2
  AND e.`ANA Pattern` = 'S'
  AND e.`aCL IgM` > (SELECT (AVG(`aCL IgM`) + AVG(`aCL IgM`)) * 0.2 FROM Examination)
```
comparator: result sets differ

### `1228` · thrombosis_prediction · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Provide list of patients and their diagnosis with triglyceride (TG) index greater than 100 of the normal range?

```sql
-- gold
SELECT T1.ID, T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.TG > 300
-- candidate
SELECT DISTINCT p.ID, p.Diagnosis
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE l.TG > 300
```
comparator: result sets differ

### `1243` · thrombosis_prediction · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** For all patients who are older than 55 years old, what is the percentage of female who has abnormal prothrombin time (PT)?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.PT >= 14 AND T1.SEX = 'F' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE STRFTIME('%Y', CURRENT_TIMESTAMP) - STRFTIME('%Y', T1.Birthday) > 55
-- candidate
SELECT CAST(SUM(CASE WHEN p.SEX = 'F' AND l.PT >= 14 THEN 1 ELSE 0 END) AS REAL) * 100.0 / SUM(CASE WHEN l.PT >= 14 THEN 1 ELSE 0 END)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE (STRFTIME('%Y', CURRENT_TIMESTAMP) - STRFTIME('%Y', p.Birthday)) > 55
```
comparator: result sets differ

### `1248` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many patients born after 1980/1/1 have an abnormal fibrinogen level?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.FG <= 150 OR T2.FG >= 450 AND T1.Birthday > '1980-01-01'
-- candidate
SELECT COUNT(DISTINCT p.ID)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE p.Birthday > '1980-01-01'
  AND (l.FG < 150 OR l.FG > 450)
```
comparator: result sets differ

### `1252` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Among the patients with a normal Ig G level, how many of them have symptoms?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE T2.IGG BETWEEN 900 AND 2000 AND T3.Symptoms IS NOT NULL
-- candidate
SELECT COUNT(DISTINCT l.ID)
FROM Laboratory l
JOIN Examination e ON l.ID = e.ID
WHERE l.IGG > 900 AND l.IGG < 2000
AND e.Symptoms IS NOT NULL
```
comparator: result sets differ

### `1254` · thrombosis_prediction · moderate · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** How many patients with a normal Ig A level came to the hospital after 1990/1/1?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.IGA BETWEEN 80 AND 500 AND  strftime('%Y',  T1.`First Date`) > '1990'
-- candidate
SELECT COUNT(DISTINCT p.ID)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE l.IGA > 80
  AND l.IGA < 500
  AND YEAR(p.`First Date`) >= 1990

SELECT COUNT(DISTINCT p.ID)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE l.IGA > 80
  AND l.IGA < 500
  AND strftime('%Y', p.`First Date`) >= '1990'
```
comparator: parse_error: candidate did not parse under the named or generic dialect

### `1265` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many patients have a normal level of anti-ribonuclear protein and have been admitted to the hospital?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.RNP = 'negative' OR T2.RNP = '0' AND T1.Admission = '+'
-- candidate
SELECT COUNT(DISTINCT p.ID)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE l.RNP IN ('-', '+-')
AND p.Admission = '+'
```
comparator: result sets differ

### `1273` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch

**Q:** How many patients have a normal anti-SSB and are diagnosed with SLE in the examination?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.SSB = 'negative' OR '0' AND T1.Diagnosis = 'SLE'
-- candidate
SELECT COUNT(DISTINCT e.ID)
FROM Examination e
JOIN Laboratory l ON e.ID = l.ID
WHERE l.SSB IN ('-', '+-')
AND e.Diagnosis = 'SLE'
```
comparator: result sets differ

### `1298` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** Among the patients whose total cholesterol is within the normal range, how many of them have a P pattern observed in the sheet of ANA examination?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T1.ID = T3.ID WHERE T3.`ANA Pattern` = 'P' AND T2.`T-CHO` < 250
-- candidate
SELECT COUNT(DISTINCT p.ID)
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
JOIN Examination e ON p.ID = e.ID
WHERE l.`T-CHO` < 250
  AND e.`ANA Pattern` = 'P'
```
comparator: result sets differ

### `1309` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** Please list a patient's platelet level if it is within the normal range and if he or she is diagnosed with MCTD.

```sql
-- gold
SELECT T2.PLT FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T1.Diagnosis = 'MCTD' AND T2.PLT BETWEEN 100 AND 400
-- candidate
SELECT DISTINCT L.ID, L.PLT
FROM Laboratory L
JOIN Patient P ON L.ID = P.ID
WHERE L.PLT > 100 AND L.PLT < 400
AND P.Diagnosis = 'MCTD'
```
comparator: result sets differ

### `1475` · debit_card_specializing · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many customers in KAM had a consumption of less than 30,000 for the year 2012?

```sql
-- gold
SELECT COUNT(*) FROM ( SELECT T2.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'KAM' AND SUBSTRING(T2.Date, 1, 4) = '2012' GROUP BY T2.CustomerID HAVING SUM(T2.Consumption) < 30000 ) AS t1
-- candidate
SELECT COUNT(DISTINCT y.CustomerID)
FROM yearmonth y
JOIN customers c ON y.CustomerID = c.CustomerID
WHERE c.Segment = 'KAM'
  AND y.Date BETWEEN '201201' AND '201212'
GROUP BY y.CustomerID
HAVING SUM(y.Consumption) < 30000
```
comparator: result sets differ

### `1500` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Please list the product description of the products consumed in September, 2013.

```sql
-- gold
SELECT T3.Description FROM transactions_1k AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID INNER JOIN products AS T3 ON T1.ProductID = T3.ProductID WHERE T2.Date = '201309'
-- candidate
SELECT DISTINCT p.Description
FROM products p
JOIN transactions_1k t ON p.ProductID = t.ProductID
WHERE strftime('%Y%m', t.Date) = '201309'
```
comparator: result sets differ

