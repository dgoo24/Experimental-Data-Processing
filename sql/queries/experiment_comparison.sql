-- Descriptive comparison between experiments, based on individual sample fits.
-- This is not a significance test.

SELECT
    e.experiment_id,
    COUNT(DISTINCT rr.sample_id)                 AS n_samples,
    SUM(rr.n_points)                             AS n_points,
    ROUND(AVG(rr.slope)::numeric, 8)             AS mean_slope_deg_per_deg,
    ROUND(STDDEV_SAMP(rr.slope)::numeric, 8)     AS stddev_slope,
    ROUND(AVG(rr.intercept)::numeric, 8)         AS mean_intercept_deg,
    ROUND(AVG(rr.r_squared)::numeric, 8)         AS mean_r_squared
FROM regression_results AS rr
JOIN experiments AS e ON e.id = rr.experiment_id
GROUP BY e.experiment_id
ORDER BY e.experiment_id;
