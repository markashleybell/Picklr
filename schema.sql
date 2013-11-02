CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    access_token BLOB,
    delta_cursor TEXT
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
    sharekey TEXT UNIQUE NOT NULL,
    path TEXT UNIQUE NOT NULL,
    tags TEXT,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tags_images (
    tag_id INTEGER NOT NULL,
    image_id INTEGER NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES tags(id),
    FOREIGN KEY(image_id) REFERENCES images(id),
    PRIMARY KEY(tag_id, image_id)
);
