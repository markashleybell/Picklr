-- Tag Search
SELECT
    f1.id,
    f1.path,
    f1.sharekey,
    f1.date_added,
    f1.description,
    f1.tags,
    (
        SELECT 
            COUNT(*) 
        FROM (
            SELECT
                f3.sharekey
            FROM
                files f3, 
                tags_files m3, 
                tags t3
            WHERE
                f3.user_id = XXXXX
            AND
                m3.tag_id = t3.id
            AND
                (t3.tag IN ('architecture', 'photography'))
            AND
                f3.id = m3.file_id
            GROUP BY
                f3.id
            HAVING
                COUNT(f3.id) = 2
        )
    ) as total_records
FROM
    files f1,
    tags_files m1,
    tags t1
WHERE
    f1.user_id = XXXXX
AND
    m1.tag_id = t1.id
AND
    (t1.tag IN ('architecture', 'photography'))
AND
    f1.id = m1.file_id
AND
    f1.id NOT IN (
        SELECT
            f2.id
        FROM
            files f2, 
            tags_files m2, 
            tags t2
        WHERE
            f2.user_id = XXXXX
        AND
            m2.tag_id = t2.id
        AND
            (t2.tag IN ('architecture', 'photography'))
        AND
            f2.id = m2.file_id
        GROUP BY
            f2.id
        HAVING
            COUNT(f2.id) = 2
        ORDER BY
            f2.date_added DESC
        LIMIT
            0 -- Start at
    )
GROUP BY
    f1.id
HAVING
    COUNT(f1.id) = 2
ORDER BY
    f1.date_added DESC
LIMIT
    2 -- Page Size


-- Standard Paging
SELECT
    f1.id,
    f1.path,
    f1.sharekey,
    f1.date_added,
    f1.description,
    f1.tags,
    (
        SELECT
            COUNT(*)
        FROM
            files f3
        WHERE
            f3.user_id = XXXXX
    ) as total_records
FROM
    files f1
WHERE
    f1.user_id = XXXXX
AND
    f1.id NOT IN (
        SELECT
            f2.id
        FROM
            files f2
        WHERE
            f2.user_id = XXXXX
        ORDER BY
            f2.date_added DESC
        LIMIT
            0 -- Start at
    )
ORDER BY
    f1.date_added DESC
LIMIT
    2 -- Page Size