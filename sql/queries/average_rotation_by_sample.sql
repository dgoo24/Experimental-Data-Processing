-- Average observed rotation and spread for each experiment/sample.

SELECT
    e.experiment_id,
    s.sample_id,
    COUNT(*)                              AS n_measurements,
    ROUND(AVG(pm.measurement_angle)::numeric, 6)  AS mean_angle_deg,
    ROUND(AVG(pm.observed_rotation)::numeric, 6)  AS mean_rotation_deg,
    ROUND(STDDEV_SAMP(pm.observed_rotation)::numeric, 6) AS stddev_rotation_deg,
    MIN(pm.observed_rotation)             AS min_rotation_deg,
    MAX(pm.observed_rotation)             AS max_rotation_deg
FROM processed_measurements AS pm
JOIN experiments AS e ON e.id = pm.experiment_id
JOIN samples AS s ON s.id = pm.sample_id
GROUP BY e.experiment_id, s.sample_id
ORDER BY e.experiment_id, s.sample_id;
