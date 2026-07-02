# Mini-Dev — failure analysis

**pass@1 0.568 (284/500)** (strict multiset default) · model `openrouter/google/gemini-3.5-flash` · prompt `generate/v3` · schema-RAG, single-shot, slice `minidev-sqlite-500`.

pass@1 under BIRD set-semantics: **0.598 (299/500)** — `+15` scorer-strictness false-negatives vs `201` genuine model errors.

## Genuine-error taxonomy

Deterministic sqlglot-AST diffs of gold vs candidate (a failure may carry several tags).

| root-cause tag | genuine failures |
| --- | --- |
| table_mismatch | 74 |
| join_mismatch | 67 |
| missing_table | 62 |
| projection_count_mismatch | 55 |
| distinct_mismatch | 50 |
| aggregate_mismatch | 49 |
| extra_table | 40 |
| shape_matches_value_level | 25 |
| spurious_join | 19 |
| group_by_mismatch | 18 |
| where_mismatch | 15 |
| limit_mismatch | 14 |
| candidate_unparseable | 6 |

## terminal states

| state | count |
| --- | --- |
| success | 284 |
| wrong_answer | 193 |
| execution_error_final | 7 |
| guardrail_rejected | 16 |

## Failures (gold vs candidate)

### `1481` · debit_card_specializing · challenging · _guardrail_rejected_ · tags: join_mismatch, aggregate_mismatch, group_by_mismatch

**Q:** What is the difference in the annual average consumption of the customers with the least amount of consumption paid in CZK for 2013 between SME and LAM, LAM and KAM, and KAM and SME?

```sql
-- gold
SELECT CAST(SUM(IIF(T1.Segment = 'SME', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) - CAST(SUM(IIF(T1.Segment = 'LAM', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) , CAST(SUM(IIF(T1.Segment = 'LAM', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) - CAST(SUM(IIF(T1.Segment = 'KAM', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) , CAST(SUM(IIF(T1.Segment = 'KAM', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) - CAST(SUM(IIF(T1.Segment = 'SME', T2.Consumption, 0)) AS REAL) / COUNT(T1.CustomerID) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Currency = 'CZK' AND T2.Consumption = ( SELECT MIN(Consumption) FROM yearmonth ) AND T2.Date BETWEEN 201301 AND 201312
-- candidate
SELECT 
  (sme_avg - lam_avg) AS diff_sme_lam,
  (lam_avg - kam_avg) AS diff_lam_kam,
  (kam_avg - sme_avg) AS diff_kam_sme
FROM (
  SELECT COALESCE(AVG(total_consumption), 0) AS sme_avg
  FROM (
    SELECT c.CustomerID, SUM(y.Consumption) AS total_consumption
    FROM customers c
    JOIN yearmonth y ON c.CustomerID = y.CustomerID
    WHERE c.Segment = 'SME' 
      AND c.Currency = 'CZK' 
      AND y.Date BETWEEN '201301' AND '201312'
    GROUP BY c.CustomerID
  )
  WHERE total_consumption = (
    SELECT MIN(sub.total_consumption)
    FROM (
      SELECT SUM(y2.Consumption) AS total_consumption
      FROM customers c2
      JOIN yearmonth y2 ON c2.CustomerID = y2.CustomerID
      WHERE c2.Segment = 'SME' 
        AND c2.Currency = 'CZK' 
        AND y2.Date BETWEEN '201301' AND '201312'
      GROUP BY c2.CustomerID
    ) sub
  )
) AS sme
CROSS JOIN (
  SELECT COALESCE(AVG(total_consumption), 0) AS lam_avg
  FROM (
    SELECT c.CustomerID, SUM(y.Consumption) AS total_consumption
    FROM customers c
    JOIN yearmonth y ON c.CustomerID = y.CustomerID
    WHERE c.Segment = 'LAM' 
      AND c.Currency = 'CZK' 
      AND y.Date BETWEEN '201301' AND '201312'
    GROUP BY c.CustomerID
  )
  WHERE total_consumption = (
    SELECT MIN(sub.total_consumption)
    FROM (
      SELECT SUM(y2.Consumption) AS total_consumption
      FROM customers c2
      JOIN yearmonth y2 ON c2.CustomerID = y2.CustomerID
      WHERE c2.Segment = 'LAM' 
        AND c2.Currency = 'CZK' 
        AND y2.Date BETWEEN '201301' AND '201312'
      GROUP BY c2.CustomerID
    ) sub
  )
) AS lam
CROSS JOIN (
  SELECT COALESCE(AVG(total_consumption), 0) AS kam_avg
  FROM (
    SELECT c.CustomerID, SUM(y.Consumption) AS total_consumption
    FROM customers c
    JOIN yearmonth y ON c.CustomerID = y.CustomerID
    WHERE c.Segment = 'KAM' 
      AND c.Currency = 'CZK' 
      AND y.Date BETWEEN '201301' AND '201312'
    GROUP BY c.CustomerID
  )
  WHERE total_consumption = (
    SELECT MIN(sub.total_consumption)
    FROM (
      SELECT SUM(y2.Consumption) AS total_consumption
      FROM customers c2
      JOIN yearmonth y2 ON c2.CustomerID = y2.CustomerID
      WHERE c2.Segment = 'KAM' 
        AND c2.Currency = 'CZK' 
        AND y2.Date BETWEEN '201301' AND '201312'
      GROUP BY c2.CustomerID
    ) sub
  )
) AS kam;
```
comparator: —

### `1482` · debit_card_specializing · challenging · _wrong_answer_ · tags: group_by_mismatch, where_mismatch, projection_count_mismatch

**Q:** Which of the three segments—SME, LAM and KAM—has the biggest and lowest percentage increases in consumption paid in EUR between 2012 and 2013?

```sql
-- gold
SELECT CAST((SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0))) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0)), CAST(SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'LAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) , CAST(SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'KAM' AND T2.Date LIKE '2012%', T2.Consumption, 0)) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
-- candidate
SELECT 
  c.Segment,
  (SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2013' THEN y.Consumption ELSE 0 END) - 
   SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2012' THEN y.Consumption ELSE 0 END)) / 
   SUM(CASE WHEN SUBSTR(y.Date, 1, 4) = '2013' THEN y.Consumption ELSE 0 END) * 100 AS pct_increase
FROM customers c
JOIN yearmonth y ON c.CustomerID = y.CustomerID
WHERE c.Currency = 'EUR'
GROUP BY c.Segment
ORDER BY pct_increase DESC;
```
comparator: result sets differ

### `1490` · debit_card_specializing · moderate · _wrong_answer_ · tags: group_by_mismatch

**Q:** How many percent of LAM customer consumed more than 46.73?

```sql
-- gold
SELECT CAST(SUM(IIF(T2.Consumption > 46.73, 1, 0)) AS FLOAT) * 100 / COUNT(T1.CustomerID) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM'
-- candidate
SELECT 
  (CAST(COUNT(CASE WHEN total_consumption > 46.73 THEN 1 END) AS REAL) / COUNT(*)) * 100 AS percentage
FROM (
  SELECT 
    c.CustomerID,
    SUM(y.Consumption) AS total_consumption
  FROM customers c
  LEFT JOIN yearmonth y ON c.CustomerID = y.CustomerID
  WHERE c.Segment = 'LAM'
  GROUP BY c.CustomerID
);
```
comparator: result sets differ

### `1493` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, group_by_mismatch, distinct_mismatch

**Q:** In February 2012, what percentage of customers consumed more than 528.3?

```sql
-- gold
SELECT CAST(SUM(IIF(Consumption > 528.3, 1, 0)) AS FLOAT) * 100 / COUNT(CustomerID) FROM yearmonth WHERE Date = '201202'
-- candidate
SELECT (COUNT(DISTINCT CASE WHEN t.total_amount > 528.3 THEN t.CustomerID END) * 100.0) / COUNT(DISTINCT t.CustomerID) AS percentage
FROM (
  SELECT CustomerID, SUM(Amount) AS total_amount
  FROM transactions_1k
  WHERE Date >= '2012-02-01' AND Date <= '2012-02-29'
  GROUP BY CustomerID
) t
```
comparator: result sets differ

### `1498` · debit_card_specializing · simple · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch, limit_mismatch

**Q:** What is the highest monthly consumption in the year 2012?

```sql
-- gold
SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012' GROUP BY SUBSTR(Date, 5, 2) ORDER BY SUM(Consumption) DESC LIMIT 1
-- candidate
SELECT MAX(Consumption) AS MaxConsumption
FROM yearmonth
WHERE SUBSTR(Date, 1, 4) = '2012';
```
comparator: result sets differ

### `1500` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, spurious_join, distinct_mismatch

**Q:** Please list the product description of the products consumed in September, 2013.

```sql
-- gold
SELECT T3.Description FROM transactions_1k AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID INNER JOIN products AS T3 ON T1.ProductID = T3.ProductID WHERE T2.Date = '201309'
-- candidate
SELECT DISTINCT p.Description
FROM transactions_1k t
JOIN products p ON t.ProductID = p.ProductID
WHERE t.Date >= '2013-09-01' AND t.Date <= '2013-09-30'
```
comparator: result sets differ

### `1501` · debit_card_specializing · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, spurious_join

**Q:** Please list the countries of the gas stations with transactions taken place in June, 2013.

```sql
-- gold
SELECT DISTINCT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID INNER JOIN yearmonth AS T3 ON T1.CustomerID = T3.CustomerID WHERE T3.Date = '201306'
-- candidate
SELECT DISTINCT g.Country
FROM gasstations g
INNER JOIN transactions_1k t ON g.GasStationID = t.GasStationID
WHERE t.Date >= '2013-06-01' AND t.Date <= '2013-06-30'
```
comparator: result sets differ

### `1505` · debit_card_specializing · simple · _wrong_answer_ · tags: distinct_mismatch

**Q:** Among the customers who paid in euro, how many of them have a monthly consumption of over 1000?

```sql
-- gold
SELECT COUNT(*) FROM yearmonth AS T1 INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID WHERE T2.Currency = 'EUR' AND T1.Consumption > 1000.00
-- candidate
SELECT COUNT(DISTINCT c.CustomerID)
FROM customers c
JOIN yearmonth y ON c.CustomerID = y.CustomerID
WHERE c.Currency = 'EUR' AND y.Consumption > 1000
```
comparator: result sets differ

### `1514` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, spurious_join, distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** What kind of currency did the customer paid at 16:25:00 in 2012/8/24?

```sql
-- gold
SELECT DISTINCT T3.Currency FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID INNER JOIN customers AS T3 ON T1.CustomerID = T3.CustomerID WHERE T1.Date = '2012-08-24' AND T1.Time = '16:25:00'
-- candidate
SELECT customers.Currency FROM customers JOIN transactions_1k ON customers.CustomerID = transactions_1k.CustomerID WHERE transactions_1k.Date = '2012-08-24' AND transactions_1k.Time = '16:25:00'
```
comparator: result sets differ

### `1524` · debit_card_specializing · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, spurious_join

**Q:** What's the nationality of the customer who spent 548.4 in 2012/8/24?

```sql
-- gold
SELECT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.Date = '2012-08-24' AND T1.Price  = 548.4
-- candidate
SELECT t1.Currency FROM customers AS t1 JOIN transactions_1k AS t2 ON t1.CustomerID = t2.CustomerID WHERE t2.Date = '2012-08-24' AND t2.Price = 548.4
```
comparator: result sets differ

### `1525` · debit_card_specializing · simple · _wrong_answer_ · tags: spurious_join, aggregate_mismatch, distinct_mismatch

**Q:** What is the percentage of the customers who used EUR in 2012/8/25?

```sql
-- gold
SELECT CAST(SUM(IIF(T2.Currency = 'EUR', 1, 0)) AS FLOAT) * 100 / COUNT(T1.CustomerID) FROM transactions_1k AS T1 INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Date = '2012-08-25'
-- candidate
SELECT 
  (CAST(COUNT(DISTINCT CASE WHEN c.Currency = 'EUR' THEN t.CustomerID END) AS REAL) / COUNT(DISTINCT t.CustomerID)) * 100.0 AS Percentage
FROM transactions_1k t
INNER JOIN customers c ON t.CustomerID = c.CustomerID
WHERE t.Date = '2012-08-25'
```
comparator: result sets differ

### `1526` · debit_card_specializing · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** For the customer who paid 634.8 in 2012/8/25, what was the consumption decrease rate from Year 2012 to 2013?

```sql
-- gold
SELECT CAST(SUM(IIF(SUBSTRING(Date, 1, 4) = '2012', Consumption, 0)) - SUM(IIF(SUBSTRING(Date, 1, 4) = '2013', Consumption, 0)) AS FLOAT) / SUM(IIF(SUBSTRING(Date, 1, 4) = '2012', Consumption, 0)) FROM yearmonth WHERE CustomerID = ( SELECT T1.CustomerID FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.Date = '2012-08-25' AND T1.Price  = 1513.12 )
-- candidate
SELECT (SUM(CASE WHEN Date LIKE '2012%' THEN Consumption ELSE 0 END) - SUM(CASE WHEN Date LIKE '2013%' THEN Consumption ELSE 0 END)) / SUM(CASE WHEN Date LIKE '2012%' THEN Consumption ELSE 0 END) FROM yearmonth WHERE CustomerID = (SELECT CustomerID FROM transactions_1k WHERE Date = '2012-08-25' AND Price = 634.8)
```
comparator: result sets differ

### `1529` · debit_card_specializing · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** What is the amount spent by customer "38508" at the gas stations? How much had the customer spent in January 2012?

```sql
-- gold
SELECT SUM(T1.Price ) , SUM(IIF(T3.Date = '201201', T1.Price, 0)) FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID INNER JOIN yearmonth AS T3 ON T1.CustomerID = T3.CustomerID WHERE T1.CustomerID = '38508'
-- candidate
SELECT 
  (SELECT SUM(Amount * Price) 
   FROM transactions_1k 
   WHERE CustomerID = 38508) AS TotalSpent,
  (SELECT Consumption 
   FROM yearmonth 
   WHERE CustomerID = 38508 AND Date = '201201') AS ConsumptionJan2012
```
comparator: result sets differ

### `1531` · debit_card_specializing · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, spurious_join, where_mismatch

**Q:** Who is the top spending customer and how much is the average price per single item purchased by this customer? What currency was being used?

```sql
-- gold
SELECT T2.CustomerID, SUM(T2.Price / T2.Amount), T1.Currency FROM customers AS T1 INNER JOIN transactions_1k AS T2 ON T1.CustomerID = T2.CustomerID WHERE T2.CustomerID = ( SELECT CustomerID FROM yearmonth ORDER BY Consumption DESC LIMIT 1 ) GROUP BY T2.CustomerID, T1.Currency
-- candidate
SELECT 
  t.CustomerID,
  (SUM(t.Price) / SUM(t.Amount)) AS AveragePricePerItem,
  c.Currency
FROM transactions_1k t
JOIN customers c ON t.CustomerID = c.CustomerID
GROUP BY t.CustomerID, c.Currency
ORDER BY SUM(t.Price) DESC
LIMIT 1;
```
comparator: result sets differ

### `1533` · debit_card_specializing · moderate · _wrong_answer_ · tags: join_mismatch, projection_count_mismatch

**Q:** For all the people who paid more than 29.00 per unit of product id No.5. Give their consumption status in the August of 2012.

```sql
-- gold
SELECT T2.Consumption FROM transactions_1k AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Price / T1.Amount > 29.00 AND T1.ProductID = 5 AND T2.Date = '201208'
-- candidate
SELECT CustomerID, Consumption FROM yearmonth WHERE Date = '201208' AND CustomerID IN (SELECT CustomerID FROM transactions_1k WHERE ProductID = 5 AND Amount > 0 AND (Price / Amount) > 29.00)
```
comparator: result sets differ

### `1322` · student_club · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, distinct_mismatch

**Q:** Among the events attended by more than 10 members of the Student_Club, how many of them are meetings?

```sql
-- gold
SELECT COUNT(DISTINCT T1.event_id) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event WHERE T1.type = 'Meeting' GROUP BY T1.event_id HAVING COUNT(T2.link_to_event) > 10
-- candidate
SELECT COUNT(*) FROM (SELECT T1.event_id FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.type = 'Meeting' GROUP BY T1.event_id HAVING COUNT(T1.event_id) > 10)
```
comparator: result sets differ

### `1338` · student_club · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Was each expense in October Meeting on October 8, 2019 approved?

```sql
-- gold
SELECT T3.approved FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'October Meeting' AND T1.event_date LIKE '2019-10-08%'
-- candidate
SELECT
  t1.expense_description,
  t1.approved
FROM expense AS t1
INNER JOIN budget AS t2
  ON t1.link_to_budget = t2.budget_id
INNER JOIN event AS t3
  ON t2.link_to_event = t3.event_id
WHERE
  t3.event_name = 'October Meeting'
  AND t3.event_date LIKE '2019-10-08%'
```
comparator: result sets differ

### `1375` · student_club · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** List all the members of the "School of Applied Sciences, Technology and Education" department.

```sql
-- gold
SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T2.department = 'School of Applied Sciences, Technology and Education'
-- candidate
SELECT t1.first_name || ' ' || t1.last_name AS full_name
FROM member AS t1
INNER JOIN major AS t2 ON t1.link_to_major = t2.major_id
WHERE t2.department = 'School of Applied Sciences, Technology and Education';
```
comparator: result sets differ

### `1381` · student_club · moderate · _execution_error_final_ · tags: shape_matches_value_level

**Q:** List the name of students that have attended more than 7 events.

```sql
-- gold
SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN attendance AS T2 ON T1.member_id = T2.link_to_member GROUP BY T2.link_to_member HAVING COUNT(T2.link_to_event) > 7
-- candidate
SELECT
  t1.first_name,
  t1.last_name
FROM member AS t1
INNER JOIN attendance AS t2
  ON t1.member_id = t2.member_id
GROUP BY
  t1.member_id,
  t1.first_name,
  t1.last_name
HAVING COUNT(t2.link_to_event) > 7
```
comparator: —

### `1387` · student_club · moderate · _wrong_answer_ · tags: limit_mismatch

**Q:** Which student has been entrusted to manage the budget for the Yearly Kickoff?

```sql
-- gold
SELECT T4.first_name, T4.last_name FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget INNER JOIN member AS T4 ON T3.link_to_member = T4.member_id WHERE T1.event_name = 'Yearly Kickoff'
-- candidate
SELECT t4.first_name, t4.last_name
FROM event AS t1
JOIN budget AS t2 ON t1.event_id = t2.link_to_event
JOIN expense AS t3 ON t2.budget_id = t3.link_to_budget
JOIN member AS t4 ON t3.link_to_member = t4.member_id
WHERE t1.event_name = 'Yearly Kickoff'
LIMIT 1;
```
comparator: result sets differ

### `1399` · student_club · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** Did Maya Mclean attend the 'Women's Soccer' event?

```sql
-- gold
SELECT CASE WHEN T3.event_name = 'Women''s Soccer' THEN 'YES' END AS result FROM member AS T1 INNER JOIN attendance AS T2 ON T1.member_id = T2.link_to_member INNER JOIN event AS T3 ON T2.link_to_event = T3.event_id WHERE T1.first_name = 'Maya' AND T1.last_name = 'Mclean'
-- candidate
SELECT
  CASE
    WHEN COUNT(*) > 0 THEN 'Yes'
    ELSE 'No'
  END AS attended
FROM attendance AS a
INNER JOIN member AS m ON a.link_to_member = m.member_id
INNER JOIN event AS e ON a.link_to_event = e.event_id
WHERE m.first_name = 'Maya'
  AND m.last_name = 'Mclean'
  AND e.event_name = 'Women''s Soccer';
```
comparator: result sets differ

### `1404` · student_club · moderate · _wrong_answer_ · tags: group_by_mismatch

**Q:** Identify the type of expenses and their total value approved for 'October Meeting' event.

```sql
-- gold
SELECT T1.type, SUM(T3.cost) FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'October Meeting'
-- candidate
SELECT 
  b.category AS expense_type, 
  SUM(e.cost) AS total_value
FROM expense e
JOIN budget b ON e.link_to_budget = b.budget_id
JOIN event ev ON b.link_to_event = ev.event_id
WHERE ev.event_name = 'October Meeting' AND e.approved = 'true'
GROUP BY b.category;
```
comparator: result sets differ

### `1410` · student_club · simple · _wrong_answer_ · tags: group_by_mismatch, projection_count_mismatch

**Q:** List out the full name and total cost that member id "rec4BLdZHS2Blfp4v" incurred?

```sql
-- gold
SELECT T1.first_name, T1.last_name, SUM(T2.cost) FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.member_id = 'rec4BLdZHS2Blfp4v'
-- candidate
SELECT 
  t1.first_name || ' ' || t1.last_name AS full_name,
  SUM(t2.cost) AS total_cost
FROM member t1
JOIN expense t2 ON t1.member_id = t2.link_to_member
WHERE t1.member_id = 'rec4BLdZHS2Blfp4v'
GROUP BY t1.member_id, t1.first_name, t1.last_name;
```
comparator: result sets differ

### `1411` · student_club · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** State what kind of expenses that Sacha Harrison incurred?

```sql
-- gold
SELECT T2.expense_description FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.first_name = 'Sacha' AND T1.last_name = 'Harrison'
-- candidate
SELECT NULL AS expense_description WHERE 1 = 0
```
comparator: result sets differ

### `1422` · student_club · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** State the category of events were held at MU 215.

```sql
-- gold
SELECT DISTINCT T2.category FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.location = 'MU 215'
-- candidate
SELECT T1.category FROM budget AS T1 INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id WHERE T2.location = 'MU 215'
```
comparator: result sets differ

### `1427` · student_club · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** What are the budget category of the events located at MU 215 and a guest speaker type with a 0 budget spent?

```sql
-- gold
SELECT DISTINCT T2.category, T1.type FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.location = 'MU 215' AND T2.spent = 0 AND T1.type = 'Guest Speaker'
-- candidate
SELECT budget.category FROM budget JOIN event ON budget.link_to_event = event.event_id WHERE event.location = 'MU 215' AND event.type = 'Guest Speaker' AND budget.spent = 0
```
comparator: result sets differ

### `1435` · student_club · moderate · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** List the names of closed event as "game" that was closed from 3/15/2019 to 3/20/2020.

```sql
-- gold
SELECT DISTINCT event_name FROM event WHERE type = 'Game' AND date(SUBSTR(event_date, 1, 10)) BETWEEN '2019-03-15' AND '2020-03-20' AND status = 'Closed'
-- candidate
SELECT event_name
FROM event
WHERE type = 'Game'
  AND status = 'Closed'
  AND event_date BETWEEN '2019-03-15T00:00:00' AND '2020-03-20T23:59:59';
```
comparator: result sets differ

### `1460` · student_club · challenging · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Write the full name of the member who spent money for water, veggie tray and supplies and include the cost of it.

```sql
-- gold
SELECT T2.first_name, T2.last_name, T1.cost FROM expense AS T1 INNER JOIN member AS T2 ON T1.link_to_member = T2.member_id WHERE T1.expense_description = 'Water, Veggie tray, supplies'
-- candidate
SELECT member.first_name || ' ' || member.last_name AS full_name, expense.cost FROM member JOIN expense ON member.member_id = expense.link_to_member WHERE expense.expense_description = 'Water, Veggie tray, supplies'
```
comparator: result sets differ

### `1149` · thrombosis_prediction · moderate · _wrong_answer_ · tags: aggregate_mismatch, where_mismatch, projection_count_mismatch

**Q:** Are there more in-patient or outpatient who were male? What is the deviation in percentage?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) AS REAL) * 100 / SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) FROM Patient WHERE SEX = 'M'
-- candidate
SELECT CASE WHEN COUNT(CASE WHEN SEX = 'M' AND Admission = '+' THEN 1 END) > COUNT(CASE WHEN SEX = 'M' AND Admission = '-' THEN 1 END) THEN 'in-patient' ELSE 'outpatient' END AS more_patients, (COUNT(CASE WHEN SEX = 'M' AND Admission = '+' THEN 1 END) * 100.0) / COUNT(CASE WHEN SEX = 'M' AND Admission = '-' THEN 1 END) AS deviation_percentage FROM Patient;
```
comparator: result sets differ

### `1152` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the ratio of outpatient to inpatient followed up treatment among all the 'SLE' diagnosed patient?

```sql
-- gold
SELECT SUM(CASE WHEN Admission = '+' THEN 1.0 ELSE 0 END) / SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) FROM Patient WHERE Diagnosis = 'SLE'
-- candidate
SELECT 
  CAST(SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) AS REAL) / 
  SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END)
FROM Patient
WHERE Diagnosis = 'SLE'
```
comparator: result sets differ

### `1166` · thrombosis_prediction · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What are the symptoms observed by the youngest patient to ever did a medical examination? Identify their diagnosis.

```sql
-- gold
SELECT T2.Symptoms, T1.Diagnosis FROM Patient AS T1 INNER JOIN Examination AS T2 ON T1.ID = T2.ID WHERE T2.Symptoms IS NOT NULL ORDER BY T1.Birthday DESC LIMIT 1
-- candidate
SELECT 
  t1.Symptoms, 
  t1.Diagnosis 
FROM Examination AS t1 
INNER JOIN Patient AS t2 
  ON t1.ID = t2.ID 
WHERE t1.Symptoms IS NOT NULL 
ORDER BY t2.Birthday DESC 
LIMIT 1;
```
comparator: result sets differ

### `1168` · thrombosis_prediction · challenging · _wrong_answer_ · tags: projection_count_mismatch

**Q:** The oldest SJS patient's medical laboratory work was completed on what date, and what age was the patient when they initially arrived at the hospital?

```sql
-- gold
SELECT T1.Date, STRFTIME('%Y', T2.`First Date`) - STRFTIME('%Y', T2.Birthday),T2.Birthday FROM Laboratory AS T1 INNER JOIN Patient AS T2 ON T1.ID = T2.ID WHERE T2.Diagnosis = 'SJS' AND T2.Birthday IS NOT NULL ORDER BY T2.Birthday ASC LIMIT 1
-- candidate
SELECT 
  t1.Date,
  (CAST(strftime('%Y', t2.First_Date) AS INTEGER) - CAST(strftime('%Y', t2.Birthday) AS INTEGER)) AS Initial_Age
FROM Laboratory AS t1
INNER JOIN (
  SELECT ID, Birthday, `First Date` AS First_Date
  FROM Patient
  WHERE Diagnosis LIKE '%SJS%'
  ORDER BY Birthday ASC
  LIMIT 1
) AS t2 ON t1.ID = t2.ID;
```
comparator: result sets differ

### `1169` · thrombosis_prediction · challenging · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the ratio of male to female patients among all those with abnormal uric acid counts?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.UA <= 8.0 AND T1.SEX = 'M' THEN 1 ELSE 0 END) AS REAL) / SUM(CASE WHEN T2.UA <= 6.5 AND T1.SEX = 'F' THEN 1 ELSE 0 END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
-- candidate
SELECT 
  (CAST(SUM(CASE WHEN t2.SEX = 'M' AND t1.UA > 8.0 THEN 1 ELSE 0 END) AS REAL) / 
   NULLIF(SUM(CASE WHEN t2.SEX = 'F' AND t1.UA > 6.5 THEN 1 ELSE 0 END), 0)) AS ratio
FROM Laboratory t1
JOIN Patient t2 ON t1.ID = t2.ID;
```
comparator: result sets differ

### `1171` · thrombosis_prediction · challenging · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many underage patients were examined during the course of the three-year period from 1990 to 1993?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Examination AS T2 ON T1.ID = T2.ID WHERE STRFTIME('%Y', T2.`Examination Date`) BETWEEN '1990' AND '1993' AND STRFTIME('%Y', T2.`Examination Date`) - STRFTIME('%Y', T1.Birthday) < 18
-- candidate
SELECT Count(DISTINCT Patient.ID)
FROM Patient
INNER JOIN Examination ON Patient.ID = Examination.ID
WHERE CAST(strftime('%Y', Patient.Birthday) AS INTEGER) < 18
  AND strftime('%Y', Examination.`Examination Date`) BETWEEN '1990' AND '1993'
```
comparator: result sets differ

### `1175` · thrombosis_prediction · moderate · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** How old was the patient who had the highest hemoglobin count at the time of the examination, and what is the doctor's diagnosis?

```sql
-- gold
SELECT STRFTIME('%Y', T2.Date) - STRFTIME('%Y', T1.Birthday), T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID ORDER BY T2.HGB DESC LIMIT 1
-- candidate
This is standard and clean.
I will output this.
```
comparator: —

### `1179` · thrombosis_prediction · moderate · _wrong_answer_ · tags: join_mismatch, projection_count_mismatch

**Q:** For the patient who was diagnosed with SLE on 1994/2/19, what was his/her anti-Cardiolipin antibody concentration status on 1993/11/12?

```sql
-- gold
SELECT `aCL IgA`, `aCL IgG`, `aCL IgM` FROM Examination WHERE ID IN ( SELECT ID FROM Patient WHERE Diagnosis = 'SLE' AND Description = '1994-02-19' ) AND `Examination Date` = '1993-11-12'
-- candidate
SELECT
  t1.`aCL IgM`
FROM Examination AS t1
INNER JOIN Patient AS t2
  ON t1.ID = t2.ID
WHERE
  t2.Diagnosis = 'SLE'
  AND t2.Description = '1994-02-19'
  AND t1.`Examination Date` = '1993-11-12'
```
comparator: result sets differ

### `1189` · thrombosis_prediction · challenging · _wrong_answer_ · tags: join_mismatch, distinct_mismatch

**Q:** What number of patients with a degree of thrombosis level 2 and ANA pattern of only S, have a level of anti-Cardiolip in antibody (IgM) 20% higher than average?

```sql
-- gold
SELECT COUNT(*) FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S' AND `aCL IgM` > (SELECT AVG(`aCL IgM`) * 1.2 FROM Examination WHERE Thrombosis = 2 AND `ANA Pattern` = 'S')
-- candidate
SELECT count(DISTINCT T1.ID)
FROM Examination AS T1
CROSS JOIN (
  SELECT avg(`aCL IgM`) AS avg_igm
  FROM Examination
) AS T2
WHERE T1.Thrombosis = 2
  AND T1.`ANA Pattern` = 'S'
  AND T1.`aCL IgM` > T2.avg_igm * 1.20;
```
comparator: result sets differ

### `1205` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** Was the patient with the number 57266's uric acid within a normal range?

```sql
-- gold
SELECT CASE WHEN (T1.SEX = 'F' AND T2.UA > 6.5) OR (T1.SEX = 'M' AND T2.UA > 8.0) THEN true ELSE false END FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T1.ID = 57266
-- candidate
SELECT 
  CASE 
    WHEN (SEX = 'M' AND NOT (e.`aCL IgG` > 8.0)) OR (SEX = 'F' AND NOT (e.`aCL IgG` > 6.5)) THEN 'Yes'
    ELSE 'No'
  END AS UA_Within_Normal
FROM Patient p
JOIN Examination e ON p.ID = e.ID
WHERE p.ID = 57266;
```
comparator: result sets differ

### `1209` · thrombosis_prediction · moderate · _wrong_answer_ · tags: group_by_mismatch, distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Please provide the diagnosis of patients with ALT glutamic pylvic transaminase beyond the normal range by ascending order of their date of birth.

```sql
-- gold
SELECT DISTINCT T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.GPT > 60 ORDER BY T1.Birthday ASC
-- candidate
SELECT T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.GPT > 60 GROUP BY T1.ID ORDER BY T1.Birthday ASC
```
comparator: result sets differ

### `1225` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** List and group all patients by sex for total bilirubin (T-BIL) level not within the normal range.

```sql
-- gold
SELECT T1.ID,T1.SEX FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.`T-BIL` >= 2.0 GROUP BY T1.SEX,T1.ID
-- candidate
SELECT SEX, GROUP_CONCAT(DISTINCT Patient.ID) FROM Patient JOIN Laboratory ON Patient.ID = Laboratory.ID WHERE Laboratory.`T-BIL` >= 2.0 GROUP BY SEX;
```
comparator: result sets differ

### `1231` · thrombosis_prediction · challenging · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, spurious_join

**Q:** For patient born between 1936-1956, how many male patients have creatinine phosphokinase beyond the normal range?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE STRFTIME('%Y', T1.Birthday) BETWEEN '1936' AND '1956' AND T1.SEX = 'M' AND T2.CPK >= 250
-- candidate
SELECT COUNT(DISTINCT t1.ID) FROM Patient AS t1 INNER JOIN WORK_UP AS t2 ON t1.ID = t2.ID WHERE strftime('%Y', t1.Birthday) BETWEEN '1936' AND '1956' AND t1.SEX = 'M' AND t2.CPK >= 250
```
comparator: —

### `1235` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What are the patient's diagnosis for those who has lower red blood blood cell? State their ID and age.

```sql
-- gold
SELECT DISTINCT T1.Diagnosis, T1.ID , STRFTIME('%Y', CURRENT_TIMESTAMP) -STRFTIME('%Y', T1.Birthday) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.RBC < 3.5
-- candidate
SELECT DISTINCT
  Patient.ID,
  (strftime('%Y', 'now') - strftime('%Y', Patient.Birthday)) AS age,
  Patient.Diagnosis
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Laboratory.RBC < 3.5;
```
comparator: result sets differ

### `1241` · thrombosis_prediction · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, where_mismatch

**Q:** For patients with abnormal platelet level, state the number of patients with lower than normal range. How is it compare to the number of patients with higher than normal range?

```sql
-- gold
SELECT SUM(CASE WHEN T2.PLT <= 100 THEN 1 ELSE 0 END) - SUM(CASE WHEN T2.PLT >= 400 THEN 1 ELSE 0 END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
-- candidate
SELECT 
  SUM(CASE WHEN PLT < 100 THEN 1 ELSE 0 END) - SUM(CASE WHEN PLT > 400 THEN 1 ELSE 0 END) AS result
FROM Laboratory
WHERE PLT <= 100 OR PLT >= 400;
```
comparator: result sets differ

### `1242` · thrombosis_prediction · challenging · _wrong_answer_ · tags: distinct_mismatch

**Q:** For laboratory examinations take in 1984, list all patients below 50 years old with normal platelet level.

```sql
-- gold
SELECT DISTINCT T1.ID FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.PLT BETWEEN 100 AND 400 AND STRFTIME('%Y', T2.Date) - STRFTIME('%Y', T1.Birthday) < 50 AND STRFTIME('%Y', T2.Date) = '1984'
-- candidate
SELECT T1.ID FROM Patient AS T1 JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE strftime('%Y', T2.Date) = '1984' AND T2.PLT BETWEEN 100 AND 400 AND (strftime('%Y', 'now') - strftime('%Y', T1.Birthday)) < 50
```
comparator: result sets differ

### `1243` · thrombosis_prediction · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** For all patients who are older than 55 years old, what is the percentage of female who has abnormal prothrombin time (PT)?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.PT >= 14 AND T1.SEX = 'F' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(CASE WHEN T2.PT >= 14 THEN 1 ELSE 0 END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE STRFTIME('%Y', CURRENT_TIMESTAMP) - STRFTIME('%Y', T1.Birthday) > 55
-- candidate
SELECT 
  (CAST(SUM(CASE WHEN l.PT >= 14 AND p.SEX = 'F' THEN 1 ELSE 0 END) AS REAL) / 
   SUM(CASE WHEN l.PT >= 14 THEN 1 ELSE 0 END)) * 100 AS Percentage
FROM Patient p
JOIN Laboratory l ON p.ID = l.ID
WHERE (strftime('%Y', 'now') - strftime('%Y', p.Birthday)) > 55;
```
comparator: result sets differ

### `1247` · thrombosis_prediction · challenging · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** Among the male patients who have a normal level of white blood cells, how many of them have an abnormal fibrinogen level?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.FG <= 150 OR T2.FG >= 450 AND T2.WBC > 3.5 AND T2.WBC < 9.0 AND T1.SEX = 'M'
-- candidate
SELECT COUNT(DISTINCT Patient.ID)
FROM Patient
WHERE Patient.SEX = 'M'
  AND EXISTS (
    -- Even though the database schema provided does not contain WBC or FG columns,
    -- following the rules and external knowledge guidelines, we write the logical 
    -- query structure representation if we assume those columns exist or if WBC/FG 
    -- are hypothetical. Since SQLite tables provided do not contain WBC/FG,
    -- the standard treatment of such questions is to assume they are on the Patient or Examination table.
    -- Assuming WBC and FG columns might be present in a Lab table or just Patient/Examination:
  );
```
comparator: —

### `1251` · thrombosis_prediction · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** How many patients with an Ig G higher than normal?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE T2.IGG >= 2000
-- candidate
SELECT COUNT(DISTINCT ID) FROM Examination WHERE "aCL IgG" >= 2000;
```
comparator: result sets differ

### `1252` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** Among the patients with a normal Ig G level, how many of them have symptoms?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE T2.IGG BETWEEN 900 AND 2000 AND T3.Symptoms IS NOT NULL
-- candidate
SELECT COUNT(DISTINCT Examination.ID) FROM Examination WHERE Examination.[aCL IgG] > 900 AND Examination.[aCL IgG] < 2000 AND Examination.Symptoms IS NOT NULL
```
comparator: result sets differ

### `1254` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many patients with a normal Ig A level came to the hospital after 1990/1/1?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.IGA BETWEEN 80 AND 500 AND  strftime('%Y',  T1.`First Date`) > '1990'
-- candidate
SELECT COUNT(DISTINCT Patient.ID) AS patient_count
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Laboratory.IGA > 80 AND Laboratory.IGA < 500
  AND strftime('%Y', Patient.`First Date`) >= '1990';
```
comparator: result sets differ

### `1255` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** For the patients with an abnormal Ig M level, what is the most common disease they are diagnosed with?

```sql
-- gold
SELECT T1.Diagnosis FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.IGM NOT BETWEEN 40 AND 400 GROUP BY T1.Diagnosis ORDER BY COUNT(T1.Diagnosis) DESC LIMIT 1
-- candidate
SELECT T1.Diagnosis FROM Patient AS T1 JOIN Examination AS T2 ON T1.ID = T2.ID WHERE T2."aCL IgM" <= 40 OR T2."aCL IgM" >= 400 GROUP BY T1.Diagnosis ORDER BY count(*) DESC LIMIT 1
```
comparator: result sets differ

### `1256` · thrombosis_prediction · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many patients with a abnormal C-reactive protein don't have their data recorded?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE (T2.CRP = '+' ) AND T1.Description IS NULL
-- candidate
SELECT COUNT(DISTINCT Patient.ID) AS patient_count
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Laboratory.CRP = '+' AND Patient.Description IS NULL;
```
comparator: result sets differ

### `1265` · thrombosis_prediction · moderate · _execution_error_final_ · tags: table_mismatch, missing_table, extra_table

**Q:** How many patients have a normal level of anti-ribonuclear protein and have been admitted to the hospital?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.RNP = 'negative' OR T2.RNP = '0' AND T1.Admission = '+'
-- candidate
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 JOIN Examination AS T2 ON T1.ID = T2.ID WHERE T1.Admission = '+' AND T2.RNP IN ('-', '+-')
```
comparator: —

### `1267` · thrombosis_prediction · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, distinct_mismatch

**Q:** Among the patients with normal anti-SM, how many of them does not have thrombosis?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Examination AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.SM IN ('negative','0') AND T1.Thrombosis = 0
-- candidate
SELECT count(DISTINCT Patient.ID)
FROM Patient
INNER JOIN Laboratory ON Patient.ID = Laboratory.ID
INNER JOIN Examination ON Patient.ID = Examination.ID
WHERE (Laboratory.SM IN ('-', '+-') OR Laboratory.SM = 'negative' OR Laboratory.SM = '0')
  AND Examination.Thrombosis = 0;
```
comparator: result sets differ

### `1270` · thrombosis_prediction · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** Among the patients who has a normal anti-scl70, how many of them are female and does not have any symptom?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T3.ID = T2.ID WHERE (T2.SC170 = 'negative' OR T2.SC170 = '0') AND T1.SEX = 'F' AND T3.Symptoms IS NULL
-- candidate
SELECT COUNT(DISTINCT Patient.ID) FROM Patient JOIN Examination ON Patient.ID = Examination.ID WHERE Patient.SEX = 'F' AND Examination.Symptoms IS NULL
```
comparator: result sets differ

### `1275` · thrombosis_prediction · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Among the patients who has a normal level of anti-centromere and a normal level of anti-SSB, how many of them are male?

```sql
-- gold
SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.CENTROMEA IN ('negative', '0') AND T2.SSB IN ('negative', '0') AND T1.SEX = 'M'
-- candidate
SELECT COUNT(DISTINCT Patient.ID) AS count
FROM Patient
JOIN Laboratory ON Patient.ID = Laboratory.ID
WHERE Laboratory.CENTROMEA IN ('-','+-')
  AND Laboratory.SSB IN ('-','+-')
  AND Patient.SEX = 'M';
```
comparator: result sets differ

### `1302` · thrombosis_prediction · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** For the patients with a normal range of creatinine phosphokinase, how many of them have a positive measure of degree of coagulation?

```sql
-- gold
SELECT COUNT(T1.ID) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID INNER JOIN Examination AS T3 ON T1.ID = T3.ID WHERE T2.CPK < 250 AND (T3.KCT = '+' OR T3.RVVT = '+' OR T3.LAC = '+')
-- candidate
SELECT COUNT(DISTINCT Patient.ID) FROM Patient JOIN Examination ON Patient.ID = Examination.ID WHERE (Examination.KCT = '+' OR Examination.RVVT = '+' OR Examination.LAC = '+')
```
comparator: result sets differ

### `1029` · european_football_2 · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** What are the speed in which attacks are put together of the top 4 teams with the highest build Up Play Speed?

```sql
-- gold
SELECT t1.buildUpPlaySpeed FROM Team_Attributes AS t1 INNER JOIN Team AS t2 ON t1.team_api_id = t2.team_api_id ORDER BY t1.buildUpPlaySpeed ASC LIMIT 4
-- candidate
SELECT DISTINCT T.team_long_name, TA.buildUpPlaySpeed
FROM Team AS T
JOIN Team_Attributes AS TA ON T.team_api_id = TA.team_api_id
ORDER BY TA.buildUpPlaySpeed DESC
LIMIT 4;
```
comparator: result sets differ

### `1031` · european_football_2 · challenging · _wrong_answer_ · tags: projection_count_mismatch

**Q:** At present, calculate for the player's age who have a sprint speed of no less than 97 between 2013 to 2015.

```sql
-- gold
SELECT DISTINCT DATETIME() - T2.birthday age FROM Player_Attributes AS t1 INNER JOIN Player AS t2 ON t1.player_api_id = t2.player_api_id WHERE STRFTIME('%Y',t1.`date`) >= '2013' AND STRFTIME('%Y',t1.`date`) <= '2015' AND t1.sprint_speed >= 97
-- candidate
SELECT DISTINCT player_name, (strftime('%Y', 'now') - strftime('%Y', birthday)) AS age FROM Player JOIN Player_Attributes ON Player.player_api_id = Player_Attributes.player_api_id WHERE Player_Attributes.sprint_speed >= 97 AND strftime('%Y', Player_Attributes.date) >= '2013' AND strftime('%Y', Player_Attributes.date) <= '2015'
```
comparator: result sets differ

### `1032` · european_football_2 · moderate · _wrong_answer_ · tags: aggregate_mismatch, limit_mismatch

**Q:** Give the name of the league with the highest matches of all time and how many matches were played in the said league.

```sql
-- gold
SELECT t2.name, t1.max_count FROM League AS t2 JOIN (SELECT league_id, MAX(cnt) AS max_count FROM (SELECT league_id, COUNT(id) AS cnt FROM Match GROUP BY league_id) AS subquery) AS t1 ON t1.league_id = t2.id
-- candidate
SELECT L.name, COUNT(M.id) AS match_count FROM Match M JOIN League L ON M.league_id = L.id GROUP BY L.name ORDER BY match_count DESC LIMIT 1;
```
comparator: result sets differ

### `1035` · european_football_2 · simple · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** Give the team_fifa_api_id of teams with more than 50 but less than 60 build-up play speed.

```sql
-- gold
SELECT DISTINCT team_fifa_api_id FROM Team_Attributes WHERE buildUpPlaySpeed > 50 AND buildUpPlaySpeed < 60
-- candidate
AS0SELECT DISTINCT team_fifa_api_id FROM Team_Attributes WHERE buildUpPlaySpeed > 50 AND buildUpPlaySpeed < 60;
```
comparator: —

### `1036` · european_football_2 · challenging · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch, distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** List the long name of teams with above-average build-up play passing in 2012.

```sql
-- gold
SELECT DISTINCT t4.team_long_name FROM Team_Attributes AS t3 INNER JOIN Team AS t4 ON t3.team_api_id = t4.team_api_id WHERE SUBSTR(t3.`date`, 1, 4) = '2012' AND t3.buildUpPlayPassing > ( SELECT CAST(SUM(t2.buildUpPlayPassing) AS REAL) / COUNT(t1.id) FROM Team AS t1 INNER JOIN Team_Attributes AS t2 ON t1.team_api_id = t2.team_api_id WHERE STRFTIME('%Y',t2.`date`) = '2012')
-- candidate
SELECT t.team_long_name FROM Team AS t JOIN Team_Attributes AS ta ON t.team_api_id = ta.team_api_id WHERE strftime('%Y', ta.date) = '2012' AND ta.buildUpPlayPassing > (SELECT AVG(buildUpPlayPassing) FROM Team_Attributes WHERE strftime('%Y', date) = '2012')
```
comparator: result sets differ

### `1040` · european_football_2 · moderate · _wrong_answer_ · tags: aggregate_mismatch · **BIRD-ok (scorer artifact)**

**Q:** List the top 10 players' names whose heights are above 180 in descending order of average heading accuracy.

```sql
-- gold
SELECT t1.player_name FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE t1.height > 180 GROUP BY t1.id ORDER BY CAST(SUM(t2.heading_accuracy) AS REAL) / COUNT(t2.`player_fifa_api_id`) DESC LIMIT 10
-- candidate
SELECT p.player_name FROM Player p JOIN Player_Attributes pa ON p.player_api_id = pa.player_api_id WHERE p.height > 180 GROUP BY p.player_api_id, p.player_name ORDER BY AVG(pa.heading_accuracy) DESC LIMIT 10;
```
comparator: result sets differ

### `1058` · european_football_2 · challenging · _wrong_answer_ · tags: join_mismatch, group_by_mismatch

**Q:** Who has the highest average finishing rate between the highest and shortest football player?

```sql
-- gold
SELECT A FROM ( SELECT AVG(finishing) result, 'Max' A FROM Player AS T1 INNER JOIN Player_Attributes AS T2 ON T1.player_api_id = T2.player_api_id WHERE T1.height = ( SELECT MAX(height) FROM Player ) UNION SELECT AVG(finishing) result, 'Min' A FROM Player AS T1 INNER JOIN Player_Attributes AS T2 ON T1.player_api_id = T2.player_api_id WHERE T1.height = ( SELECT MIN(height) FROM Player ) ) ORDER BY result DESC LIMIT 1
-- candidate
SELECT p.player_name
FROM Player p
JOIN Player_Attributes pa ON p.player_api_id = pa.player_api_id
WHERE p.height = (SELECT MAX(height) FROM Player) OR p.height = (SELECT MIN(height) FROM Player)
GROUP BY p.player_api_id, p.player_name
ORDER BY AVG(pa.finishing) DESC
LIMIT 1;
```
comparator: result sets differ

### `1068` · european_football_2 · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** From 2010 to 2015, what was the average overall rating of players who are higher than 170?

```sql
-- gold
SELECT CAST(SUM(t2.overall_rating) AS REAL) / COUNT(t2.id) FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE t1.height > 170 AND STRFTIME('%Y',t2.`date`) >= '2010' AND STRFTIME('%Y',t2.`date`) <= '2015'
-- candidate
SELECT AVG(t2.overall_rating) FROM Player AS t1 JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE strftime('%Y', t2.date) >= '2010' AND strftime('%Y', t2.date) <= '2015' AND t1.height > 170
```
comparator: result sets differ

### `1080` · european_football_2 · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** Among the players whose preferred foot was the left foot when attacking, how many of them would remain in his position when the team attacked?

```sql
-- gold
SELECT COUNT(player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left' AND attacking_work_rate = 'low'
-- candidate
SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left' AND attacking_work_rate = 'low';
```
comparator: result sets differ

### `1092` · european_football_2 · simple · _wrong_answer_ · tags: aggregate_mismatch, limit_mismatch

**Q:** Give the name of the league had the most matches in the 2008/2009 season?

```sql
-- gold
SELECT t1.name FROM League AS t1 JOIN Match AS t2 ON t1.id = t2.league_id WHERE t2.season = '2008/2009' GROUP BY t1.name HAVING COUNT(t2.id) = (SELECT MAX(match_count) FROM (SELECT COUNT(t2.id) AS match_count FROM Match AS t2 WHERE t2.season = '2008/2009' GROUP BY t2.league_id))
-- candidate
SELECT League.name
FROM Match
JOIN League ON Match.league_id = League.id
WHERE Match.season = '2008/2009'
GROUP BY League.id, League.name
ORDER BY COUNT(Match.id) DESC
LIMIT 1;
```
comparator: result sets differ

### `1094` · european_football_2 · challenging · _guardrail_rejected_ · tags: join_mismatch, aggregate_mismatch, where_mismatch

**Q:** How much higher in percentage is Ariel Borysiuk's overall rating than that of Paulin Puel?

```sql
-- gold
SELECT (SUM(CASE WHEN t1.player_name = 'Ariel Borysiuk' THEN t2.overall_rating ELSE 0 END) * 1.0 - SUM(CASE WHEN t1.player_name = 'Paulin Puel' THEN t2.overall_rating ELSE 0 END)) * 100 / SUM(CASE WHEN t1.player_name = 'Paulin Puel' THEN t2.overall_rating ELSE 0 END) FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id
-- candidate
SELECT 
  ((A.avg_rating - B.avg_rating) / B.avg_rating) * 100
FROM (
  SELECT AVG(overall_rating) AS avg_rating
  FROM Player_Attributes
  JOIN Player ON Player.player_api_id = Player_Attributes.player_api_id
  WHERE Player.player_name = 'Ariel Borysiuk'
) A, (
  SELECT AVG(overall_rating) AS avg_rating
  FROM Player_Attributes
  JOIN Player ON Player.player_api_id = Player_Attributes.player_api_id
  WHERE Player.player_name = 'Paulin Puel'
) B
```
comparator: —

### `1107` · european_football_2 · moderate · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch

**Q:** When was the first time did Kevin Constant have his highest crossing score? Give the date.

```sql
-- gold
SELECT `date` FROM ( SELECT t2.crossing, t2.`date` FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_fifa_api_id = t2.player_fifa_api_id WHERE t1.player_name = 'Kevin Constant' ORDER BY t2.crossing DESC) ORDER BY date DESC LIMIT 1
-- candidate
SELECT PA.date
FROM Player_Attributes AS PA
JOIN Player AS P ON PA.player_api_id = P.player_api_id
WHERE P.player_name = 'Kevin Constant' 
  AND PA.crossing = (
    SELECT MAX(PA2.crossing)
    FROM Player_Attributes AS PA2
    JOIN Player AS P2 ON PA2.player_api_id = P2.player_api_id
    WHERE P2.player_name = 'Kevin Constant'
  )
ORDER BY PA.date ASC
LIMIT 1;
```
comparator: result sets differ

### `1115` · european_football_2 · challenging · _guardrail_rejected_ · tags: join_mismatch, aggregate_mismatch · **BIRD-ok (scorer artifact)**

**Q:** What percentage is Landon Donovan's overall rating higher than Jordan Bowery on 2013/7/12?

```sql
-- gold
SELECT (SUM(CASE WHEN t1.player_name = 'Landon Donovan' THEN t2.overall_rating ELSE 0 END) * 1.0 - SUM(CASE WHEN t1.player_name = 'Jordan Bowery' THEN t2.overall_rating ELSE 0 END)) * 100 / SUM(CASE WHEN t1.player_name = 'Landon Donovan' THEN t2.overall_rating ELSE 0 END) LvsJ_percent FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_fifa_api_id = t2.player_fifa_api_id WHERE SUBSTR(t2.`date`, 1, 10) = '2013-07-12'
-- candidate
SELECT 
  ((p1.overall_rating - p2.overall_rating) * 100.0) / p1.overall_rating AS rating_percentage_difference
FROM 
  (
    SELECT pa.overall_rating 
    FROM Player_Attributes pa
    JOIN Player p ON pa.player_api_id = p.player_api_id
    WHERE p.player_name = 'Landon Donovan' AND pa.date LIKE '2013-07-12%'
  ) AS p1,
  (
    SELECT pa.overall_rating 
    FROM Player_Attributes pa
    JOIN Player p ON pa.player_api_id = p.player_api_id
    WHERE p.player_name = 'Jordan Bowery' AND pa.date LIKE '2013-07-12%'
  ) AS p2;
```
comparator: —

### `1135` · european_football_2 · moderate · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch

**Q:** Please provide top four football players' IDs who are among the lowest potential players and prefer to use the right foot when attacking.

```sql
-- gold
SELECT id FROM Player_Attributes WHERE preferred_foot = 'right' ORDER BY potential ASC LIMIT 4
-- candidate
SELECT player_api_id FROM Player_Attributes WHERE preferred_foot = 'right' GROUP BY player_api_id ORDER BY MIN(potential) ASC LIMIT 4;
```
comparator: result sets differ

### `1136` · european_football_2 · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many players had the highest potential score for crossing that preferred to use their left foots while attacking?

```sql
-- gold
SELECT COUNT(t1.id) FROM Player_Attributes AS t1 WHERE t1.preferred_foot = 'left' AND t1.crossing = ( SELECT MAX(crossing) FROM Player_Attributes)
-- candidate
SELECT count(DISTINCT player_api_id)
FROM Player_Attributes
WHERE crossing = (SELECT MAX(crossing) FROM Player_Attributes)
  AND preferred_foot = 'left';
```
comparator: result sets differ

### `1144` · european_football_2 · simple · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch, projection_count_mismatch

**Q:** Please state the finishing rate and curve score of the player who has the heaviest weight.

```sql
-- gold
SELECT id, finishing, curve FROM Player_Attributes WHERE player_api_id = ( SELECT player_api_id FROM Player ORDER BY weight DESC LIMIT 1 ) LIMIT 1
-- candidate
SELECT
  pa.finishing,
  pa.curve
FROM Player AS p
INNER JOIN Player_Attributes AS pa
  ON p.player_api_id = pa.player_api_id
WHERE p.weight = (SELECT MAX(weight) FROM Player)
ORDER BY pa.date DESC
LIMIT 1;
```
comparator: result sets differ

### `1145` · european_football_2 · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Which top 4 leagues had the most games in the 2015-2016 season?

```sql
-- gold
SELECT t1.name FROM League AS t1 INNER JOIN Match AS t2 ON t1.id = t2.league_id WHERE t2.season = '2015/2016' GROUP BY t1.name ORDER BY COUNT(t2.id) DESC LIMIT 4
-- candidate
SELECT
  L.name,
  COUNT(M.id) AS num_matches
FROM Match AS M
JOIN League AS L ON M.league_id = L.id
WHERE M.season = '2015/2016'
GROUP BY L.name
ORDER BY num_matches DESC
LIMIT 4;
```
comparator: result sets differ

### `847` · formula_1 · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the surname of the driver with the best lap time in race number 19 in the second qualifying period?

```sql
-- gold
SELECT T2.surname FROM qualifying AS T1 INNER JOIN drivers AS T2 ON T2.driverId = T1.driverId WHERE T1.raceId = 19 ORDER BY T1.q2 ASC LIMIT 1
-- candidate
SELECT drivers.surname FROM qualifying JOIN drivers ON qualifying.driverId = drivers.driverId WHERE qualifying.raceId = 19 AND qualifying.q2 IS NOT NULL AND qualifying.q2 != '' ORDER BY qualifying.q2 ASC LIMIT 1;
```
comparator: result sets differ

### `866` · formula_1 · moderate · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Who was the player that got the lap time of 0:01:27 in the race No. 161? Show his introduction website.

```sql
-- gold
SELECT DISTINCT T2.forename, T2.surname, T2.url FROM lapTimes AS T1 INNER JOIN drivers AS T2 ON T2.driverId = T1.driverId WHERE T1.raceId = 161 AND T1.time LIKE '1:27%'
-- candidate
SELECT T1.forename, T1.surname, T1.url FROM drivers AS T1 INNER JOIN lapTimes AS T2 ON T1.driverId = T2.driverId WHERE T2.raceId = 161 AND T2.time LIKE '1:27%'
```
comparator: result sets differ

### `881` · formula_1 · moderate · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, spurious_join

**Q:** For the drivers who took part in the race in 1983/7/16, what's their race completion rate?

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T2.time IS NOT NULL THEN T2.driverId END) AS REAL) * 100 / COUNT(T2.driverId) FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId WHERE T1.date = '1983-07-16'
-- candidate
SELECT
  (CAST(COUNT(CASE WHEN r.statusId IN (1, 11, 12, 13, 14, 15, 16, 17, 18, 19) THEN 1 END) AS REAL) / COUNT(*)) * 100.0 AS completion_rate
FROM raceResults AS r
JOIN races AS ra ON r.raceId = ra.raceId
WHERE ra.date = '1983-07-16';
```
comparator: —

### `892` · formula_1 · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, aggregate_mismatch, group_by_mismatch, limit_mismatch, projection_count_mismatch

**Q:** State the driver with the most points scored. Find his full name with that points.

```sql
-- gold
SELECT T3.forename, T3.surname, T2.points FROM races AS T1 INNER JOIN driverStandings AS T2 ON T2.raceId = T1.raceId INNER JOIN drivers AS T3 ON T3.driverId = T2.driverId ORDER BY T2.points DESC LIMIT 1
-- candidate
SELECT 
  d.forename || ' ' || d.surname AS full_name,
  MAX(ds.total_points) AS total_points
FROM drivers d
JOIN (
  SELECT 
    driverId, 
    SUM(points) AS total_points 
  FROM results 
  GROUP BY driverId
) ds ON d.driverId = ds.driverId;
```
comparator: result sets differ

### `894` · formula_1 · moderate · _wrong_answer_ · tags: aggregate_mismatch, where_mismatch, limit_mismatch, projection_count_mismatch

**Q:** What is the best lap time recorded? List the driver and race with such recorded lap time.

```sql
-- gold
SELECT T2.milliseconds, T1.forename, T1.surname, T3.name FROM drivers AS T1 INNER JOIN lapTimes AS T2 ON T1.driverId = T2.driverId INNER JOIN races AS T3 ON T2.raceId = T3.raceId ORDER BY T2.milliseconds ASC LIMIT 1
-- candidate
SELECT drivers.forename, drivers.surname, races.name
FROM lapTimes
JOIN drivers ON lapTimes.driverId = drivers.driverId
JOIN races ON lapTimes.raceId = races.raceId
WHERE lapTimes.milliseconds = (SELECT MIN(milliseconds) FROM lapTimes);
```
comparator: result sets differ

### `896` · formula_1 · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** Calculate the percentage whereby Hamilton was not at the 1st track of the the f1 circuit since 2010.

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T2.position <> 1 THEN T2.position END) AS REAL) * 100 / COUNT(T2.driverStandingsId) FROM races AS T1 INNER JOIN driverStandings AS T2 ON T2.raceId = T1.raceId INNER JOIN drivers AS T3 ON T3.driverId = T2.driverId WHERE T3.surname = 'Hamilton' AND T1.year >= 2010
-- candidate
SELECT 
  (CAST(COUNT(CASE WHEN d.surname = 'Hamilton' AND r.position > 1 THEN 1 END) AS REAL) / 
   COUNT(CASE WHEN d.surname = 'Hamilton' THEN 1 END)) * 100 AS percentage
FROM results r
JOIN drivers d ON r.driverId = d.driverId
JOIN races ra ON r.raceId = ra.raceId
WHERE ra.year >= 2010;
```
comparator: result sets differ

### `897` · formula_1 · moderate · _wrong_answer_ · tags: aggregate_mismatch, projection_count_mismatch

**Q:** Name the driver with the most winning. Mention his nationality and what is his maximum point scores.

```sql
-- gold
SELECT T1.forename, T1.surname, T1.nationality, MAX(T2.points) FROM drivers AS T1 INNER JOIN driverStandings AS T2 ON T2.driverId = T1.driverId WHERE T2.wins >= 1 GROUP BY T1.forename, T1.surname, T1.nationality ORDER BY COUNT(T2.wins) DESC LIMIT 1
-- candidate
SELECT 
  d.forename || ' ' || d.surname AS driver_name,
  d.nationality,
  MAX(ds.points) AS max_points
FROM drivers d
JOIN driverStandings ds ON d.driverId = ds.driverId
WHERE d.driverId = (
  SELECT driverId 
  FROM driverStandings 
  GROUP BY driverId 
  ORDER BY SUM(wins) DESC 
  LIMIT 1
)
GROUP BY d.driverId, d.forename, d.surname, d.nationality;
```
comparator: result sets differ

### `902` · formula_1 · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** Which race was Alex Yoong in when he was in track number less than 20?

```sql
-- gold
SELECT T1.name FROM races AS T1 INNER JOIN driverStandings AS T2 ON T2.raceId = T1.raceId INNER JOIN drivers AS T3 ON T3.driverId = T2.driverId WHERE T3.forename = 'Alex' AND T3.surname = 'Yoong' AND T2.position < 20
-- candidate
SELECT r.name FROM races r JOIN results res ON r.raceId = res.raceId JOIN drivers d ON res.driverId = d.driverId WHERE d.forename = 'Alex' AND d.surname = 'Yoong' AND res.position < 20
```
comparator: result sets differ

### `915` · formula_1 · simple · _wrong_answer_ · tags: where_mismatch

**Q:** Which country is the oldest driver from?

```sql
-- gold
SELECT nationality FROM drivers WHERE dob IS NOT NULL ORDER BY dob ASC LIMIT 1
-- candidate
SELECT nationality 
FROM drivers 
ORDER BY dob ASC 
LIMIT 1;
```
comparator: result sets differ

### `928` · formula_1 · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, projection_count_mismatch

**Q:** Which driver ranked the first in the Canadian Grand Prix in 2007? Please give his reference name.

```sql
-- gold
SELECT T3.forename, T3.surname, T3.driverRef FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId INNER JOIN drivers AS T3 ON T3.driverId = T2.driverId WHERE T1.name = 'Canadian Grand Prix' AND T2.rank = 1 AND T1.year = 2007
-- candidate
SELECT t1.driverRef
FROM drivers AS t1
INNER JOIN driverStandings AS t2 ON t1.driverId = t2.driverId
INNER JOIN races AS t3 ON t2.raceId = t3.raceId
WHERE t3.name = 'Canadian Grand Prix' 
  AND t3.year = 2007 
  AND t2.position = 1;
```
comparator: result sets differ

### `930` · formula_1 · simple · _wrong_answer_ · tags: join_mismatch, limit_mismatch

**Q:** In which Formula_1 race did Lewis Hamilton rank the highest?

```sql
-- gold
SELECT name FROM races WHERE raceId IN ( SELECT raceId FROM results WHERE rank = 1 AND driverId = ( SELECT driverId FROM drivers WHERE forename = 'Lewis' AND surname = 'Hamilton' ) )
-- candidate
SELECT races.name FROM results JOIN races ON results.raceId = races.raceId JOIN drivers ON results.driverId = drivers.driverId WHERE drivers.forename = 'Lewis' AND drivers.surname = 'Hamilton' ORDER BY results.rank ASC LIMIT 1;
```
comparator: result sets differ

### `931` · formula_1 · moderate · _wrong_answer_ · tags: aggregate_mismatch, limit_mismatch

**Q:** What was the fastest lap speed among all drivers in the 2009 Spanish Grand Prix?

```sql
-- gold
SELECT T2.fastestLapSpeed FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId WHERE T1.name = 'Spanish Grand Prix' AND T1.year = 2009 AND T2.fastestLapSpeed IS NOT NULL ORDER BY T2.fastestLapSpeed DESC LIMIT 1
-- candidate
SELECT MAX(CAST(results.fastestLapSpeed AS REAL)) AS max_fastest_lap_speed
FROM results
JOIN races ON results.raceId = races.raceId
WHERE races.year = 2009 AND races.name = 'Spanish Grand Prix';
```
comparator: result sets differ

### `937` · formula_1 · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What's the finish time for the driver who ranked second in 2008's AustChineseralian Grand Prix?

```sql
-- gold
SELECT T1.time FROM results AS T1 INNER JOIN races AS T2 on T1.raceId = T2.raceId WHERE T1.rank = 2 AND T2.name = 'Chinese Grand Prix' AND T2.year = 2008
-- candidate
SELECT results.time FROM results JOIN races ON results.raceId = races.raceId WHERE races.name = 'Chinese Grand Prix' AND races.year = 2008 AND results.position = 2
```
comparator: result sets differ

### `944` · formula_1 · challenging · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, spurious_join, aggregate_mismatch, limit_mismatch · **BIRD-ok (scorer artifact)**

**Q:** How much faster in percentage is the champion than the driver who finished the race last in the 2008 Australian Grand Prix?

```sql
-- gold
WITH time_in_seconds AS ( SELECT T1.positionOrder, CASE WHEN T1.positionOrder = 1 THEN (CAST(SUBSTR(T1.time, 1, 1) AS REAL) * 3600) + (CAST(SUBSTR(T1.time, 3, 2) AS REAL) * 60) + CAST(SUBSTR(T1.time, 6) AS REAL) ELSE CAST(SUBSTR(T1.time, 2) AS REAL) END AS time_seconds FROM results AS T1 INNER JOIN races AS T2 ON T1.raceId = T2.raceId WHERE T2.name = 'Australian Grand Prix' AND T1.time IS NOT NULL AND T2.year = 2008 ), champion_time AS ( SELECT time_seconds FROM time_in_seconds WHERE positionOrder = 1), last_driver_incremental AS ( SELECT time_seconds FROM time_in_seconds WHERE positionOrder = (SELECT MAX(positionOrder) FROM time_in_seconds) ) SELECT (CAST((SELECT time_seconds FROM last_driver_incremental) AS REAL) * 100) / (SELECT time_seconds + (SELECT time_seconds FROM last_driver_incremental) FROM champion_time)
-- candidate
WITH race_info AS (
  SELECT raceId 
  FROM races 
  WHERE year = 2008 AND name = 'Australian Grand Prix'
),
race_results AS (
  SELECT 
    r.driverId,
    r.positionOrder,
    r.time,
    r.milliseconds
  FROM results r
  JOIN race_info ri ON r.raceId = ri.raceId
  WHERE r.positionText NOT IN ('D', 'R', 'N', 'W', 'F', 'd', 'q') AND r.milliseconds IS NOT NULL
),
champion AS (
  SELECT milliseconds AS champ_ms
  FROM race_results
  ORDER BY positionOrder ASC
  LIMIT 1
),
last_driver AS (
  SELECT milliseconds AS last_ms
  FROM race_results
  ORDER BY positionOrder DESC
  LIMIT 1
)
SELECT 
  ((CAST(last_ms AS REAL) - champ_ms) / last_ms) * 100 AS percentage_faster
FROM champion, last_driver;
```
comparator: —

### `948` · formula_1 · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** What are the maximum points of British constructors?

```sql
-- gold
SELECT MAX(T1.points) FROM constructorStandings AS T1 INNER JOIN constructors AS T2 on T1.constructorId = T2.constructorId WHERE T2.nationality = 'British'
-- candidate
SELECT MAX(t1.points) FROM constructorResults AS t1 JOIN constructors AS t2 ON t1.constructorId = t2.constructorId WHERE t2.nationality = 'British';
```
comparator: result sets differ

### `950` · formula_1 · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** Please list the constructor names with 0 points at race 291.

```sql
-- gold
SELECT T2.name FROM constructorStandings AS T1 INNER JOIN constructors AS T2 on T1.constructorId = T2.constructorId WHERE T1.points = 0 AND T1.raceId = 291
-- candidate
SELECT c.name FROM constructors AS c JOIN constructorResults AS cr ON c.constructorId = cr.constructorId WHERE cr.raceId = 291 AND cr.points = 0;
```
comparator: result sets differ

### `951` · formula_1 · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, aggregate_mismatch, distinct_mismatch

**Q:** How many Japanese constructors have 0 points in 2 races?

```sql
-- gold
SELECT COUNT(T1.raceId) FROM constructorStandings AS T1 INNER JOIN constructors AS T2 on T1.constructorId = T2.constructorId WHERE T1.points = 0 AND T2.nationality = 'Japanese' GROUP BY T1.constructorId HAVING COUNT(raceId) = 2
-- candidate
SELECT COUNT(*)
FROM (
  SELECT c.constructorId
  FROM constructors c
  JOIN constructorResults cr ON c.constructorId = cr.constructorId
  WHERE c.nationality = 'Japanese'
  GROUP BY c.constructorId
  HAVING COUNT(DISTINCT cr.raceId) = 2 AND SUM(cr.points) = 0
) AS temp;
```
comparator: result sets differ

### `955` · formula_1 · challenging · _wrong_answer_ · tags: table_mismatch, missing_table

**Q:** What is the average time in seconds of champion for each year, before year 1975?

```sql
-- gold
WITH time_in_seconds AS ( SELECT T2.year, T2.raceId, T1.positionOrder, CASE WHEN T1.positionOrder = 1 THEN (CAST(SUBSTR(T1.time, 1, 1) AS REAL) * 3600) + (CAST(SUBSTR(T1.time, 3, 2) AS REAL) * 60) + CAST(SUBSTR(T1.time, 6,2) AS REAL )   + CAST(SUBSTR(T1.time, 9) AS REAL)/1000 ELSE 0 END AS time_seconds FROM results AS T1 INNER JOIN races AS T2 ON T1.raceId = T2.raceId WHERE T1.time IS NOT NULL ), champion_time AS ( SELECT year, raceId, time_seconds FROM time_in_seconds WHERE positionOrder = 1 ) SELECT year, AVG(time_seconds) FROM champion_time WHERE year < 1975 GROUP BY year HAVING AVG(time_seconds) IS NOT NULL
-- candidate
SELECT t1.year, AVG(t1.total_seconds) AS average_time
FROM (
  SELECT 
    races.year,
    results.time,
    (
      CAST(SUBSTR(results.time, 1, INSTR(results.time, ':') - 1) AS INTEGER) * 3600 +
      CAST(SUBSTR(results.time, INSTR(results.time, ':') + 1, 2) AS INTEGER) * 60 +
      CAST(SUBSTR(results.time, INSTR(results.time, ':') + 4) AS REAL)
    ) AS total_seconds
  FROM results
  JOIN races ON results.raceId = races.raceId
  WHERE races.year < 1975
    AND results.position = 1
    AND results.time LIKE '%:%:%'
) AS t1
GROUP BY t1.year;
```
comparator: result sets differ

### `959` · formula_1 · simple · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** What is the fastest lap number of the champion in 2009?

```sql
-- gold
SELECT T1.fastestLap FROM results AS T1 INNER JOIN races AS T2 on T1.raceId = T2.raceId WHERE T2.year = 2009 AND T1.time LIKE '_:%:__.___'
-- candidate
had?"
    Yes, that corresponds to `ORDER BY T1.fastestLapTime ASC LIMIT 1`.

    Wait, what if "the champion in 2009" means Jenson Button, and the question asks for the fastest lap number in *a specific race*, but didn't mention it?
    Is there a race in 2009 where Jenson Button had the fastest lap of the race?
    Actually, let's write a query that yields the fastest lap number of the 2009 champion's fastest lap.
    Wait, let's double check if there are other interpretations.
    "Only the time of the champion shows in the format of 'hour: minutes: seconds.millionsecond'"
```
comparator: —

### `962` · formula_1 · challenging · _wrong_answer_ · tags: aggregate_mismatch, distinct_mismatch

**Q:** From 2000 to 2005, what percentage of drivers who were born before 1985 and the lap numbers were over 50?

```sql
-- gold
SELECT CAST(SUM(IIF(STRFTIME('%Y', T3.dob) < '1985' AND T1.laps > 50, 1, 0)) AS REAL) * 100 / COUNT(*) FROM results AS T1 INNER JOIN races AS T2 on T1.raceId = T2.raceId INNER JOIN drivers AS T3 on T1.driverId = T3.driverId WHERE T2.year BETWEEN 2000 AND 2005
-- candidate
SELECT (COUNT(DISTINCT CASE WHEN CAST(strftime('%Y', d.dob) AS INTEGER) < 1985 AND res.laps > 50 THEN d.driverId END) * 100.0) / COUNT(DISTINCT d.driverId) FROM drivers d JOIN results res ON d.driverId = res.driverId JOIN races rac ON res.raceId = rac.raceId WHERE rac.year BETWEEN 2000 AND 2005
```
comparator: result sets differ

### `963` · formula_1 · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many French drivers who obtain the laptime less than 02:00.00?

```sql
-- gold
SELECT COUNT(T1.driverId) FROM drivers AS T1 INNER JOIN lapTimes AS T2 on T1.driverId = T2.driverId WHERE T1.nationality = 'French' AND (CAST(SUBSTR(T2.time, 1, 2) AS INTEGER) * 60 + CAST(SUBSTR(T2.time, 4, 2) AS INTEGER) + CAST(SUBSTR(T2.time, 7, 2) AS REAL) / 1000) < 120
-- candidate
SELECT COUNT(DISTINCT drivers.driverId)
FROM drivers
JOIN lapTimes ON drivers.driverId = lapTimes.driverId
WHERE drivers.nationality = 'French'
  AND lapTimes.milliseconds < 120000
```
comparator: result sets differ

### `964` · formula_1 · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** List out the code for drivers who have nationality in American.

```sql
-- gold
SELECT code FROM drivers WHERE Nationality = 'American'
-- candidate
SELECT code 
FROM drivers 
WHERE nationality = 'American' AND code IS NOT NULL;
```
comparator: result sets differ

### `967` · formula_1 · simple · _wrong_answer_ · tags: projection_count_mismatch

**Q:** State code numbers of top 3 yougest drivers. How many Netherlandic drivers among them?

```sql
-- gold
SELECT COUNT(*) FROM ( SELECT T1.nationality FROM drivers AS T1 ORDER BY JULIANDAY(T1.dob) DESC LIMIT 3) AS T3 WHERE T3.nationality = 'Dutch'
-- candidate
SELECT t.code, (SELECT COUNT(*) FROM drivers WHERE dob IN (SELECT dob FROM drivers ORDER BY dob DESC LIMIT 3) AND nationality = 'Dutch') AS count_dutch
FROM (
  SELECT code
  FROM drivers
  ORDER BY dob DESC
  LIMIT 3
) AS t
```
comparator: result sets differ

### `972` · formula_1 · moderate · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Which drivers who were born in 1971 and has the fastest lap time on the race? Give id and code of these drivers.

```sql
-- gold
SELECT T2.driverId, T2.code FROM results AS T1 INNER JOIN drivers AS T2 on T1.driverId = T2.driverId WHERE STRFTIME('%Y', T2.dob) = '1971' AND T1.fastestLapTime IS NOT NULL
-- candidate
SELECT DISTINCT d.driverId, d.code
FROM drivers d
JOIN results r ON d.driverId = r.driverId
WHERE strftime('%Y', d.dob) = '1971'
  AND r.fastestLapTime IS NOT NULL;
```
comparator: result sets differ

### `978` · formula_1 · simple · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, aggregate_mismatch, group_by_mismatch, distinct_mismatch, projection_count_mismatch

**Q:** How many times the circuits were held in Austria? Please give their location and coordinates.

```sql
-- gold
SELECT DISTINCT location, lat, lng FROM circuits WHERE country = 'Austria'
-- candidate
SELECT 
  c.name, 
  c.location, 
  c.lat, 
  c.lng, 
  COUNT(r.raceId) AS race_count
FROM circuits c
LEFT JOIN races r ON c.circuitId = r.circuitId
WHERE c.country = 'Austria'
GROUP BY c.circuitId, c.name, c.location, c.lat, c.lng;
```
comparator: result sets differ

### `988` · formula_1 · challenging · _wrong_answer_ · tags: aggregate_mismatch, projection_count_mismatch

**Q:** List down top 3 German drivers who has the shortest average pit stop duration and were born between 1980-1985.

```sql
-- gold
SELECT T2.forename, T2.surname FROM pitStops AS T1 INNER JOIN drivers AS T2 on T1.driverId = T2.driverId WHERE T2.nationality = 'German' AND STRFTIME('%Y', T2.dob) BETWEEN '1980' AND '1985' GROUP BY T2.forename, T2.surname ORDER BY AVG(T1.duration) LIMIT 3
-- candidate
SELECT 
  d.forename, 
  d.surname, 
  (SUM(p.duration) / COUNT(p.duration)) AS avg_pit_stop_duration
FROM drivers d
JOIN pitStops p ON d.driverId = p.driverId
WHERE d.nationality = 'German'
  AND strftime('%Y', d.dob) BETWEEN '1980' AND '1985'
GROUP BY d.driverId, d.forename, d.surname
ORDER BY avg_pit_stop_duration ASC
LIMIT 3;
```
comparator: result sets differ

### `989` · formula_1 · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, projection_count_mismatch

**Q:** Who is the champion of the Canadian Grand Prix in 2008? Indicate his finish time.

```sql
-- gold
SELECT T1.time FROM results AS T1 INNER JOIN races AS T2 ON T1.raceId = T2.raceId WHERE T2.name = 'Canadian Grand Prix' AND T2.year = 2008 AND T1.time LIKE '_:%:__.___'
-- candidate
SELECT 
  d.forename, 
  d.surname, 
  r.time
FROM results r
JOIN races ra ON r.raceId = ra.raceId
JOIN drivers d ON r.driverId = d.driverId
WHERE ra.name = 'Canadian Grand Prix' 
  AND ra.year = 2008 
  AND r.position = 1;
```
comparator: result sets differ

### `717` · superhero · simple · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table

**Q:** Please list all the superpowers of 3-D Man.

```sql
-- gold
SELECT T3.power_name FROM superhero AS T1 INNER JOIN hero_power AS T2 ON T1.id = T2.hero_id INNER JOIN superpower AS T3 ON T2.power_id = T3.id WHERE T1.superhero_name = '3-D Man'
-- candidate
SELECT attribute_name
FROM attribute
JOIN hero_attribute ON attribute.id = hero_attribute.attribute_id
JOIN superhero ON hero_attribute.hero_id = superhero.id
WHERE superhero_name = '3-D Man'
```
comparator: result sets differ

### `1001` · formula_1 · challenging · _wrong_answer_ · tags: join_mismatch, projection_count_mismatch

**Q:** What is full name of the racer who ranked 1st in the 3rd qualifying race held in the Marina Bay Street Circuit in 2008?

```sql
-- gold
SELECT T2.forename, T2.surname FROM qualifying AS T1 INNER JOIN drivers AS T2 on T1.driverId = T2.driverId INNER JOIN races AS T3 ON T1.raceid = T3.raceid WHERE q3 IS NOT NULL AND T3.year = 2008 AND T3.circuitId IN ( SELECT circuitId FROM circuits WHERE name = 'Marina Bay Street Circuit' ) ORDER BY CAST(SUBSTR(q3, 1, INSTR(q3, ':') - 1) AS INTEGER) * 60 + CAST(SUBSTR(q3, INSTR(q3, ':') + 1, INSTR(q3, '.') - INSTR(q3, ':') - 1) AS REAL) + CAST(SUBSTR(q3, INSTR(q3, '.') + 1) AS REAL) / 1000 ASC LIMIT 1
-- candidate
SELECT (drivers.forename || ' ' || drivers.surname) AS full_name
FROM qualifying
JOIN drivers ON qualifying.driverId = drivers.driverId
JOIN races ON qualifying.raceId = races.raceId
JOIN circuits ON races.circuitId = circuits.circuitId
WHERE races.year = 2008
  AND circuits.name = 'Marina Bay Street Circuit'
  AND qualifying.q3 IS NOT NULL
  AND qualifying.q3 != ''
ORDER BY qualifying.q3 ASC
LIMIT 1;
```
comparator: result sets differ

### `1002` · formula_1 · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, spurious_join, aggregate_mismatch, where_mismatch, limit_mismatch, projection_count_mismatch

**Q:** As of the present, what is the full name of the youngest racer? Indicate her nationality and the name of the race to which he/she first joined.

```sql
-- gold
SELECT T1.forename, T1.surname, T1.nationality, T3.name FROM drivers AS T1 INNER JOIN driverStandings AS T2 on T1.driverId = T2.driverId INNER JOIN races AS T3 on T2.raceId = T3.raceId ORDER BY JULIANDAY(T1.dob) DESC LIMIT 1
-- candidate
WITH YoungestDriver AS (
  SELECT driverId, forename || ' ' ||  surname AS full_name, nationality
  FROM drivers
  WHERE dob = (SELECT MAX(dob) FROM drivers)
),
FirstRace AS (
  SELECT yd.full_name, yd.nationality, r.name AS race_name,
         ROW_NUMBER() OVER (PARTITION BY yd.driverId ORDER BY r.date ASC, r.time ASC) as rn
  FROM YoungestDriver yd
  JOIN lapTimes lt ON yd.driverId = lt.driverId
  JOIN races r ON lt.raceId = r.raceId
)
SELECT full_name, nationality, race_name
FROM FirstRace
WHERE rn = 1;
```
comparator: result sets differ

### `1011` · formula_1 · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, projection_count_mismatch

**Q:** Which top 20 driver created the shortest lap time ever record in a Formula_1 race? Please give them full names.

```sql
-- gold
WITH lap_times_in_seconds AS (SELECT driverId, (CASE WHEN SUBSTR(time, 1, INSTR(time, ':') - 1) <> '' THEN CAST(SUBSTR(time, 1, INSTR(time, ':') - 1) AS REAL) * 60 ELSE 0 END + CASE WHEN SUBSTR(time, INSTR(time, ':') + 1, INSTR(time, '.') - INSTR(time, ':') - 1) <> '' THEN CAST(SUBSTR(time, INSTR(time, ':') + 1, INSTR(time, '.') - INSTR(time, ':') - 1) AS REAL) ELSE 0 END + CASE WHEN SUBSTR(time, INSTR(time, '.') + 1) <> '' THEN CAST(SUBSTR(time, INSTR(time, '.') + 1) AS REAL) / 1000 ELSE 0 END) AS time_in_seconds FROM lapTimes) SELECT T2.forename, T2.surname, T1.driverId FROM (SELECT driverId, MIN(time_in_seconds) AS min_time_in_seconds FROM lap_times_in_seconds GROUP BY driverId) AS T1 INNER JOIN drivers AS T2 ON T1.driverId = T2.driverId ORDER BY T1.min_time_in_seconds ASC LIMIT 20
-- candidate
SELECT drivers.forename || ' ' || drivers.surname, MIN(lapTimes.time)
FROM lapTimes
JOIN drivers ON lapTimes.driverId = drivers.driverId
GROUP BY drivers.driverId
ORDER BY MIN(lapTimes.milliseconds) ASC
LIMIT 20;
```
comparator: result sets differ

### `1014` · formula_1 · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, aggregate_mismatch, limit_mismatch, projection_count_mismatch

**Q:** Please list the lap records for the circuits in Italy.

```sql
-- gold
WITH fastest_lap_times AS (SELECT T1.raceId, T1.FastestLapTime, (CAST(SUBSTR(T1.FastestLapTime, 1, INSTR(T1.FastestLapTime, ':') - 1) AS REAL) * 60) + (CAST(SUBSTR(T1.FastestLapTime, INSTR(T1.FastestLapTime, ':') + 1, INSTR(T1.FastestLapTime, '.') - INSTR(T1.FastestLapTime, ':') - 1) AS REAL)) + (CAST(SUBSTR(T1.FastestLapTime, INSTR(T1.FastestLapTime, '.') + 1) AS REAL) / 1000) as time_in_seconds FROM results AS T1 WHERE T1.FastestLapTime IS NOT NULL ) SELECT T1.FastestLapTime as lap_record FROM results AS T1 INNER JOIN races AS T2 on T1.raceId = T2.raceId INNER JOIN circuits AS T3 on T2.circuitId = T3.circuitId INNER JOIN (SELECT MIN(fastest_lap_times.time_in_seconds) as min_time_in_seconds FROM fastest_lap_times INNER JOIN races AS T2 on fastest_lap_times.raceId = T2.raceId INNER JOIN circuits AS T3 on T2.circuitId = T3.circuitId WHERE T3.country = 'Italy' ) AS T4 ON (CAST(SUBSTR(T1.FastestLapTime, 1, INSTR(T1.FastestLapTime, ':') - 1) AS REAL) * 60) + (CAST(SUBSTR(T1.FastestLapTime, INSTR(T1.FastestLapTime, ':') + 1, INSTR(T1.FastestLapTime, '.') - INSTR(T1.FastestLapTime, ':') - 1) AS REAL)) + (CAST(SUBSTR(T1.FastestLapTime, INSTR(T1.FastestLapTime, '.') + 1) AS REAL) / 1000) = T4.min_time_in_seconds LIMIT 1
-- candidate
WITH RankedLaps AS (
  SELECT 
    c.name AS circuit,
    d.forename || ' ' || d.surname AS driver,
    l.time AS lap_record,
    ROW_NUMBER() OVER (PARTITION BY c.circuitId ORDER BY l.milliseconds ASC) as rn
  FROM circuits c
  JOIN races r ON c.circuitId = r.circuitId
  JOIN lapTimes l ON r.raceId = l.raceId
  JOIN drivers d ON l.driverId = d.driverId
  WHERE c.country = 'Italy'
)
SELECT circuit, driver, lap_record
FROM RankedLaps
WHERE rn = 1
```
comparator: result sets differ

### `726` · superhero · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Rank heroes published by Marvel Comics by their height in descending order.

```sql
-- gold
SELECT superhero_name, height_cm, RANK() OVER (ORDER BY height_cm DESC) AS HeightRank FROM superhero INNER JOIN publisher ON superhero.publisher_id = publisher.id WHERE publisher.publisher_name = 'Marvel Comics'
-- candidate
SELECT s.superhero_name, s.height_cm
FROM superhero s
JOIN publisher p ON s.publisher_id = p.id
WHERE p.publisher_name = 'Marvel Comics'
ORDER BY s.height_cm DESC;
```
comparator: result sets differ

### `728` · superhero · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Rank superheroes from Marvel Comics by their eye color popularity, starting with the most common color.

```sql
-- gold
SELECT colour.colour AS EyeColor, COUNT(superhero.id) AS Count, RANK() OVER (ORDER BY COUNT(superhero.id) DESC) AS PopularityRank FROM superhero INNER JOIN colour ON superhero.eye_colour_id = colour.id INNER JOIN publisher ON superhero.publisher_id = publisher.id WHERE publisher.publisher_name = 'Marvel Comics' GROUP BY colour.colour
-- candidate
SELECT
  c.colour AS eye_colour,
  COUNT(s.id) AS superhero_count
FROM superhero s
INNER JOIN publisher p ON s.publisher_id = p.id
INNER JOIN colour c ON s.eye_colour_id = c.id
WHERE p.publisher_name = 'Marvel Comics'
GROUP BY c.colour
ORDER BY COUNT(s.id) DESC;
```
comparator: result sets differ

### `743` · superhero · challenging · _execution_error_final_ · tags: table_mismatch, missing_table, join_mismatch, where_mismatch

**Q:** What is the percentage of superheroes who act in their own self-interest or make decisions based on their own moral code? Indicate how many of the said superheroes were published by Marvel Comics.

```sql
-- gold
SELECT (CAST(COUNT(*) AS REAL) * 100 / (SELECT COUNT(*) FROM superhero)), CAST(SUM(CASE WHEN T2.publisher_name = 'Marvel Comics' THEN 1 ELSE 0 END) AS REAL) FROM superhero AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.id INNER JOIN alignment AS T3 ON T3.id = T1.alignment_id WHERE T3.alignment = 'Bad'
-- candidate
SELECT 
  (CAST(SUM(CASE WHEN alignment = 'Bad' THEN 1 ELSE 0 END) AS REAL) / COUNT(id)) * 100 AS percentage,
  SUM(CASE WHEN alignment = 'Bad' AND publisher_name = 'Marvel Comics' THEN 1 ELSE 0 END) AS marvel_count
FROM superhero
LEFT JOIN publisher ON superhero.publisher_id = publisher.id
```
comparator: —

### `751` · superhero · moderate · _execution_error_final_ · tags: table_mismatch, missing_table, join_mismatch, group_by_mismatch

**Q:** List down at least five superpowers of male superheroes.

```sql
-- gold
SELECT T3.power_name FROM superhero AS T1 INNER JOIN hero_power AS T2 ON T1.id = T2.hero_id INNER JOIN superpower AS T3 ON T3.id = T2.power_id INNER JOIN gender AS T4 ON T4.id = T1.gender_id WHERE T4.gender = 'Male' LIMIT 5
-- candidate
SELECT hero_power.power_name
FROM superhero
JOIN gender ON superhero.gender_id = gender.id
JOIN hero_power ON superhero.id = hero_power.hero_id
WHERE gender.gender = 'Male'
GROUP BY hero_power.power_name
LIMIT 5;
```
comparator: —

### `758` · superhero · moderate · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Provide the hair colour of the human superhero who is 185 cm tall.

```sql
-- gold
SELECT DISTINCT T3.colour FROM superhero AS T1 INNER JOIN race AS T2 ON T1.race_id = T2.id INNER JOIN colour AS T3 ON T1.hair_colour_id = T3.id WHERE T1.height_cm = 185 AND T2.race = 'Human'
-- candidate
SELECT t4.colour
FROM superhero AS t1
INNER JOIN race AS t2 ON t1.race_id = t2.id
INNER JOIN colour AS t4 ON t1.hair_colour_id = t4.id
WHERE t2.race LIKE 'human' AND t1.height_cm = 185
```
comparator: result sets differ

### `772` · superhero · challenging · _guardrail_rejected_ · tags: table_mismatch, extra_table, join_mismatch

**Q:** List the eyes, hair and skin colour of all female superheroes published by Dark Horse Comics.

```sql
-- gold
SELECT T1.eye_colour_id, T1.hair_colour_id, T1.skin_colour_id FROM superhero AS T1 INNER JOIN publisher AS T2 ON T2.id = T1.publisher_id INNER JOIN gender AS T3 ON T3.id = T1.gender_id WHERE T2.publisher_name = 'Dark Horse Comics' AND T3.gender = 'Female'
-- candidate
SELECT 
  t3.colour AS eye_colour, 
  t4.colour AS hair_colour, 
  t5.colour AS skin_colour
FROM superhero AS t1
JOIN gender AS t2 ON t1.gender_id = t2.id
LEFT JOIN colour AS t3 ON t1.eye_colour_id = t3.id
LEFT JOIN colour AS t4 ON t1.hair_colour_id = t4.id
LEFT JOIN colour AS t5 ON t1.skin_colour_id = t5.id
JOIN publisher AS t6 ON t1.publisher_id = t6.id
WHERE t2.gender = 'Female' 
  AND t6.publisher_name = 'Dark Horse Comics'
```
comparator: —

### `775` · superhero · challenging · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, spurious_join, aggregate_mismatch

**Q:** What is the percentage of blue female superheroes among all female superheroes?

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T3.colour = 'Blue' THEN T1.id ELSE NULL END) AS REAL) * 100 / COUNT(T1.id) FROM superhero AS T1 INNER JOIN gender AS T2 ON T1.gender_id = T2.id INNER JOIN colour AS T3 ON T1.skin_colour_id = T3.id WHERE T2.gender = 'Female'
-- candidate
SELECT (CAST(SUM(CASE WHEN c.colour = 'Blue' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) * 100 AS percentage FROM hero AS h JOIN gender AS g ON h.gender_id = g.id JOIN colour AS c ON h.skin_colour_id = c.id WHERE g.gender = 'Female'
```
comparator: —

### `788` · superhero · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** How many percent of female heroes were published by Marvel Comics?

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T3.gender = 'Female' AND T2.publisher_name = 'Marvel Comics' THEN 1 ELSE NULL END) AS REAL) / COUNT(CASE WHEN T2.publisher_name = 'Marvel Comics' THEN 1 ELSE NULL END) * 100 FROM superhero AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.id INNER JOIN gender AS T3 ON T1.gender_id = T3.id
-- candidate
SELECT (SUM(CASE WHEN g.gender = 'Female' AND p.publisher_name = 'Marvel Comics' THEN 1 ELSE 0 END) * 100.0) / SUM(CASE WHEN g.gender = 'Female' THEN 1 ELSE 0 END) AS percent
FROM superhero s
JOIN gender g ON s.gender_id = g.id
JOIN publisher p ON s.publisher_id = p.id
```
comparator: result sets differ

### `791` · superhero · simple · _wrong_answer_ · tags: aggregate_mismatch

**Q:** Calculate the average height for all superhero.

```sql
-- gold
SELECT CAST(SUM(height_cm) AS REAL) / COUNT(id) FROM superhero
-- candidate
SELECT AVG(height_cm) AS average_height FROM superhero;
```
comparator: result sets differ

### `798` · superhero · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** What is the publisher for Hawkman, Karate Kid and Speedy?

```sql
-- gold
SELECT T2.publisher_name FROM superhero AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.id WHERE T1.superhero_name IN ('Hawkman', 'Karate Kid', 'Speedy')
-- candidate
SELECT 
  s.superhero_name, 
  p.publisher_name 
FROM 
  superhero s
JOIN 
  publisher p ON s.publisher_id = p.id
WHERE 
  s.superhero_name IN ('Hawkman', 'Karate Kid', 'Speedy')
```
comparator: result sets differ

### `800` · superhero · moderate · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, aggregate_mismatch

**Q:** Calculate the percentage of superheroes with blue eyes.

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T2.colour = 'Blue' THEN 1 ELSE NULL END) AS REAL) * 100 / COUNT(T1.id) FROM superhero AS T1 INNER JOIN colour AS T2 ON T1.eye_colour_id = T2.id
-- candidate
SELECT (CAST(SUM(CASE WHEN eye_colour_id = 7 THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) * 100.0 AS percentage FROM superhero_profile;
```
comparator: —

### `801` · superhero · moderate · _guardrail_rejected_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, aggregate_mismatch

**Q:** Find the ratio between male superheroes and female superheroes.

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T2.gender = 'Male' THEN T1.id ELSE NULL END) AS REAL) / COUNT(CASE WHEN T2.gender = 'Female' THEN T1.id ELSE NULL END) FROM superhero AS T1 INNER JOIN gender AS T2 ON T1.gender_id = T2.id
-- candidate
SELECT CAST(SUM(CASE WHEN gender_id = 1 THEN 1 ELSE 0 END) AS REAL) / SUM(CASE WHEN gender_id = 2 THEN 1 ELSE 0 END) FROM hero_battles;
```
comparator: —

### `533` · codebase_community · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** How many users last accessed the website after 2014/9/1?

```sql
-- gold
SELECT COUNT(Id) FROM users WHERE date(LastAccessDate) > '2014-09-01'
-- candidate
SELECT COUNT(Id) AS user_count
FROM users
WHERE LastAccessDate > '2014-09-01';
```
comparator: result sets differ

### `557` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Among the posts with a score of over 5, what is the percentage of them being owned by an elder user?

```sql
-- gold
SELECT CAST(SUM(IIF(T2.Age > 65, 1, 0)) AS REAL) * 100 / COUNT(T1.Id) FROM posts AS T1 INNER JOIN users AS T2 ON T1.OwnerUserId = T2.Id WHERE T1.Score > 5
-- candidate
SELECT (SUM(CASE WHEN u.Age > 65 THEN 1.0 ELSE 0.0 END) / COUNT(*)) * 100 FROM posts AS p LEFT JOIN users AS u ON p.OwnerUserId = u.Id WHERE p.Score > 5
```
comparator: result sets differ

### `563` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** User No.3025 gave a comment at 20:29:39 on 2014/4/23 to a post, how many favorite counts did that post get?

```sql
-- gold
SELECT T1.FavoriteCount FROM posts AS T1 INNER JOIN comments AS T2 ON T1.Id = T2.PostId WHERE T2.CreationDate = '2014-04-23 20:29:39.0' AND T2.UserId = 3025
-- candidate
SELECT posts.FavoriteCount
FROM posts
JOIN comments ON posts.Id = comments.PostId
WHERE comments.UserId = 3025
  AND comments.CreationDate = '2014-04-23 20:29:39';
```
comparator: result sets differ

### `565` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** User No.23853 gave a comment to a post at 9:08:18 on 2013/7/12, was that post well-finished?

```sql
-- gold
SELECT IIF(T2.ClosedDate IS NULL, 'NOT well-finished', 'well-finished') AS resylt FROM comments AS T1 INNER JOIN posts AS T2 ON T1.PostId = T2.Id WHERE T1.UserId = 23853 AND T1.CreationDate = '2013-07-12 09:08:18.0'
-- candidate
SELECT 
  CASE 
    WHEN p.ClosedDate IS NULL THEN 'Yes' 
    ELSE 'No' 
  END AS 'Well-Finished'
FROM comments c
JOIN posts p ON c.PostId = p.Id
WHERE c.UserId = 23853 
  AND c.CreationDate = '2013-07-12 09:08:18.0';
```
comparator: result sets differ

### `581` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Who is the owner of the post titled 'Open source tools for visualizing multi-dimensional data?'

```sql
-- gold
SELECT T2.DisplayName FROM posts AS T1 INNER JOIN users AS T2 ON T1.OwnerUserId = T2.Id WHERE T1.Title = 'Open source tools for visualizing multi-dimensional data?'
-- candidate
SELECT u.DisplayName
FROM posts p
JOIN users u ON p.OwnerUserId = u.Id
WHERE p.Title = 'Open source tools for visualizing multi-dimensional data';
```
comparator: result sets differ

### `584` · codebase_community · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, distinct_mismatch

**Q:** Write all the comments left by users who edited the post titled 'Why square the difference instead of taking the absolute value in standard deviation?'

```sql
-- gold
SELECT T2.Comment FROM posts AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.PostId WHERE T1.Title = 'Why square the difference instead of taking the absolute value in standard deviation?'
-- candidate
SELECT c.Text
FROM comments c
WHERE c.UserId IN (
    SELECT DISTINCT ph.UserId
    FROM postHistory ph
    JOIN posts p ON ph.PostId = p.Id
    WHERE p.Title = 'Why square the difference instead of taking the absolute value in standard deviation?'
      AND ph.PostHistoryTypeId IN (4, 5, 6)
)
```
comparator: result sets differ

### `586` · codebase_community · challenging · _wrong_answer_ · tags: projection_count_mismatch

**Q:** Which user added a bounty amount of 50 to the post title mentioning variance?

```sql
-- gold
SELECT T3.DisplayName, T1.Title FROM posts AS T1 INNER JOIN votes AS T2 ON T1.Id = T2.PostId INNER JOIN users AS T3 ON T3.Id = T2.UserId WHERE T2.BountyAmount = 50 AND T1.Title LIKE '%variance%'
-- candidate
SELECT u.DisplayName FROM users u JOIN votes v ON u.Id = v.UserId JOIN posts p ON v.PostId = p.Id WHERE v.BountyAmount = 50 AND p.Title LIKE '%variance%'
```
comparator: result sets differ

### `587` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Calculate the average view count of each post tagged as 'humor' and list the title and the comment of each post.

```sql
-- gold
SELECT AVG(T2.ViewCount), T2.Title, T1.Text FROM comments AS T1 INNER JOIN posts AS T2 ON T2.Id = T1.PostId  WHERE T2.Tags = '<humor>' GROUP BY T2.Title, T1.Text 
-- candidate
SELECT AVG(posts.ViewCount), posts.Title, comments.Text
FROM posts
JOIN comments ON posts.Id = comments.PostId
WHERE posts.Tags LIKE '%<humor>%'
GROUP BY posts.Id, posts.Title, comments.Text
```
comparator: result sets differ

### `595` · codebase_community · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, projection_count_mismatch

**Q:** Which user have only one post history per post and having at least 1000 views?

```sql
-- gold
SELECT T2.UserId FROM users AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.UserId INNER JOIN posts AS T3 ON T2.PostId = T3.Id WHERE T3.ViewCount >= 1000 GROUP BY T2.UserId HAVING COUNT(DISTINCT T2.PostHistoryTypeId) = 1
-- candidate
SELECT
  u.Id,
  u.DisplayName
FROM users AS u
INNER JOIN postHistory AS ph
  ON u.Id = ph.UserId
WHERE u.Views >= 1000
GROUP BY u.Id
HAVING COUNT(ph.Id) = COUNT(DISTINCT ph.PostId);
```
comparator: result sets differ

### `604` · codebase_community · moderate · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch, where_mismatch

**Q:** What is the average of the up votes and the average user age for users creating more than 10 posts?

```sql
-- gold
SELECT AVG(T1.UpVotes), AVG(T1.Age) FROM users AS T1 INNER JOIN ( SELECT OwnerUserId, COUNT(*) AS post_count FROM posts GROUP BY OwnerUserId HAVING post_count > 10) AS T2 ON T1.Id = T2.OwnerUserId
-- candidate
SELECT 
  CAST(SUM(u.UpVotes) AS REAL) / COUNT(u.Id) AS [Average Up Votes],
  CAST(SUM(u.Age) AS REAL) / COUNT(u.Id) AS [Average Age]
FROM users u
WHERE u.Id IN (
  SELECT p.OwnerUserId
  FROM posts p
  WHERE p.OwnerUserId IS NOT NULL
  GROUP BY p.OwnerUserId
  HAVING COUNT(p.Id) > 10
);
```
comparator: result sets differ

### `634` · codebase_community · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, aggregate_mismatch, group_by_mismatch

**Q:** Among posts by Harvey Motulsky and Noah Snyder, which one has higher popularity?

```sql
-- gold
SELECT T1.DisplayName FROM users AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.UserId INNER JOIN posts AS T3 ON T2.PostId = T3.Id WHERE T1.DisplayName = 'Harvey Motulsky' OR T1.DisplayName = 'Noah Snyder' GROUP BY T1.DisplayName ORDER BY SUM(T3.ViewCount) DESC LIMIT 1
-- candidate
SELECT p.Title
FROM posts AS p
JOIN users AS u ON p.OwnerUserId = u.Id
WHERE u.DisplayName IN ('Harvey Motulsky', 'Noah Snyder')
ORDER BY p.ViewCount DESC
LIMIT 1;
```
comparator: result sets differ

### `637` · codebase_community · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, distinct_mismatch

**Q:** State all the tags used by Mark Meckes in his posts that doesn't have comments.

```sql
-- gold
SELECT T3.Tags FROM users AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.UserId INNER JOIN posts AS T3 ON T3.Id = T2.PostId WHERE T1.DisplayName = 'Mark Meckes' AND T3.CommentCount = 0
-- candidate
SELECT DISTINCT tags.TagName
FROM posts
JOIN users ON posts.OwnerUserId = users.Id
JOIN tags ON posts.Tags LIKE '%<' || tags.TagName || '>%'
WHERE users.DisplayName = 'Mark Meckes'
  AND posts.CommentCount = 0;
```
comparator: result sets differ

### `639` · codebase_community · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch

**Q:** Based on posts posted by Community, calculate the percentage of posts that use the R language.

```sql
-- gold
SELECT CAST(SUM(IIF(T3.TagName = 'r', 1, 0)) AS REAL) * 100 / COUNT(T1.Id) FROM users AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.UserId INNER JOIN tags AS T3 ON T3.ExcerptPostId = T2.PostId WHERE T1.DisplayName = 'Community'
-- candidate
SELECT 
  (CAST(SUM(CASE WHEN t.Tags LIKE '%<r>%' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)) * 100.0 AS percentage
FROM posts t
JOIN users u ON t.OwnerUserId = u.Id
WHERE u.DisplayName = 'Community';
```
comparator: result sets differ

### `640` · codebase_community · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, where_mismatch

**Q:** Calculate the difference in view count from post posted by Mornington and view count from posts posted by Amos.

```sql
-- gold
SELECT SUM(IIF(T1.DisplayName = 'Mornington', T3.ViewCount, 0)) - SUM(IIF(T1.DisplayName = 'Amos', T3.ViewCount, 0)) AS diff FROM users AS T1 INNER JOIN postHistory AS T2 ON T1.Id = T2.UserId INNER JOIN posts AS T3 ON T3.Id = T2.PostId
-- candidate
SELECT 
  (SELECT SUM(p.ViewCount) FROM posts p JOIN users u ON p.OwnerUserId = u.Id WHERE u.DisplayName = 'Mornington')
  -
  (SELECT SUM(p.ViewCount) FROM posts p JOIN users u ON p.OwnerUserId = u.Id WHERE u.DisplayName = 'Amos') 
  AS Difference;
```
comparator: result sets differ

### `672` · codebase_community · moderate · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch

**Q:** Among the users located in United Kingdom, how many users whose post have a total favorite amount of 4 or more?

```sql
-- gold
SELECT COUNT(T1.Id) FROM users AS T1 INNER JOIN posts AS T2 ON T1.Id = T2.OwnerUserId WHERE T1.Location = 'United Kingdom' AND T2.FavoriteCount >= 4
-- candidate
SELECT COUNT(*) FROM (SELECT u.Id FROM users u JOIN posts p ON u.Id = p.OwnerUserId WHERE u.Location = 'United Kingdom' GROUP BY u.Id HAVING SUM(p.FavoriteCount) >= 4)
```
comparator: result sets differ

### `682` · codebase_community · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Which is the most valuable post in 2010? Please give its id and the owner's display name.

```sql
-- gold
SELECT T2.OwnerUserId, T1.DisplayName FROM users AS T1 INNER JOIN posts AS T2 ON T1.Id = T2.OwnerUserId WHERE STRFTIME('%Y', T1.CreationDate) = '2010' ORDER BY T2.FavoriteCount DESC LIMIT 1
-- candidate
SELECT p.Id, u.DisplayName
FROM posts p
LEFT JOIN users u ON p.OwnerUserId = u.Id
WHERE strftime('%Y', p.CreaionDate) = '2010'
ORDER BY p.FavoriteCount DESC
LIMIT 1
```
comparator: result sets differ

### `683` · codebase_community · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** What is the percentage of posts whose owners had a reputation of over 1000 in 2011?

```sql
-- gold
SELECT CAST(SUM(IIF(STRFTIME('%Y', T2.CreaionDate) = '2011' AND T1.Reputation > 1000, 1, 0)) AS REAL) * 100 / COUNT(T1.Id) FROM users AS T1 INNER JOIN posts AS T2 ON T1.Id = T2.OwnerUserId
-- candidate
SELECT 
  (CAST(COUNT(CASE WHEN strftime('%Y', p.CreaionDate) = '2011' AND u.Reputation > 1000 THEN 1 END) AS REAL) / 
   COUNT(p.Id)) * 100.0 AS percentage
FROM posts p
LEFT JOIN users u ON p.OwnerUserId = u.Id;
```
comparator: result sets differ

### `694` · codebase_community · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** Provide the text of the latest 10 comments to the post with the title 'Analysing wind data with R' and the display name of the user who left it.

```sql
-- gold
SELECT T3.Text, T1.DisplayName FROM users AS T1 INNER JOIN posts AS T2 ON T1.Id = T2.OwnerUserId INNER JOIN comments AS T3 ON T2.Id = T3.PostId WHERE T2.Title = 'Analysing wind data with R' ORDER BY T1.CreationDate DESC LIMIT 10
-- candidate
SELECT c.Text, c.UserDisplayName
FROM comments c
JOIN posts p ON c.PostId = p.Id
WHERE p.Title = 'Analysing wind data with R'
ORDER BY c.CreationDate DESC
LIMIT 10;
```
comparator: result sets differ

### `710` · codebase_community · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** In posts with 1 comment, how many of the comments have 0 score?

```sql
-- gold
SELECT COUNT(T1.id) FROM comments AS T1 INNER JOIN posts AS T2 ON T1.PostId = T2.Id WHERE T2.CommentCount = 1 AND T2.Score = 0
-- candidate
SELECT COUNT(*) AS comment_count
FROM comments AS c
JOIN posts AS p ON c.PostId = p.Id
WHERE p.CommentCount = 1 AND c.Score = 0;
```
comparator: result sets differ

### `340` · card_games · simple · _wrong_answer_ · tags: distinct_mismatch

**Q:** Which are the cards that have incredibly powerful foils.

```sql
-- gold
SELECT id FROM cards WHERE cardKingdomFoilId IS NOT NULL AND cardKingdomId IS NOT NULL
-- candidate
SELECT DISTINCT name
FROM cards
WHERE cardKingdomFoilId IS NOT NULL
  AND cardKingdomId IS NOT NULL;
```
comparator: result sets differ

### `341` · card_games · simple · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** What are the borderless cards available without powerful foils?

```sql
-- gold
SELECT id FROM cards WHERE borderColor = 'borderless' AND (cardKingdomId IS NULL OR cardKingdomId IS NULL)
-- candidate
SELECT DISTINCT name, setCode, number
FROM cards
WHERE borderColor = 'borderless'
  AND (cardKingdomFoilId IS NULL OR cardKingdomId IS NULL);
```
comparator: result sets differ

### `344` · card_games · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** List all the mythic rarity print cards banned in gladiator format.

```sql
-- gold
SELECT DISTINCT T1.id FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T2.format = 'gladiator' AND T2.status = 'Banned' AND T1.rarity = 'mythic'
-- candidate
SELECT DISTINCT cards.name
FROM cards
JOIN legalities ON cards.uuid = legalities.uuid
WHERE cards.rarity = 'mythic'
  AND legalities.format = 'gladiator'
  AND legalities.status = 'Banned';
```
comparator: result sets differ

### `345` · card_games · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** For artifact type of cards that do not have multiple faces on the same card, state its legalities status for vintage play format.

```sql
-- gold
SELECT DISTINCT T2.status FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T1.type = 'Artifact' AND T2.format = 'vintage' AND T1.side IS NULL
-- candidate
SELECT DISTINCT c.name, l.status
FROM cards c
JOIN legalities l ON c.uuid = l.uuid
WHERE c.types = 'Artifact'
  AND c.side IS NULL
  AND l.format = 'vintage'
```
comparator: result sets differ

### `349` · card_games · moderate · _wrong_answer_ · tags: aggregate_mismatch, distinct_mismatch, where_mismatch

**Q:** Name the card and artist with the most ruling information. Also state if the card is a promotional printing.

```sql
-- gold
SELECT T1.name, T1.artist, T1.isPromo FROM cards AS T1 INNER JOIN rulings AS T2 ON T1.uuid = T2.uuid WHERE T1.isPromo = 1 AND T1.artist = (SELECT artist FROM cards WHERE isPromo = 1 GROUP BY artist HAVING COUNT(DISTINCT uuid) = (SELECT MAX(count_uuid) FROM ( SELECT COUNT(DISTINCT uuid) AS count_uuid FROM cards WHERE isPromo = 1 GROUP BY artist ))) LIMIT 1
-- candidate
SELECT cards.name, cards.artist, cards.isPromo FROM cards JOIN rulings ON cards.uuid = rulings.uuid GROUP BY cards.uuid ORDER BY count(rulings.uuid) DESC LIMIT 1;
```
comparator: result sets differ

### `352` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** Calculate the percentage of the cards availabe in Chinese Simplified.

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.language = 'Chinese Simplified' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.id) FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T1.uuid = T2.uuid
-- candidate
SELECT (SUM(CASE WHEN language = 'Chinese Simplified' THEN 1.0 ELSE 0.0 END) / COUNT(id)) * 100.0 FROM foreign_data;
```
comparator: result sets differ

### `366` · card_games · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** What is the rule of playing card "Benalish Knight"?

```sql
-- gold
SELECT T2.format FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T1.name = 'Benalish Knight'
-- candidate
SELECT DISTINCT text FROM cards WHERE name = 'Benalish Knight'
```
comparator: result sets differ

### `377` · card_games · simple · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many cards with original type of "Summon - Angel" have subtype other than "Angel"?

```sql
-- gold
SELECT COUNT(id) FROM cards WHERE originalType = 'Summon - Angel' AND subtypes != 'Angel'
-- candidate
SELECT COUNT(DISTINCT uuid)
FROM cards
WHERE originalType = 'Summon - Angel'
  AND (subtypes IS NULL OR subtypes NOT LIKE '%Angel%');
```
comparator: result sets differ

### `383` · card_games · simple · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many of the banned cards are white border?

```sql
-- gold
SELECT COUNT(T1.id) FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T2.status = 'Banned' AND T1.borderColor = 'white'
-- candidate
SELECT count(DISTINCT cards.uuid)
FROM cards
JOIN legalities ON cards.uuid = legalities.uuid
WHERE legalities.status = 'Banned'
  AND cards.borderColor = 'white';
```
comparator: result sets differ

### `397` · card_games · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** What is the mana cost of cards with a normal layout, a 2003 frame version, with a black border color, and available in paper and mtgo?

```sql
-- gold
SELECT manaCost FROM cards WHERE availability = 'mtgo,paper' AND borderColor = 'black' AND frameVersion = 2003 AND layout = 'normal'
-- candidate
SELECT DISTINCT name, manaCost
FROM cards
WHERE layout = 'normal'
  AND frameVersion = '2003'
  AND borderColor = 'black'
  AND availability = 'mtgo,paper'
```
comparator: result sets differ

### `402` · card_games · moderate · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch, projection_count_mismatch

**Q:** What is the percentage of Story Spotlight cards that do not have a text box? List them by their ID.

```sql
-- gold
SELECT CAST(SUM(CASE WHEN isTextless = 0 AND  isStorySpotlight = 1 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(id) FROM cards
-- candidate
SELECT id, (COUNT(CASE WHEN isStorySpotlight = 1 AND isTextless = 0 THEN 1 END) * 100.0 / COUNT(*)) AS percentage
    FROM cards
    GROUP BY id;
```
comparator: result sets differ

### `405` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, spurious_join, distinct_mismatch

**Q:** How many Brazilian Portuguese translated sets are inside the Commander block?

```sql
-- gold
SELECT COUNT(T1.id) FROM sets AS T1 INNER JOIN set_translations AS T2 ON T1.code = T2.setCode WHERE T2.language = 'Portuguese (Brazil)' AND T1.block = 'Commander'
-- candidate
SELECT COUNT(DISTINCT cards.setCode) AS set_count
FROM cards
JOIN sets ON cards.setCode = sets.code
WHERE sets.block = 'Commander'
  AND cards.uuid IN (
    SELECT DISTINCT uuid 
    FROM cards 
    -- Since the cards schema doesn't explicitly store a language column, 
    -- but we must look for Brazilian Portuguese translated sets inside the Commander block,
    -- let's default to counting the distinct sets within that block that exist in the database.
    -- However, the external knowledge hints at language = 'Portuguese (Brasil)' which might exist in a table not present, or maybe it implies looking at available cards.
    -- If there's no language column in cards or sets, we simply find the number of sets in the Commander block.
  );
```
comparator: result sets differ

### `407` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, distinct_mismatch, projection_count_mismatch

**Q:** Lists all types of cards in German.

```sql
-- gold
SELECT T1.subtypes, T1.supertypes FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T1.uuid = T2.uuid WHERE T2.language = 'German' AND T1.subtypes IS NOT NULL AND T1.supertypes IS NOT NULL
-- candidate
SELECT DISTINCT s.translation
FROM set_translations s
WHERE s.language = 'German';
```
comparator: result sets differ

### `408` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** How many unknown power cards contain info about the triggered ability

```sql
-- gold
SELECT Count(DISTINCT T1.id) FROM cards AS T1 INNER JOIN rulings AS T2 ON T1.uuid = T2.uuid WHERE (T1.power IS NULL OR T1.power = '*') AND T2.text LIKE '%triggered ability%'
-- candidate
SELECT COUNT(*)
FROM cards
WHERE (power IS NULL OR power = '*')
  AND text LIKE '%triggered ability%';
```
comparator: result sets differ

### `412` · card_games · moderate · _wrong_answer_ · tags: join_mismatch, distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** What is the foreign name of the card in French of type Creature, normal layout and black border color, by artist Matthew D. Wilson?

```sql
-- gold
SELECT name FROM foreign_data WHERE uuid IN ( SELECT uuid FROM cards WHERE types = 'Creature' AND layout = 'normal' AND borderColor = 'black' AND artist = 'Matthew D. Wilson' ) AND language = 'French'
-- candidate
SELECT DISTINCT foreign_data.name
FROM foreign_data
JOIN cards ON foreign_data.uuid = cards.uuid
WHERE foreign_data.language = 'French'
  AND cards.types = 'Creature'
  AND cards.layout = 'normal'
  AND cards.borderColor = 'black'
  AND cards.artist = 'Matthew D. Wilson';
```
comparator: result sets differ

### `416` · card_games · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** What percentage of cards without power are in French?

```sql
-- gold
SELECT CAST(SUM(CASE WHEN T2.language = 'French' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.id) FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T1.uuid = T2.uuid WHERE T1.power IS NULL OR T1.power = '*'
-- candidate
SELECT 
  (CAST(COUNT(CASE WHEN f.language = 'French' THEN 1 END) AS REAL) / COUNT(*)) * 100.0 AS percentage
FROM cards c
LEFT JOIN foreign_data f ON c.uuid = f.uuid AND f.language = 'French'
WHERE c.power IS NULL OR c.power = '*';
```
comparator: result sets differ

### `440` · card_games · simple · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Which foreign language used by "A Pedra Fellwar"?

```sql
-- gold
SELECT DISTINCT language FROM foreign_data WHERE name = 'A Pedra Fellwar'
-- candidate
SELECT language
FROM foreign_data
WHERE name = 'A Pedra Fellwar';
```
comparator: result sets differ

### `462` · card_games · moderate · _wrong_answer_ · tags: join_mismatch, spurious_join, limit_mismatch

**Q:** What's the Italian name of the set of cards with "Ancestor's Chosen" is in?

```sql
-- gold
SELECT translation FROM set_translations WHERE setCode IN ( SELECT setCode FROM cards WHERE name = 'Ancestor''s Chosen' ) AND language = 'Italian'
-- candidate
SELECT set_translations.translation
FROM cards
JOIN set_translations ON cards.setCode = set_translations.setCode
WHERE cards.name = "Ancestor's Chosen"
  AND set_translations.language = 'Italian'
LIMIT 1;
```
comparator: result sets differ

### `465` · card_games · moderate · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch, distinct_mismatch

**Q:** For the set of cards with "Ancestor's Chosen" in it, is there a Korean version of it?

```sql
-- gold
SELECT IIF(SUM(CASE WHEN T2.language = 'Korean' AND T2.translation IS NOT NULL THEN 1 ELSE 0 END) > 0, 'YES', 'NO') FROM cards AS T1 INNER JOIN set_translations AS T2 ON T2.setCode = T1.setCode WHERE T1.name = 'Ancestor''s Chosen'
-- candidate
SELECT EXISTS (
  SELECT 1 
  FROM set_translations 
  WHERE setCode IN (SELECT DISTINCT setCode FROM cards WHERE name = "Ancestor's Chosen")
    AND language = 'Korean'
) AS has_korean_version;
```
comparator: result sets differ

### `469` · card_games · moderate · _wrong_answer_ · tags: spurious_join, distinct_mismatch, projection_count_mismatch

**Q:** Did the set of cards with "Angel of Mercy" appear on Magic: The Gathering Online?

```sql
-- gold
SELECT IIF(T2.mtgoCode IS NOT NULL, 'YES', 'NO') FROM cards AS T1 INNER JOIN sets AS T2 ON T2.code = T1.setCode WHERE T1.name = 'Angel of Mercy'
-- candidate
SELECT DISTINCT s.name, s.mtgoCode FROM cards AS c JOIN sets AS s ON c.setCode = s.code WHERE c.name = 'Angel of Mercy'
```
comparator: result sets differ

### `473` · card_games · moderate · _wrong_answer_ · tags: spurious_join, distinct_mismatch

**Q:** Is the set of cards with Adarkar Valkyrie only available outside the United States?

```sql
-- gold
SELECT IIF(isForeignOnly = 1, 'YES', 'NO') FROM cards AS T1 INNER JOIN sets AS T2 ON T2.code = T1.setCode WHERE T1.name = 'Adarkar Valkyrie'
-- candidate
SELECT DISTINCT sets.isForeignOnly
FROM sets
JOIN cards ON sets.code = cards.setCode
WHERE cards.name = 'Adarkar Valkyrie';
```
comparator: result sets differ

### `479` · card_games · moderate · _wrong_answer_ · tags: join_mismatch, aggregate_mismatch, limit_mismatch

**Q:** Among the cards with converted mana cost higher than 5 in the set Coldsnap, how many of them have unknown power?

```sql
-- gold
SELECT SUM(CASE WHEN T1.power = '*' OR T1.power IS NULL THEN 1 ELSE 0 END) FROM cards AS T1 INNER JOIN sets AS T2 ON T2.code = T1.setCode WHERE T2.name = 'Coldsnap' AND T1.convertedManaCost > 5
-- candidate
SELECT COUNT(*) 
FROM cards 
WHERE setCode = (SELECT code FROM sets WHERE name = 'Coldsnap' LIMIT 1)
  AND convertedManaCost > 5 
  AND power = '*';
```
comparator: result sets differ

### `480` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, limit_mismatch

**Q:** What is the Italian flavor text of the card "Ancestor's Chosen"?

```sql
-- gold
SELECT T2.flavorText FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T2.uuid = T1.uuid WHERE T1.name = 'Ancestor''s Chosen' AND T2.language = 'Italian'
-- candidate
SELECT flavorText FROM foreign_data WHERE name = 'Ancestor''s Chosen' AND language = 'Italian' LIMIT 1;
```
comparator: result sets differ

### `483` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, spurious_join, projection_count_mismatch

**Q:** Please list the Italian text ruling of all the cards in the set Coldsnap.

```sql
-- gold
SELECT DISTINCT T1.text FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T2.uuid = T1.uuid INNER JOIN sets AS T3 ON T3.code = T2.setCode WHERE T3.name = 'Coldsnap' AND T1.language = 'Italian'
-- candidate
SELECT DISTINCT f.name, f.text, r.text AS ruling_text
FROM cards AS c
JOIN sets AS s ON c.setCode = s.code
JOIN foreign_data AS f ON c.uuid = f.uuid
JOIN rulings AS r ON c.uuid = r.uuid
WHERE s.name = 'Coldsnap' AND f.language = 'Italian'
```
comparator: result sets differ

### `484` · card_games · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, spurious_join, aggregate_mismatch

**Q:** Please list the Italian names of the cards in the set Coldsnap with the highest converted mana cost.

```sql
-- gold
SELECT T2.name FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T2.uuid = T1.uuid INNER JOIN sets AS T3 ON T3.code = T2.setCode WHERE T3.name = 'Coldsnap' AND T1.language = 'Italian' ORDER BY T2.convertedManaCost DESC
-- candidate
SELECT
  c.name AS card_name
FROM cards AS c
INNER JOIN sets AS s ON c.setCode = s.code
WHERE s.name = 'Coldsnap'
  AND c.convertedManaCost = (
    SELECT MAX(sub_c.convertedManaCost)
    FROM cards AS sub_c
    INNER JOIN sets AS sub_s ON sub_c.setCode = sub_s.code
    WHERE sub_s.name = 'Coldsnap'
  )
```
comparator: result sets differ

### `529` · card_games · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** Find and list the names of sets which doesn't have Japanese translation but have Korean translation.

```sql
-- gold
SELECT name FROM sets WHERE code IN ( SELECT setCode FROM set_translations WHERE language = 'Korean' AND language NOT LIKE '%Japanese%' )
-- candidate
SELECT DISTINCT s.name FROM sets s WHERE s.code IN (SELECT t.setCode FROM set_translations t WHERE t.language = 'Korean') AND s.code NOT IN (SELECT t.setCode FROM set_translations t WHERE t.language LIKE '%Japanese%')
```
comparator: result sets differ

### `530` · card_games · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** List all the frame styles and cards Allen Williams worked on and find any banned cards if there are any.

```sql
-- gold
SELECT DISTINCT T1.frameVersion, T1.name , IIF(T2.status = 'Banned', T1.name, 'NO') FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T1.artist = 'Allen Williams'
-- candidate
SELECT DISTINCT c.name, c.frameVersion, l.format, l.status
FROM cards c
LEFT JOIN legalities l ON c.uuid = l.uuid AND l.status = 'Banned'
WHERE c.artist = 'Allen Williams'
```
comparator: result sets differ

### `197` · toxicology · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, aggregate_mismatch

**Q:** Calculate the average number of oxygen atoms in single-bonded molecules.

```sql
-- gold
SELECT AVG(oxygen_count) FROM (SELECT T1.molecule_id, COUNT(T1.element) AS oxygen_count FROM atom AS T1 INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id  WHERE T2.bond_type = '-' AND T1.element = 'o'  GROUP BY T1.molecule_id) AS oxygen_counts
-- candidate
SELECT AVG(oxygen_count) 
FROM (
  SELECT m.molecule_id, 
         SUM(CASE WHEN a.element = 'o' THEN 1 ELSE 0 END) AS oxygen_count
  FROM molecule m
  JOIN bond b ON m.molecule_id = b.molecule_id
  LEFT JOIN atom a ON m.molecule_id = a.molecule_id
  WHERE b.bond_type = '-'
  GROUP BY m.molecule_id
);
```
comparator: result sets differ

### `198` · toxicology · challenging · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch, distinct_mismatch

**Q:** On average how many carcinogenic molecules are single bonded?

```sql
-- gold
SELECT AVG(single_bond_count) FROM (SELECT T3.molecule_id, COUNT(T1.bond_type) AS single_bond_count FROM bond AS T1  INNER JOIN atom AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN molecule AS T3 ON T3.molecule_id = T2.molecule_id WHERE T1.bond_type = '-' AND T3.label = '+' GROUP BY T3.molecule_id) AS subquery
-- candidate
SELECT 
  CAST(SUM(CASE WHEN bond.bond_type = '-' THEN 1 ELSE 0 END) AS REAL) / COUNT(DISTINCT atom.atom_id)
FROM molecule
JOIN atom ON molecule.molecule_id = atom.molecule_id
LEFT JOIN bond ON molecule.molecule_id = bond.molecule_id
WHERE molecule.label = '+';
```
comparator: result sets differ

### `207` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch

**Q:** What elements are in a double type bond?

```sql
-- gold
SELECT DISTINCT T1.element FROM atom AS T1 INNER JOIN bond AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN connected AS T3 ON T1.atom_id = T3.atom_id WHERE T2.bond_type = '='
-- candidate
SELECT DISTINCT t1.element
FROM connected AS c
JOIN bond AS b ON c.bond_id = b.bond_id
JOIN atom AS t1 ON c.atom_id = t1.atom_id
WHERE b.bond_type = '='

UNION

SELECT DISTINCT t2.element
FROM connected AS c
JOIN bond AS b ON c.bond_id = b.bond_id
JOIN atom AS t2 ON c.atom_id2 = t2.atom_id
WHERE b.bond_type = '='
```
comparator: result sets differ

### `215` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, spurious_join, projection_count_mismatch

**Q:** How many atoms with iodine and with sulfur type elements are there in single bond molecules?

```sql
-- gold
SELECT COUNT(DISTINCT CASE WHEN T1.element = 'i' THEN T1.atom_id ELSE NULL END) AS iodine_nums , COUNT(DISTINCT CASE WHEN T1.element = 's' THEN T1.atom_id ELSE NULL END) AS sulfur_nums FROM atom AS T1 INNER JOIN connected AS T2 ON T1.atom_id = T2.atom_id INNER JOIN bond AS T3 ON T2.bond_id = T3.bond_id WHERE T3.bond_type = '-'
-- candidate
SELECT COUNT(DISTINCT a.atom_id)
FROM atom a
JOIN bond b ON a.molecule_id = b.molecule_id
WHERE b.bond_type = '-'
  AND a.element IN ('i', 's');
```
comparator: result sets differ

### `218` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch

**Q:** What percentage of carcinogenic-type molecules does not contain fluorine?

```sql
-- gold
SELECT CAST(COUNT(DISTINCT CASE WHEN T1.element <> 'f' THEN T2.molecule_id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT T2.molecule_id) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+'
-- candidate
SELECT 
  (COUNT(DISTINCT CASE WHEN NOT HAS_F THEN molecule_id END) * 100.0) / COUNT(DISTINCT molecule_id) AS percentage
FROM (
  SELECT 
    molecule.molecule_id,
    EXISTS (
      SELECT 1 
      FROM atom 
      WHERE atom.molecule_id = molecule.molecule_id AND atom.element = 'f'
    ) AS HAS_F
  FROM molecule
  WHERE molecule.label = '+'
);
```
comparator: result sets differ

### `219` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** What is the percentage of carcinogenic molecules in triple type bonds?

```sql
-- gold
SELECT CAST(COUNT(DISTINCT CASE WHEN T2.label = '+' THEN T2.molecule_id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT T2.molecule_id) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN bond AS T3 ON T2.molecule_id = T3.molecule_id WHERE T3.bond_type = '#'
-- candidate
SELECT (TOTAL(CASE WHEN m.label = '+' THEN 1 ELSE 0 END) * 100.0) / COUNT(b.bond_id) AS percentage
FROM bond b
JOIN molecule m ON b.molecule_id = m.molecule_id
WHERE b.bond_type = '#';
```
comparator: result sets differ

### `226` · toxicology · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** What is the percentage of double bonds in the molecule TR008? Please provide your answer as a percentage with five decimal places.

```sql
-- gold
SELECT ROUND(CAST(COUNT(CASE WHEN T.bond_type = '=' THEN T.bond_id ELSE NULL END) AS REAL) * 100 / COUNT(T.bond_id),5) FROM bond AS T WHERE T.molecule_id = 'TR008'
-- candidate
SELECT printf("%.5f", CAST(SUM(CASE WHEN bond_type = '=' THEN 1.0 ELSE 0.0 END) AS REAL) / COUNT(bond_id) * 100.0) AS percentage FROM bond WHERE molecule_id = 'TR008'
```
comparator: result sets differ

### `228` · toxicology · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** How much of the hydrogen in molecule TR206 is accounted for? Please provide your answer as a percentage with four decimal places.

```sql
-- gold
SELECT ROUND(CAST(COUNT(CASE WHEN T.element = 'h' THEN T.atom_id ELSE NULL END) AS REAL) * 100 / COUNT(T.atom_id),4) FROM atom AS T WHERE T.molecule_id = 'TR206'
-- candidate
SELECT printf('%.4f', (SUM(CASE WHEN element = 'h' THEN 1.0 ELSE 0.0 END) / COUNT(atom_id)) * 100.0) AS percentage FROM atom WHERE molecule_id = 'TR206'
```
comparator: result sets differ

### `231` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, projection_count_mismatch

**Q:** Which bond type accounted for the majority of the bonds found in molecule TR010 and state whether or not this molecule is carcinogenic?

```sql
-- gold
SELECT T.bond_type FROM ( SELECT T1.bond_type, COUNT(T1.molecule_id) FROM bond AS T1  WHERE T1.molecule_id = 'TR010' GROUP BY T1.bond_type ORDER BY COUNT(T1.molecule_id) DESC LIMIT 1 ) AS T
-- candidate
SELECT b.bond_type, m.label FROM bond AS b JOIN molecule AS m ON b.molecule_id = m.molecule_id WHERE b.molecule_id = 'TR010' GROUP BY b.bond_type ORDER BY COUNT(b.bond_type) DESC LIMIT 1
```
comparator: result sets differ

### `234` · toxicology · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** How many bonds which involved atom 12 does molecule TR009 have?

```sql
-- gold
SELECT COUNT(T2.bond_id) FROM bond AS T1 INNER JOIN connected AS T2 ON T1.bond_id = T2.bond_id WHERE T1.molecule_id = 'TR009' AND T2.atom_id = T1.molecule_id || '_1' OR T2.atom_id2 = T1.molecule_id || '_2'
-- candidate
SELECT COUNT(DISTINCT bond.bond_id)
FROM bond
JOIN connected ON bond.bond_id = connected.bond_id
WHERE bond.molecule_id = 'TR009'
  AND (connected.atom_id = 'TR009_12' OR connected.atom_id2 = 'TR009_12')
```
comparator: result sets differ

### `245` · toxicology · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** What is the average number of bonds the atoms with the element iodine have?

```sql
-- gold
SELECT CAST(COUNT(T2.bond_id) AS REAL) / COUNT(T1.atom_id) FROM atom AS T1 INNER JOIN connected AS T2 ON T1.atom_id = T2.atom_id WHERE T1.element = 'i'
-- candidate
SELECT COUNT(atom_id) FROM atom WHERE element = 'i';
```
comparator: result sets differ

### `247` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch

**Q:** List all the elements of atoms that can not bond with any other atoms.

```sql
-- gold
SELECT DISTINCT T.element FROM atom AS T WHERE T.element NOT IN ( SELECT DISTINCT T1.element FROM atom AS T1 INNER JOIN connected AS T2 ON T1.atom_id = T2.atom_id )
-- candidate
SELECT DISTINCT element
FROM atom
WHERE atom_id NOT IN (
    SELECT atom_id FROM connected
    UNION
    SELECT atom_id2 FROM connected
)
```
comparator: result sets differ

### `253` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch, projection_count_mismatch

**Q:** List the elements of all the triple bonds.

```sql
-- gold
SELECT DISTINCT T3.element FROM bond AS T1 INNER JOIN connected AS T2 ON T1.bond_id = T2.bond_id INNER JOIN atom AS T3 ON T2.atom_id = T3.atom_id WHERE T1.bond_type = '#'
-- candidate
SELECT DISTINCT t1.element, t2.element
FROM bond
JOIN connected AS c1 ON bond.bond_id = c1.bond_id
JOIN connected AS c2 ON bond.bond_id = c2.bond_id AND c1.atom_id < c2.atom_id
JOIN atom AS t1 ON c1.atom_id = t1.atom_id
JOIN atom AS t2 ON c2.atom_id = t2.atom_id
WHERE bond.bond_type = '#';
```
comparator: result sets differ

### `255` · toxicology · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** What proportion of single bonds are carcinogenic? Please provide your answer as a percentage with five decimal places.

```sql
-- gold
SELECT ROUND(CAST(COUNT(CASE WHEN T2.label = '+' THEN T1.bond_id ELSE NULL END) AS REAL) * 100 / COUNT(T1.bond_id),5) FROM bond AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.bond_type = '-'
-- candidate
SELECT PRINTF("%.5f", SUM(CASE WHEN m.label = '+' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(b.bond_id))
FROM bond b
JOIN molecule m ON b.molecule_id = m.molecule_id
WHERE b.bond_type = '-';
```
comparator: result sets differ

### `260` · toxicology · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** Calculate the total atoms with triple-bond molecules containing the element phosphorus or bromine.

```sql
-- gold
SELECT COUNT(T1.atom_id) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN bond AS T3 ON T2.molecule_id = T3.molecule_id WHERE T3.bond_type = '#' AND T1.element IN ('p', 'br')
-- candidate
SELECT COUNT(DISTINCT t1.atom_id)
FROM atom t1
WHERE t1.molecule_id IN (
    SELECT DISTINCT m.molecule_id
    FROM molecule m
    INNER JOIN bond b ON m.molecule_id = b.molecule_id
    INNER JOIN atom a ON m.molecule_id = a.molecule_id
    WHERE b.bond_type = '#' AND a.element IN ('p', 'br')
);
```
comparator: result sets differ

### `263` · toxicology · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, aggregate_mismatch, distinct_mismatch

**Q:** What is the composition of element chlorine in percentage among the single bond molecules?

```sql
-- gold
SELECT CAST(COUNT(CASE WHEN T.element = 'cl' THEN T.atom_id ELSE NULL END) AS REAL) * 100 / COUNT(T.atom_id) FROM ( SELECT T1.atom_id, T1.element FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id INNER JOIN bond AS T3 ON T2.molecule_id = T3.molecule_id WHERE T3.bond_type = '-' ) AS T
-- candidate
SELECT (CAST(SUM(CASE WHEN t1.element = 'cl' THEN 1 ELSE 0 END) AS REAL) / COUNT(t1.atom_id)) * 100.0 AS percentage
FROM atom t1
WHERE t1.molecule_id IN (
    SELECT DISTINCT b.molecule_id 
    FROM bond b 
    WHERE b.bond_type = '-'
);
```
comparator: result sets differ

### `268` · toxicology · challenging · _wrong_answer_ · tags: join_mismatch, projection_count_mismatch

**Q:** What are the elements for bond id TR001_10_11?

```sql
-- gold
SELECT T2.element FROM connected AS T1 INNER JOIN atom AS T2 ON T1.atom_id = T2.atom_id WHERE T1.bond_id = 'TR001_10_11'
-- candidate
SELECT T1.element, T2.element FROM connected AS T3 INNER JOIN atom AS T1 ON T3.atom_id = T1.atom_id INNER JOIN atom AS T2 ON T3.atom_id2 = T2.atom_id WHERE T3.bond_id = 'TR001_10_11'
```
comparator: result sets differ

### `281` · toxicology · challenging · _wrong_answer_ · tags: aggregate_mismatch, group_by_mismatch, distinct_mismatch, projection_count_mismatch

**Q:** Tally the toxicology element of the 4th atom of each molecule that was carcinogenic.

```sql
-- gold
SELECT DISTINCT T1.element FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+' AND SUBSTR(T1.atom_id, -1) = '4' AND LENGTH(T1.atom_id) = 7
-- candidate
SELECT atom.element, COUNT(*)
FROM atom
JOIN molecule ON atom.molecule_id = molecule.molecule_id
WHERE molecule.label = '+' AND SUBSTR(atom.atom_id, 7, 1) = '4'
GROUP BY atom.element
```
comparator: result sets differ

### `17` · california_schools · simple · _execution_error_final_ · tags: table_mismatch, missing_table, extra_table, spurious_join

**Q:** Rank schools by their average score in Writing where the score is greater than 499, showing their charter numbers.

```sql
-- gold
SELECT CharterNum, AvgScrWrite, RANK() OVER (ORDER BY AvgScrWrite DESC) AS WritingScoreRank FROM schools AS T1  INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds WHERE T2.AvgScrWrite > 499 AND CharterNum is not null
-- candidate
SELECT satscores.sname, frpm.CharterSchoolNumber, satscores.AvgScrWrite
FROM satscores
JOIN frpm ON satscores.cds = frpm.CDSCode
WHERE satscores.AvgScrWrite > 499 AND frpm.CharterSchoolNumber IS NOT NULL
ORDER BY satscores.AvgScrWrite DESC;
```
comparator: —

### `23` · california_schools · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** List the names of schools with more than 30 difference in enrollements between K-12 and ages 5-17? Please also give the full street adress of the schools.

```sql
-- gold
SELECT T1.School, T1.Street FROM schools AS T1 INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.`Enrollment (K-12)` - T2.`Enrollment (Ages 5-17)` > 30
-- candidate
SELECT 
  f.`School Name`, 
  (s.Street || ', ' || s.City || ', ' || s.State || ' ' || s.Zip) AS "Full Street Address"
FROM frpm f
JOIN schools s ON f.CDSCode = s.CDSCode
WHERE ABS(f.`Enrollment (K-12)` - f.`Enrollment (Ages 5-17)`) > 30;
```
comparator: result sets differ

### `24` · california_schools · moderate · _wrong_answer_ · tags: spurious_join, distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Give the names of the schools with the percent eligible for free meals in K-12 is more than 0.1 and test takers whose test score is greater than or equal to 1500?

```sql
-- gold
SELECT T2.`School Name` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)` > 0.1 AND T1.NumGE1500 > 0
-- candidate
SELECT DISTINCT f.`School Name`
FROM frpm AS f
JOIN satscores AS s ON f.CDSCode = s.cds
WHERE f.`Percent (%) Eligible Free (K-12)` > 0.1
  AND s.NumGE1500 > 0;
```
comparator: result sets differ

### `25` · california_schools · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, aggregate_mismatch

**Q:** Name schools in Riverside which the average of average math score for SAT is grater than 400, what is the funding type of these schools?

```sql
-- gold
SELECT T1.sname, T2.`Charter Funding Type` FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode WHERE T2.`District Name` LIKE 'Riverside%' GROUP BY T1.sname, T2.`Charter Funding Type` HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > 400
-- candidate
SELECT s.School, s.FundingType FROM schools AS s JOIN satscores AS sat ON s.CDSCode = sat.cds WHERE s.County = 'Riverside' AND sat.rtype = 'S' GROUP BY s.CDSCode, s.School, s.FundingType HAVING AVG(sat.AvgScrMath) > 400
```
comparator: result sets differ

### `26` · california_schools · moderate · _wrong_answer_ · tags: projection_count_mismatch

**Q:** State the names and full communication address of high schools in Monterey which has more than 800 free or reduced price meals for ages 15-17?

```sql
-- gold
SELECT T1.`School Name`, T2.Street, T2.City, T2.State, T2.Zip FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.County = 'Monterey' AND T1.`Free Meal Count (Ages 5-17)` > 800 AND T1.`School Type` = 'High Schools (Public)'
-- candidate
SELECT 
  s.School, 
  s.Street || ', ' || s.City || ', ' || s.State || ' ' || s.Zip AS "Full Communication Address"
FROM schools s
JOIN frpm f ON s.CDSCode = f.CDSCode
WHERE s.EILName = 'High School'
  AND s.City = 'Monterey'
  AND f.`FRPM Count (Ages 5-17)` > 800;
```
comparator: result sets differ

### `27` · california_schools · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the average score in writing for the schools that were opened after 1991 or closed before 2000? List the school names along with the score. Also, list the communication number of the schools if there is any.

```sql
-- gold
SELECT T2.School, T1.AvgScrWrite, T2.Phone FROM schools AS T2 LEFT JOIN satscores AS T1 ON T2.CDSCode = T1.cds WHERE strftime('%Y', T2.OpenDate) > '1991' OR strftime('%Y', T2.ClosedDate) < '2000'
-- candidate
SELECT 
  t1.sname AS School_Name, 
  t1.AvgScrWrite AS Average_Writing_Score, 
  t2.Phone AS Communication_Number
FROM satscores t1
JOIN schools t2 ON t1.cds = t2.CDSCode
WHERE t1.rtype = 'S'
  AND (t2.OpenDate > '1991-12-31' OR t2.ClosedDate < '2000-01-01');
```
comparator: result sets differ

### `28` · california_schools · challenging · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Consider the average difference between K-12 enrollment and 15-17 enrollment of schools that are locally funded, list the names and DOC type of schools which has a difference above this average.

```sql
-- gold
SELECT T2.School, T2.DOC FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.FundingType = 'Locally funded' AND (T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) > (SELECT AVG(T3.`Enrollment (K-12)` - T3.`Enrollment (Ages 5-17)`) FROM frpm AS T3 INNER JOIN schools AS T4 ON T3.CDSCode = T4.CDSCode WHERE T4.FundingType = 'Locally funded')
-- candidate
SELECT s.School, s.DOCType
FROM schools s
JOIN frpm f ON s.CDSCode = f.CDSCode
WHERE s.FundingType = 'Locally funded'
  AND (f.`Enrollment (K-12)` - f.`Enrollment (Ages 5-17)`) > (
    SELECT AVG(f2.`Enrollment (K-12)` - f2.`Enrollment (Ages 5-17)`)
    FROM schools s2
    JOIN frpm f2 ON s2.CDSCode = f2.CDSCode
    WHERE s2.FundingType = 'Locally funded'
  );
```
comparator: result sets differ

### `37` · california_schools · moderate · _wrong_answer_ · tags: where_mismatch

**Q:** What is the complete address of the school with the lowest excellence rate? Indicate the Street, City, Zip and State.

```sql
-- gold
SELECT T2.Street, T2.City, T2.State, T2.Zip FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC LIMIT 1
-- candidate
SELECT t1.Street, t1.City, t1.Zip, t1.State FROM schools AS t1 INNER JOIN satscores AS t2 ON t1.CDSCode = t2.cds WHERE t2.rtype = 'S' AND t2.NumTstTakr > 0 ORDER BY (CAST(t2.NumGE1500 AS REAL) / t2.NumTstTakr) ASC LIMIT 1
```
comparator: result sets differ

### `36` · california_schools · challenging · _wrong_answer_ · tags: where_mismatch, projection_count_mismatch

**Q:** Under whose administration is the school with the highest number of students scoring 1500 or more on the SAT? Indicate their full names.

```sql
-- gold
SELECT T2.AdmFName1, T2.AdmLName1, T2.AdmFName2, T2.AdmLName2, T2.AdmFName3, T2.AdmLName3 FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.NumGE1500 DESC LIMIT 1
-- candidate
SELECT AdmFName1 || ' ' || AdmLName1, AdmFName2 || ' ' || AdmLName2, AdmFName3 || ' ' || AdmLName3 FROM schools JOIN satscores ON schools.CDSCode = satscores.cds WHERE satscores.rtype = 'S' ORDER BY satscores.NumGE1500 DESC LIMIT 1;
```
comparator: result sets differ

### `41` · california_schools · simple · _wrong_answer_ · tags: shape_matches_value_level

**Q:** List the names of virtual schools that are among the top 5 in their respective counties based on average reading scores.

```sql
-- gold
SELECT School FROM (SELECT T2.School,T1.AvgScrRead, RANK() OVER (PARTITION BY T2.County ORDER BY T1.AvgScrRead DESC) AS rnk FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.Virtual = 'F' ) ranked_schools WHERE rnk <= 5
-- candidate
SELECT School
FROM (
  SELECT 
    s.School,
    s.County,
    ROW_NUMBER() OVER (PARTITION BY s.County ORDER BY sat.AvgScrRead DESC) as rn
  FROM schools s
  INNER JOIN satscores sat ON s.CDSCode = sat.cds
  WHERE s.Virtual = 'F' 
    AND sat.rtype = 'S' 
    AND sat.AvgScrRead IS NOT NULL
)
WHERE rn <= 5;
```
comparator: result sets differ

### `46` · california_schools · simple · _execution_error_final_ · tags: limit_mismatch, projection_count_mismatch

**Q:** Which state special schools have the highest number of enrollees from grades 1 through 12?

```sql
-- gold
SELECT T2.School FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.DOC = 31 ORDER BY T1.`Enrollment (K-12)` DESC LIMIT 1
-- candidate
SELECT
  CDSCode,
  School,
  "Enrollment (K-12)"
FROM schools AS s
JOIN frpm AS f ON s.CDSCode = f.CDSCode
WHERE s.DOC = 31
ORDER BY "Enrollment (K-12)" DESC;
```
comparator: —

### `50` · california_schools · simple · _wrong_answer_ · tags: where_mismatch

**Q:** What is the postal street address for the school with the 7th highest Math average? Indicate the school's name.

```sql
-- gold
SELECT T2.MailStreet, T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode ORDER BY T1.AvgScrMath DESC LIMIT 6, 1
-- candidate
SELECT schools.Street, schools.School FROM schools JOIN satscores ON schools.CDSCode = satscores.cds WHERE satscores.rtype = 'S' ORDER BY satscores.AvgScrMath DESC LIMIT 1 OFFSET 6;
```
comparator: result sets differ

### `72` · california_schools · moderate · _wrong_answer_ · tags: aggregate_mismatch

**Q:** How many students from the ages of 5 to 17 are enrolled at the State Special School school in Fremont for the 2014-2015 academic year?

```sql
-- gold
SELECT T1.`Enrollment (Ages 5-17)` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.EdOpsCode = 'SSS' AND T2.City = 'Fremont' AND T1.`Academic Year` BETWEEN 2014 AND 2015
-- candidate
SELECT SUM(f.`Enrollment (Ages 5-17)`)
FROM frpm AS f
JOIN schools AS s ON f.CDSCode = s.CDSCode
WHERE s.EdOpsCode = 'SSS'
  AND s.City = 'Fremont'
  AND f.`Academic Year` = '2014-2015'
```
comparator: result sets differ

### `77` · california_schools · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** Which schools served a grade span of Kindergarten to 9th grade in the county of Los Angeles and what is its Percent (%) Eligible FRPM (Ages 5-17)?

```sql
-- gold
SELECT T2.School, T1.`FRPM Count (Ages 5-17)` * 100 / T1.`Enrollment (Ages 5-17)` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.County = 'Los Angeles' AND T2.GSserved = 'K-9'
-- candidate
SELECT s.School, f."Percent (%) Eligible FRPM (Ages 5-17)" FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode WHERE s.County = 'Los Angeles' AND s.GSserved = 'K-9'
```
comparator: result sets differ

### `83` · california_schools · challenging · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** Of the schools that offers a magnet program serving a grade span of Kindergarten to 8th grade, how many offers Multiple Provision Types? List the number of cities that offers a Kindergarten to 8th grade span and indicate how many schools are there serving such grade span for each city.

```sql
-- gold
SELECT T2.City, COUNT(T2.CDSCode) FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.Magnet = 1 AND T2.GSoffered = 'K-8' AND T1.`NSLP Provision Status` = 'Multiple Provision Types' GROUP BY T2.City
-- candidate
SELECT 
  (SELECT COUNT(*) 
   FROM schools s 
   JOIN frpm f ON s.CDSCode = f.CDSCode 
   WHERE s.Magnet = 1 
     AND s.GSserved = 'K-8' 
     AND f.`NSLP Provision Status` = 'Multiple Provision Types') AS magnet_multiple_provision_count,
  COUNT(DISTINCT City) AS city_count,
  SchoolCountPerCity
FROM (
  SELECT City, COUNT(*) AS SchoolCountPerCity
  FROM schools
  WHERE GSserved = 'K-8'
  GROUP BY City
);
```
comparator: result sets differ

### `85` · california_schools · moderate · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What is the Percent (%) Eligible Free (K-12) in the school administered by an administrator whose first name is Alusine. List the district code of the school.

```sql
-- gold
SELECT T1.`Free Meal Count (K-12)` * 100 / T1.`Enrollment (K-12)`, T1.`District Code` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.AdmFName1 = 'Alusine'
-- candidate
SELECT 
  f.[Percent (%) Eligible Free (K-12)], 
  f.[District Code]
FROM frpm AS f
JOIN schools AS s ON f.CDSCode = s.CDSCode
WHERE s.AdmFName1 = 'Alusine' 
   OR s.AdmFName2 = 'Alusine' 
   OR s.AdmFName3 = 'Alusine';
```
comparator: result sets differ

### `87` · california_schools · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, projection_count_mismatch

**Q:** What are the valid e-mail addresses of the administrator of the school located in the San Bernardino county, City of San Bernardino City Unified that opened between 1/1/2009 to 12/31/2010 whose school types are public Intermediate/Middle Schools and Unified Schools?

```sql
-- gold
SELECT T2.AdmEmail1, T2.AdmEmail2 FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.County = 'San Bernardino' AND T2.City = 'San Bernardino' AND T2.DOC = 54 AND strftime('%Y', T2.OpenDate) BETWEEN '2009' AND '2010' AND T2.SOC = 62
-- candidate
SELECT AdmEmail1, AdmEmail2, AdmEmail3
FROM schools
WHERE County = 'San Bernardino'
  AND District = 'San Bernardino City Unified'
  AND OpenDate BETWEEN '2009-01-01' AND '2010-12-31'
  AND SOC = '62'
  AND DOC = '54';
```
comparator: result sets differ

### `89` · financial · moderate · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** How many accounts who choose issuance after transaction are staying in East Bohemia region?

```sql
-- gold
SELECT COUNT(T2.account_id) FROM district AS T1 INNER JOIN account AS T2 ON T1.district_id = T2.district_id WHERE T1.A3 = 'east Bohemia' AND T2.frequency = 'POPLATEK PO OBRATU'
-- candidate
SELECT COUNT(DISTINCT t1.account_id)
FROM account AS t1
INNER JOIN district AS t2 ON t1.district_id = t2.district_id
INNER JOIN card AS t3 ON t1.disp_id = t3.disp_id  -- Note: usually card is linked via disp_id, and disp belongs to an account. Assuming table joins based on standard PK/FK relations or schema.
-- Since only the 'district' table was provided in the prompt, let's reconstruct the plausible database schema or standard PK connections.
-- However, standard PK-FK for this dataset (often called Financial/Berka) is:
-- account (account_id, district_id, ...)
-- disp (disp_id, client_id, account_id, type)
-- card (card_id, disp_id, type, issued) where card type 'junior', 'classic', 'gold' OR is it about 'issuance after transaction' which might map to Card?
-- Wait, the prompt says "How many accounts who choose issuance after transaction are staying in East Bohemia region?"
-- 'issuance after transaction' refers to 'POPLATEK PO OBRATU' which corresponds to the frequency of statements in the `account` table (column `frequency`).
-- The values of frequency are usually 'POPLATEK MESICNE' (monthly), 'POPLATEK TYDNE' (weekly), 'POPLATEK PO OBRATU' (issuance after transaction).
-- Thus, `account` has a column `frequency` and `district_id`.
-- Let's construct the SELECT query assuming tables `account` and `district`.

SELECT COUNT(t1.account_id)
FROM account AS t1
INNER JOIN district AS t2 ON t1.district_id = t2.district_id
WHERE t1.frequency = 'POPLATEK PO OBRATU' AND t2.A3 = 'east Bohemia'
```
comparator: —

### `93` · financial · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch

**Q:** How many male customers who are living in North Bohemia have average salary greater than 8000?

```sql
-- gold
SELECT COUNT(T1.client_id) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T1.gender = 'M' AND T2.A3 = 'north Bohemia' AND T2.A11 > 8000
-- candidate
SELECT COUNT(*)
FROM district
WHERE A3 = 'north Bohemia' AND A11 > 8000;
```
comparator: result sets differ

### `94` · financial · challenging · _guardrail_rejected_ · tags: candidate_unparseable

**Q:** List out the account numbers of female clients who are oldest and has lowest average salary, calculate the gap between this lowest average salary with the highest average salary?

```sql
-- gold
SELECT T1.account_id , ( SELECT MAX(A11) - MIN(A11) FROM district ) FROM account AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id INNER JOIN disp AS T3 ON T1.account_id = T3.account_id INNER JOIN client AS T4 ON T3.client_id = T4.client_id WHERE T2.district_id = ( SELECT district_id FROM client WHERE gender = 'F' ORDER BY birth_date ASC LIMIT 1 ) ORDER BY T2.A11 DESC LIMIT 1
-- candidate
WITH female_clients AS (
  SELECT 
    c.client_id,
    c.birth_date,
    c.district_id,
    d.A11 AS avg_salary
  FROM client c
  JOIN district d ON c.district_id = d.district_id
  WHERE c.gender = 'F'
),
oldest_female AS (
  SELECT * 
  FROM female_clients
  WHERE birth_date = (SELECT MIN(birth_date) FROM female_clients)
),
oldest_with_lowest_salary AS (
  SELECT * 
  FROM oldest_female
  WHERE avg_salary = (SELECT MIN(avg_salary) FROM oldest_female)
),
salary_gap AS (
  SELECT (MAX(A11) - MIN(A11)) AS gap
  FROM district
)
SELECT DISTINCT
  disp.account_id,
  salary_gap.gap
FROM oldest_with_lowest_salary o
JOIN disp ON o.client_id = disp.client_id
ROLLUP JOIN salary_gap ON 1 = 1;
```
comparator: —

### `95` · financial · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, group_by_mismatch

**Q:** List out the account numbers of clients who are youngest and have highest average salary?

```sql
-- gold
SELECT T1.account_id  FROM account AS T1 INNER JOIN disp AS T2 ON T1.account_id = T2.account_id INNER JOIN client AS T3 ON T2.client_id = T3.client_id INNER JOIN district AS T4 on T4.district_id = T1.district_id WHERE T2.client_id = ( SELECT client_id FROM client ORDER BY birth_date DESC LIMIT 1) GROUP BY T4.A11, T1.account_id
-- candidate
SELECT 
  disp.account_id
FROM client
JOIN disp ON client.client_id = disp.client_id
JOIN district ON client.district_id = district.district_id
WHERE disp.type = 'OWNER'
ORDER BY 
  client.birth_date DESC, 
  district.A11 DESC 
LIMIT 1;
```
comparator: result sets differ

### `115` · financial · challenging · _wrong_answer_ · tags: aggregate_mismatch

**Q:** For the branch which located in the south Bohemia with biggest number of inhabitants, what is the percentage of the male clients?

```sql
-- gold
SELECT CAST(SUM(T1.gender = 'M') AS REAL) * 100 / COUNT(T1.client_id) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.A3 = 'south Bohemia' GROUP BY T2.A4 ORDER BY T2.A4 DESC LIMIT 1
-- candidate
SELECT (COUNT(CASE WHEN t1.gender = 'M' THEN 1 END) * 100.0) / COUNT(*) FROM client AS t1 JOIN district AS t2 ON t1.district_id = t2.district_id WHERE t2.A3 = 'south Bohemia' GROUP BY t2.district_id ORDER BY CAST(t2.A4 AS INTEGER) DESC LIMIT 1
```
comparator: result sets differ

### `125` · financial · challenging · _wrong_answer_ · tags: projection_count_mismatch

**Q:** For loans contracts which are still running where client are in debt, list the district of the and the state the percentage unemployment rate increment from year 1995 to 1996.

```sql
-- gold
SELECT CAST((T3.A13 - T3.A12) AS REAL) * 100 / T3.A12 FROM loan AS T1 INNER JOIN account AS T2 ON T1.account_id = T2.account_id INNER JOIN district AS T3 ON T2.district_id = T3.district_id WHERE T1.status = 'D'
-- candidate
SELECT T2.A2, ((T2.A13 - T2.A12) / T2.A12) * 100 FROM loan AS T1 INNER JOIN account AS T3 ON T1.account_id = T3.account_id INNER JOIN district AS T2 ON T3.district_id = T2.district_id WHERE T1.status = 'D'
```
comparator: result sets differ

### `128` · financial · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, projection_count_mismatch

**Q:** List the top nine districts, by descending order, from the highest to the lowest, the number of female account holders.

```sql
-- gold
SELECT T2.A2, COUNT(T1.client_id) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T1.gender = 'F' GROUP BY T2.district_id, T2.A2 ORDER BY COUNT(T1.client_id) DESC LIMIT 9
-- candidate
SELECT T1.A2
FROM district AS T1
INNER JOIN client AS T2
  ON T1.district_id = T2.district_id
INNER JOIN disp AS T3
  ON T2.client_id = T3.client_id
WHERE T2.gender = 'F'
  AND T3.type = 'OWNER'
GROUP BY T1.A2
ORDER BY COUNT(T2.client_id) DESC
LIMIT 9;
```
comparator: result sets differ

### `129` · financial · moderate · _wrong_answer_ · tags: distinct_mismatch, projection_count_mismatch

**Q:** Which are the top ten withdrawals (non-credit card) by district names for the month of January 1996?

```sql
-- gold
SELECT DISTINCT T1.A2 FROM district AS T1 INNER JOIN account AS T2 ON T1.district_id = T2.district_id INNER JOIN trans AS T3 ON T2.account_id = T3.account_id WHERE T3.type = 'VYDAJ' AND T3.date LIKE '1996-01%' ORDER BY A2 ASC LIMIT 10
-- candidate
SELECT 
  t.trans_id,
  d.A2 AS district_name,
  t.amount
FROM trans t
JOIN account a ON t.account_id = a.account_id
JOIN district d ON a.district_id = d.district_id
WHERE t.type = 'VYDAJ'
  AND t.date LIKE '1996-01%'
ORDER BY t.amount DESC
LIMIT 10;
```
comparator: result sets differ

### `138` · financial · moderate · _execution_error_final_ · tags: table_mismatch, extra_table, join_mismatch, distinct_mismatch

**Q:** In the branch where the second-highest number of crimes were committed in 1995 occurred, how many male clients are there?

```sql
-- gold
SELECT COUNT(T1.client_id) FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T1.gender = 'M' AND T2.A15 = (SELECT T3.A15 FROM district AS T3 ORDER BY T3.A15 DESC LIMIT 1, 1)
-- candidate
SELECT count(DISTINCT c.client_id)
FROM client AS c
JOIN disp AS d ON c.client_id = d.client_id
JOIN account AS a ON d.account_id = a.account_id
WHERE c.gender = 'M' 
  AND a.district_id = (
    SELECT district_code 
    FROM district 
    ORDER BY A15 DESC 
    LIMIT 1 OFFSET 1
  );
```
comparator: —

### `145` · financial · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, distinct_mismatch

**Q:** Who are the account holder identification numbers whose who have transactions on the credit card with the amount is less than the average, in 1998?

```sql
-- gold
SELECT T1.account_id FROM trans AS T1 INNER JOIN account AS T2 ON T1.account_id = T2.account_id WHERE STRFTIME('%Y', T1.date) = '1998' AND T1.operation = 'VYBER KARTOU' AND T1.amount < (SELECT AVG(amount) FROM trans WHERE STRFTIME('%Y', date) = '1998')
-- candidate
SELECT DISTINCT
  t.account_id
FROM trans AS t
WHERE
  t.operation = 'VYBER KARTOU'
  AND strftime('%Y', t.date) = '1998'
  AND t.amount < (
    SELECT AVG(sub.amount)
    FROM trans AS sub
    WHERE sub.operation = 'VYBER KARTOU' AND strftime('%Y', sub.date) = '1998'
  );
```
comparator: result sets differ

### `149` · financial · challenging · _wrong_answer_ · tags: distinct_mismatch · **BIRD-ok (scorer artifact)**

**Q:** Please list the account types that are not eligible for loans, and the average income of residents in the district where the account is located exceeds $8000 but is no more than $9000.

```sql
-- gold
SELECT T3.type FROM district AS T1 INNER JOIN account AS T2 ON T1.district_id = T2.district_id INNER JOIN disp AS T3 ON T2.account_id = T3.account_id WHERE T3.type != 'OWNER' AND T1.A11 BETWEEN 8000 AND 9000
-- candidate
SELECT DISTINCT disp.type
FROM disp
JOIN account ON disp.account_id = account.account_id
JOIN district ON account.district_id = district.district_id
WHERE disp.type != 'OWNER'
  AND district.A11 > 8000
  AND district.A11 <= 9000;
```
comparator: result sets differ

### `152` · financial · moderate · _wrong_answer_ · tags: distinct_mismatch

**Q:** What is the average number of crimes committed in 1995 in regions where the number exceeds 4000 and the region has accounts that are opened starting from the year 1997?

```sql
-- gold
SELECT AVG(T1.A15) FROM district AS T1 INNER JOIN account AS T2 ON T1.district_id = T2.district_id WHERE STRFTIME('%Y', T2.date) >= '1997' AND T1.A15 > 4000
-- candidate
SELECT AVG(d.A15)
FROM (
    SELECT DISTINCT district_id
    FROM account
    WHERE strftime('%Y', date) >= '1997'
) AS a
JOIN district AS d ON a.district_id = d.district_id
WHERE d.A15 > 4000;
```
comparator: result sets differ

### `159` · financial · simple · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, spurious_join, projection_count_mismatch

**Q:** List all the withdrawals in cash transactions that the client with the id 3356 makes.

```sql
-- gold
SELECT T4.trans_id FROM client AS T1 INNER JOIN disp AS T2 ON T1.client_id = T2.client_id INNER JOIN account AS T3 ON T2.account_id = T3.account_id INNER JOIN trans AS T4 ON T3.account_id = T4.account_id WHERE T1.client_id = 3356 AND T4.operation = 'VYBER'
-- candidate
SELECT
  t.trans_id,
  t.account_id,
  t.date,
  t.type,
  t.operation,
  t.amount,
  t.balance,
  t.k_symbol,
  t.bank,
  t.account
FROM trans AS t
INNER JOIN disp AS d ON t.account_id = d.account_id
WHERE d.client_id = 3356
  AND t.operation = 'VYBER';
```
comparator: result sets differ

### `168` · financial · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, spurious_join

**Q:** What percentage of clients who opened their accounts in the district with an average salary of over 10000 are women?

```sql
-- gold
SELECT CAST(SUM(T2.gender = 'F') AS REAL) * 100 / COUNT(T2.client_id) FROM district AS T1 INNER JOIN client AS T2 ON T1.district_id = T2.district_id WHERE T1.A11 > 10000
-- candidate
SELECT 
  (SUM(CASE WHEN t2.gender = 'F' THEN 1 ELSE 0 END) * 100.0) / COUNT(*) AS percentage_female
FROM account t1
JOIN client t2 ON t1.account_id = t2.client_id
JOIN district t3 ON t1.district_id = t3.district_id
WHERE t3.A11 > 10000;
```
comparator: result sets differ

### `169` · financial · challenging · _wrong_answer_ · tags: shape_matches_value_level

**Q:** What was the growth rate of the total amount of loans across all accounts for a male client between 1996 and 1997?

```sql
-- gold
SELECT CAST((SUM(CASE WHEN STRFTIME('%Y', T1.date) = '1997' THEN T1.amount ELSE 0 END) - SUM(CASE WHEN STRFTIME('%Y', T1.date) = '1996' THEN T1.amount ELSE 0 END)) AS REAL) * 100 / SUM(CASE WHEN STRFTIME('%Y', T1.date) = '1996' THEN T1.amount ELSE 0 END) FROM loan AS T1 INNER JOIN account AS T2 ON T1.account_id = T2.account_id INNER JOIN disp AS T3 ON T3.account_id = T2.account_id INNER JOIN client AS T4 ON T4.client_id = T3.client_id WHERE T4.gender = 'M' AND T3.type = 'OWNER'
-- candidate
SELECT 
  (
    (SUM(CASE WHEN strftime('%Y', l.date) = '1997' THEN l.amount ELSE 0 END) 
     - SUM(CASE WHEN strftime('%Y', l.date) = '1996' THEN l.amount ELSE 0 END))
    * 100.0 
    / SUM(CASE WHEN strftime('%Y', l.date) = '1996' THEN l.amount ELSE 0 END)
  ) AS loan_growth_rate
FROM loan l
JOIN account a ON l.account_id = a.account_id
JOIN disp d ON a.account_id = d.account_id
JOIN client c ON d.client_id = c.client_id
WHERE c.gender = 'M';
```
comparator: result sets differ

### `173` · financial · challenging · _wrong_answer_ · tags: table_mismatch, missing_table, extra_table, join_mismatch, projection_count_mismatch

**Q:** How often does account number 3 request an account statement to be released? What was the aim of debiting 3539 in total?

```sql
-- gold
SELECT T1.frequency, T2.k_symbol FROM account AS T1 INNER JOIN (SELECT account_id, k_symbol, SUM(amount) AS total_amount FROM `order` GROUP BY account_id, k_symbol) AS T2 ON T1.account_id = T2.account_id WHERE T1.account_id = 3 AND T2.total_amount = 3539
-- candidate
SELECT 
  (SELECT frequency FROM account WHERE account_id = 3) AS statement_frequency,
  k_symbol AS payment_purpose,
  SUM(amount) AS total_debited_amount
FROM trans
WHERE account_id = 3 AND type = 'VYDAJ'
GROUP BY k_symbol
HAVING total_debited_amount = 3539;
```
comparator: result sets differ

### `186` · financial · moderate · _wrong_answer_ · tags: table_mismatch, missing_table, join_mismatch, aggregate_mismatch

**Q:** What percentage of male clients request for weekly statements to be issued?

```sql
-- gold
SELECT CAST(SUM(T1.gender = 'M') AS REAL) * 100 / COUNT(T1.client_id) FROM client AS T1 INNER JOIN district AS T3 ON T1.district_id = T3.district_id INNER JOIN account AS T2 ON T2.district_id = T3.district_id INNER JOIN disp as T4 on T1.client_id = T4.client_id AND T2.account_id = T4.account_id WHERE T2.frequency = 'POPLATEK TYDNE'
-- candidate
SELECT (CAST(COUNT(CASE WHEN client.gender = 'M' THEN 1 END) AS REAL) / COUNT(*)) * 100.0 AS percentage
FROM client
JOIN disp ON client.client_id = disp.client_id
JOIN account ON disp.account_id = account.account_id
WHERE account.frequency = 'POPLATEK TYDNE';
```
comparator: result sets differ

### `120` · financial · moderate · _wrong_answer_ · tags: table_mismatch, extra_table, join_mismatch, distinct_mismatch, projection_count_mismatch

**Q:** From Year 1995 to 2000, who are the accounts holders from 'east Bohemia'. State the account ID the frequency of statement issuance.

```sql
-- gold
SELECT T1.account_id, T1.frequency FROM account AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id WHERE T2.A3 = 'east Bohemia' AND STRFTIME('%Y', T1.date) BETWEEN '1995' AND '2000'
-- candidate
SELECT DISTINCT
  client.client_id,
  account.account_id,
  account.frequency
FROM account
JOIN disp ON account.account_id = disp.account_id
JOIN client ON disp.client_id = client.client_id
JOIN district ON client.district_id = district.district_id
WHERE disp.type = 'OWNER'
  AND district.A3 = 'east Bohemia'
  AND account.date BETWEEN '1995-01-01' AND '2000-12-31';
```
comparator: result sets differ

