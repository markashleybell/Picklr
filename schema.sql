CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    access_token BLOB,
    delta_cursor TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
    sharekey TEXT UNIQUE NOT NULL,
    path TEXT UNIQUE NOT NULL,
    description TEXT,
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

CREATE TABLE IF NOT EXISTS tags_files (
    tag_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    FOREIGN KEY(tag_id) REFERENCES tags(id),
    FOREIGN KEY(file_id) REFERENCES files(id),
    PRIMARY KEY(tag_id, file_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delta_cursor TEXT NOT NULL,
    path TEXT NOT NULL,
    type INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);