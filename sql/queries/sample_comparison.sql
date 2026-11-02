-- Compare samples using their fitted slope, intercept and fit quality.

SELECT
    e.experiment_id,
    s.sample_id,
    rr.n_points,
    ROUND(rr.slope::numeric, 8)     AS slope_deg_per_deg,
    ROUND(rr.intercept::numeric, 8) AS intercept_deg,
    ROUND(rr.r_squared::numeric, 8) AS r_squared,
    ROUND(rr.residual_std_error::numeric, 8) AS residual_std_error_deg
FROM regression_results AS rr
JOIN experiments AS e ON e.id = rr.experiment_id
JOIN samples AS s ON s.id = rr.sample_id
ORDER BY rr.slope DESC, e.experiment_id, s.sample_id;
