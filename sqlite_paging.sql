SELECT
    id, path, sharekey, date_added, tags
FROM
    images
WHERE
    user_id = 100
AND
    id NOT IN (
        SELECT
            id FROM images
        ORDER BY
            date_added DESC
        LIMIT
            15 -- Start at
    )
 ORDER BY
     date_added DESC
 LIMIT
     5 -- Page Size