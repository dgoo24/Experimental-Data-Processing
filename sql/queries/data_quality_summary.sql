-- Data-quality summary for every imported file.

SELECT
    i.source_file,
    i.imported_at,
    i.n_rows,
    i.n_valid,
    i.n_invalid,
    i.n_duplicates,
    COUNT(*) FILTER (WHERE rm.status = 'invalid')   AS stored_invalid_rows,
    COUNT(*) FILTER (WHERE rm.status = 'duplicate') AS stored_duplicate_rows,
    COUNT(*) FILTER (WHERE rm.status = 'valid')     AS stored_valid_rows
FROM imports AS i
LEFT JOIN raw_measurements AS rm ON rm.import_id = i.id
GROUP BY i.id, i.source_file, i.imported_at, i.n_rows, i.n_valid, i.n_invalid, i.n_duplicates
ORDER BY i.imported_at DESC;
