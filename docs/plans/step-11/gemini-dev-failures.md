# BIRD baseline — failure analysis

**pass@1 0.500 (25/50)** (strict multiset default) · model `openrouter/google/gemini-3-flash-preview` · prompt `generate/v3` · single-shot, naive schema dump.

## Scorer artifact vs genuine model error

Our comparator defaults to **strict multiset** semantics; BIRD's official evaluator de-dupes (`set(...)`). Re-scoring the failures under `BIRD_RULES` separates the two:

- **pass@1 under BIRD set-semantics: 0.560 (28/50)** — `+3` vs the strict default.
- **3** failures are **scorer-strictness false-negatives** (BIRD would accept them); **22** are **genuine model errors** — the real target.

## Genuine-error taxonomy (the biggest bucket is what to fix first)

Deterministic sqlglot-AST diffs of gold vs candidate, over the genuine errors only (a query may carry several tags).

| root-cause tag | genuine failures |
| --- | --- |
| table_mismatch | 9 |
| join_mismatch | 9 |
| distinct_mismatch | 7 |
| shape_matches_value_level | 5 |
| aggregate_mismatch | 3 |
| group_by_mismatch | 1 |
| where_mismatch | 1 |
| projection_count_mismatch | 1 |

## pass@1 by difficulty

| difficulty | pass@1 |
| --- | --- |
| challenging | 0.429 |
| moderate | 0.421 |
| simple | 0.583 |

## pass@1 by db

| db | pass@1 |
| --- | --- |
| california_schools | 0.538 |
| debit_card_specializing | 0.333 |
| thrombosis_prediction | 0.550 |
| toxicology | 0.429 |

## terminal states

| state | count |
| --- | --- |
| success | 25 |
| wrong_answer | 25 |

## Failures (gold vs candidate)

### `25` · california_schools · moderate · _wrong_answer_ · tags: table_mismatch, aggregate_mismatch, group_by_mismatch

**Q:** Name schools in Riverside which the average of average math score for SAT is grater than 400, what is the funding type of these schools?

```sql
-- gold
SELECT T1.sname, T2.`Charter Funding Type` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T2.`District Name` LIKE 'Riverside%' GROUP BY T1.sname, T2.`Charter Funding Type` HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > 400
-- candidate
SELECT
  T1.School,
  T1.FundingType
FROM schools AS T1
JOIN satscores AS T2
  ON T1.CDSCode = T2.cds
WHERE
  T1.County = 'Riverside' AND T2.AvgScrMath > 400;
```
comparator: result sets differ

### `37` · california_schools · moderate · _wrong_answer_ · tags: where_mismatch

**Q:** What is the complete address of the school with the lowest excellence rate? Indicate the Street, City, Zip and State.

```sql
-- gold
SELECT T2.Street, T2.City, T2.State, T2.Zip FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC LIMIT 1
-- candidate
SELECT T1.Street, T1.City, T1.Zip, T1.State FROM schools AS T1 JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T2.NumTstTakr > 0 ORDER BY (CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr) ASC LIMIT 1;
```
comparator: result sets differ

### `58` · california_schools · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the phone number and extension number for the school with the zip code 95203-3704? Indicate the school's name.

```sql
-- gold
SELECT Phone, Ext, School FROM schools WHERE Zip = '95203-3704'
-- candidate
SELECT School, Phone, Ext FROM schools WHERE Zip = '95203-3704';
```
comparator: result sets differ

### `70` · california_schools · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many active and closed District Community Day Schools are there in the county of Alpine?

```sql
-- gold
SELECT COUNT(School) FROM schools WHERE (StatusType = 'Closed' OR StatusType = 'Active') AND SOC = 69 AND County = 'Alpine'
-- candidate
SELECT
  COUNT(*)
FROM schools
WHERE
  County = 'Alpine' AND DOCType = 'District Community Day School';
```
comparator: result sets differ

### `84` · california_schools · simple · _wrong_answer_ · tags: distinct_mismatch, where_mismatch · **BIRD-ok (scorer artifact)**

**Q:** What are the two most common first names among the school administrators? Indicate the district to which they administer.

```sql
-- gold
SELECT DISTINCT T1.AdmFName1, T1.District FROM schools AS T1 INNER JOIN ( SELECT admfname1 FROM schools GROUP BY admfname1 ORDER BY COUNT(admfname1) DESC LIMIT 2 ) AS T2 ON T1.AdmFName1 = T2.admfname1
-- candidate
SELECT T1.AdmFName1, T1.District
FROM schools AS T1
JOIN (
    SELECT AdmFName1
    FROM schools
    WHERE AdmFName1 IS NOT NULL AND AdmFName1 != ''
    GROUP BY AdmFName1
    ORDER BY COUNT(*) DESC
    LIMIT 2
) AS T2 ON T1.AdmFName1 = T2.AdmFName1;
```
comparator: result sets differ

### `88` · california_schools · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the administrator's email address for the school with the highest number of test takers who received SAT scores of at least 1500?Provide the name of the school.

```sql
-- gold
SELECT T2.AdmEmail1, T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.NumGE1500 DESC LIMIT 1
-- candidate
SELECT
  T2.School,
  T2.AdmEmail1
FROM satscores AS T1
JOIN schools AS T2
  ON T1.cds = T2.CDSCode
ORDER BY
  T1.NumGE1500 DESC
LIMIT 1;
```
comparator: result sets differ

### `205` · toxicology · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Identify by their ID the molecules in which there is carbon.

```sql
-- gold
SELECT T.molecule_id FROM atom AS T WHERE T.element = 'c'
-- candidate
SELECT DISTINCT molecule_id FROM atom WHERE element = 'c';
```
comparator: result sets differ

### `234` · toxicology · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** How many bonds which involved atom 12 does molecule TR009 have?

```sql
-- gold
SELECT COUNT(T2.bond_id) FROM bond AS T1 INNER JOIN connected AS T2 ON T1.bond_id = T2.bond_id WHERE T1.molecule_id = 'TR009' AND T2.atom_id = T1.molecule_id || '_1' AND T2.atom_id2 = T1.molecule_id || '_2'
-- candidate
SELECT COUNT(DISTINCT bond_id) FROM connected WHERE (atom_id = 'TR009_12' OR atom_id2 = 'TR009_12') AND bond_id IS NOT NULL;
```
comparator: result sets differ

### `247` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch

**Q:** List all the elements of atoms that can not bond with any other atoms.

```sql
-- gold
SELECT DISTINCT T.element FROM atom AS T WHERE T.element NOT IN ( SELECT DISTINCT T1.element FROM atom AS T1 INNER JOIN connected AS T2 ON T1.atom_id = T2.atom_id )
-- candidate
SELECT DISTINCT element FROM atom WHERE atom_id NOT IN (SELECT atom_id FROM connected UNION SELECT atom_id2 FROM connected);
```
comparator: result sets differ

### `259` · toxicology · simple · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** How many elements are there for single bond molecules?

```sql
-- gold
SELECT COUNT(DISTINCT T.element) FROM ( SELECT DISTINCT T2.molecule_id, T1.element FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN bond AS T3 ON T2.molecule_id = T3.molecule_id WHERE T3.bond_type = '-' ) AS T
-- candidate
SELECT count(DISTINCT T1.element) FROM atom AS T1 JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.bond_type = '-';
```
comparator: result sets differ

### `273` · toxicology · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** What is the percentage of element chlorine in carcinogenic molecules?

```sql
-- gold
SELECT CAST(COUNT( CASE WHEN T1.element = 'cl' THEN T1.element ELSE NULL END) AS REAL) * 100 / COUNT(T1.element) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+'
-- candidate
SELECT (CAST(SUM(CASE WHEN T1.element = 'cl' THEN 1 ELSE 0 END) AS REAL) / COUNT(T1.molecule_id)) FROM atom AS T1 JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+';
```
comparator: result sets differ

### `296` · toxicology · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Indicate the molecule id is belonging to the TR000_1_2 bond that has the first atom named TR000_1.

```sql
-- gold
SELECT T2.molecule_id, T2.bond_id, T1.atom_id FROM connected AS T1 INNER JOIN bond AS T2 ON T1.bond_id = T2.bond_id WHERE T1.atom_id = 'TR000_1' AND T2.bond_id = 'TR000_1_2'
-- candidate
SELECT T2.molecule_id FROM connected AS T1 JOIN bond AS T2 ON T1.bond_id = T2.bond_id WHERE T1.bond_id = 'TR000_1_2' AND T1.atom_id = 'TR000_1';
```
comparator: result sets differ

### `306` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** Which molecules have triple bonds and list all the elements they contain.

```sql
-- gold
SELECT DISTINCT T1.molecule_id, T2.element FROM bond AS T1 INNER JOIN atom AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.bond_type = '#'
-- candidate
SELECT DISTINCT
  T1.molecule_id,
  T3.element
FROM molecule AS T1
JOIN bond AS T2
  ON T1.molecule_id = T2.molecule_id
JOIN atom AS T3
  ON T1.molecule_id = T3.molecule_id
WHERE
  T2.bond_type = '#';
```
comparator: result sets differ

### `311` · toxicology · simple · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** How many molecules without sulphur element is not having double bond?

```sql
-- gold
SELECT COUNT(DISTINCT T1.molecule_id) FROM atom AS T1 INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.element <> 's' AND T2.bond_type <> '='
-- candidate
SELECT COUNT(molecule_id) FROM molecule WHERE molecule_id NOT IN (SELECT DISTINCT molecule_id FROM atom WHERE element = 's') AND molecule_id NOT IN (SELECT DISTINCT molecule_id FROM bond WHERE bond_type = ' = ');
```
comparator: result sets differ

### `1189` · thrombosis_prediction · challenging · _wrong_answer_ · tags: distinct_mismatch

**Q:** What number of patients with a degree of thrombosis level 2 and ANA pattern of only S, have a level of anti-Cardiolip in antibody (IgM) 20% higher than average?

```sql
-- gold
SELECT COUNT(*) FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S' AND `aCL IgM` > (SELECT AVG(`aCL IgM`) * 1.2 FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S')
-- candidate
SELECT COUNT(DISTINCT ID)
FROM Examination
WHERE Thrombosis = 2 
  AND `ANA Pattern` = 'S' 
  AND `aCL IgM` > (SELECT AVG(`aCL IgM`) * 1.2 FROM Examination);
```
comparator: result sets differ

### `1228` · thrombosis_prediction · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Provide list of patients and their diagnosis with triglyceride (TG) index greater than 100 of the normal range?

```sql
-- gold
SELECT T1.ID, T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.TG > 300
-- candidate
SELECT DISTINCT T1.ID, T1.Diagnosis FROM Patient AS T1 JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.TG > 300;
```
comparator: result sets differ

### `1243` · thrombosis_prediction · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** For all patients who are older than 55 years old, what is the percentage of female who has abnormal prothrombin time (PT)?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.PT >= 14 AND T1.SEX = 'F' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE STRFTIME('%Y', CURRENT_TIMESTAMP) - STRFTIME('%Y', T1.Birthday) > 55
-- candidate
SELECT CAST(SUM(CASE WHEN Patient.SEX = 'F' AND Laboratory.PT >= 14 THEN 1 ELSE 0 END) AS REAL) / SUM(CASE WHEN Laboratory.PT >= 14 THEN 1 ELSE 0 END) * 100
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE (strftime('%Y', 'now') - strftime('%Y', Patient.Birthday)) > 55;
```
comparator: result sets differ

### `1248` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many patients born after 1980/1/1 have an abnormal fibrinogen level?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.FG <= 150 OR T2.FG >= 450 AND T1.Birthday > '1980-01-01'
-- candidate
SELECT COUNT(DISTINCT Patient.ID)
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Patient.Birthday > '1980-01-01'
  AND (Laboratory.FG < 150 OR Laboratory.FG > 450);
```
comparator: result sets differ

### `1252` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Among the patients with a normal Ig G level, how many of them have symptoms?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE T2.IGG BETWEEN 900 AND 2000 AND T3.Symptoms IS NOT NULL
-- candidate
SELECT COUNT(DISTINCT Laboratory.ID) FROM Laboratory JOIN Examination ON Laboratory.ID = Examination.ID WHERE Laboratory.IGG > 900 AND Laboratory.IGG < 2000 AND Examination.Symptoms IS NOT NULL;
```
comparator: result sets differ

### `1254` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many patients with a normal Ig A level came to the hospital after 1990/1/1?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.IGA BETWEEN 80 AND 500 AND  strftime('%Y',  T1.`First Date`) > '1990'
-- candidate
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.IGA > 80 AND T2.IGA < 500 AND STRFTIME('%Y', T1.`First Date`) >= '1990';
```
comparator: result sets differ

### `1265` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many patients have a normal level of anti-ribonuclear protein and have been admitted to the hospital?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.RNP = 'negative' OR T2.RNP = '0' AND T1.Admission = '+'
-- candidate
SELECT COUNT(DISTINCT Patient.ID)
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Laboratory.RNP IN ('-', '+-')
  AND Patient.Admission = '+';
```
comparator: result sets differ

### `1273` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch

**Q:** How many patients have a normal anti-SSB and are diagnosed with SLE in the examination?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.SSB = 'negative' OR '0' AND T1.Diagnosis = 'SLE'
-- candidate
SELECT COUNT(DISTINCT Patient.ID)
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
JOIN Examination ON Patient.ID = Examination.ID
WHERE (Laboratory.SSB = 'negative' OR Laboratory.SSB = '0')
AND Examination.Diagnosis = 'SLE';
```
comparator: result sets differ

### `1298` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Among the patients whose total cholesterol is within the normal range, how many of them have a P pattern observed in the sheet of ANA examination?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T1.ID = T3.ID WHERE T3.`ANA Pattern` = 'P' AND T2.`T-CHO` < 250
-- candidate
SELECT COUNT(DISTINCT Laboratory.ID)
FROM Laboratory
JOIN Examination ON Laboratory.ID = Examination.ID
WHERE Laboratory.`T-CHO` < 250
  AND Examination.`ANA Pattern` = 'P';
```
comparator: result sets differ

### `1475` · debit_card_specializing · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many customers in KAM had a consumption of less than 30,000 for the year 2012?

```sql
-- gold
SELECT COUNT(*) FROM ( SELECT T2.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'KAM' AND SUBSTRING(T2.Date, 1, 4) = '2012' GROUP BY T2.CustomerID HAVING SUM(T2.Consumption) < 30000 ) AS t1
-- candidate
SELECT COUNT(DISTINCT T1.CustomerID)
FROM customers AS T1
JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
WHERE T1.Segment = 'KAM'
  AND T2.Date BETWEEN '201201' AND '201212'
GROUP BY T1.CustomerID
HAVING SUM(T2.Consumption) < 30000;
```
comparator: result sets differ

### `1500` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, join_mismatch, distinct_mismatch

**Q:** Please list the product description of the products consumed in September, 2013.

```sql
-- gold
SELECT T3.Description FROM transactions_1k AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID INNER JOIN products AS T3 ON T1.ProductID = T3.ProductID WHERE T2.Date = '201309'
-- candidate
SELECT DISTINCT products.Description
FROM products
JOIN transactions_1k ON products.ProductID = transactions_1k.ProductID
WHERE transactions_1k.Date BETWEEN '2013-09-01' AND '2013-09-30';
```
comparator: result sets differ

