-- Measurements for one experiment.
-- Run with a bind parameter, for example:
--   psql ... -v experiment_id=EXP-001 -f sql/queries/measurements_by_experiment.sql
-- psql variable syntax below uses :'experiment_id'.

SELECT
    e.experiment_id,
    s.sample_id,
    pm.measurement_angle,
    pm.observed_rotation,
    pm.measurement_timestamp
FROM processed_measurements AS pm
JOIN experiments AS e ON e.id = pm.experiment_id
JOIN samples AS s ON s.id = pm.sample_id
WHERE e.experiment_id = :'experiment_id'
ORDER BY s.sample_id, pm.measurement_timestamp, pm.measurement_angle;
