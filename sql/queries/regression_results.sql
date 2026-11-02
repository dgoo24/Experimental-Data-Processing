-- Latest stored regression result for every experiment/sample.

SELECT
    e.experiment_id,
    s.sample_id,
    rr.n_points,
    rr.slope,
    rr.intercept,
    rr.r_squared,
    rr.slope_std_error,
    rr.intercept_std_error,
    rr.residual_std_error,
    rr.computed_at
FROM regression_results AS rr
JOIN experiments AS e ON e.id = rr.experiment_id
JOIN samples AS s ON s.id = rr.sample_id
ORDER BY e.experiment_id, s.sample_id;
