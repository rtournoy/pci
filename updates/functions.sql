CREATE OR REPLACE FUNCTION convert_duration_to_sql_interval(d duration)
RETURNS INTERVAL AS $$
DECLARE sql_interval INTERVAL;
BEGIN
    sql_interval :=
    CASE d
        WHEN 'Two weeks' THEN '2 weeks'
        WHEN 'Three weeks' THEN '3 weeks'
        WHEN 'Four weeks' THEN '4 weeks'
        WHEN 'Five weeks' THEN '5 weeks'
        WHEN 'Six weeks' THEN '6 weeks'
        WHEN 'Seven weeks' THEN '7 weeks'
        WHEN 'Eight weeks' THEN '8 weeks'
        ELSE NULL
    END;
    RETURN sql_interval;
END;
$$ LANGUAGE plpgsql;