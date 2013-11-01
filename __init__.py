# -*- coding: utf-8 -*-

import os
import urlparse
import posixpath
import re

from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, _app_ctx_stack

from dropbox.client import DropboxClient, DropboxOAuth2Flow
from dropbox.rest import ErrorResponse

# create our little application :)
app = Flask(__name__)
app.config.from_pyfile('config.cfg')

# Set up useful app paths
currentpath = os.path.dirname(os.path.abspath(__file__))
parentpath = os.path.abspath(os.path.join(currentpath, os.pardir))
dbpath = os.path.join(parentpath, "db")

# Ensure db directory exists
try:
    os.makedirs(dbpath)
except OSError:
    pass


def init_db():
    """Creates the database tables."""
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        db.commit()


def get_db():
    """
    Opens a new database connection if there is none yet for the current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, "sqlite_db"):
        sqlite_db = sqlite3.connect(os.path.join(dbpath, app.config["DATABASE"]))
        sqlite_db.row_factory = sqlite3.Row
        top.sqlite_db = sqlite_db

    return top.sqlite_db


def get_access_token():
    userid = session.get("user_id")
    if userid is None:
        return None
    db = get_db()
    row = db.execute("SELECT access_token FROM users WHERE id = ?", [userid]).fetchone()
    if row is None:
        return None
    return row[0]


def get_user_id():
    userid = session.get("user_id")
    if userid is None:
        return None
    db = get_db()
    row = db.execute("SELECT id FROM users WHERE id = ?", [userid]).fetchone()
    if row is None:
        return None
    return row[0]


def get_db_images(fromid, pagesize):
    userid = session.get("user_id")
    if userid is None:
        return None
    db = get_db()
    # if fromid > 0:
    #     sql += "AND id > ? "
    # if pagesize > 0:
    #     sql += "LIMIT " + pagesize
    rows = db.execute("SELECT id, path, sharekey, date_added FROM images WHERE user_id = ?", [userid]).fetchall()
    if rows is None:
        return None
    return rows


@app.route("/")
def home():
    if "user_id" not in session:
        session["user_id"] = 0
        return redirect(get_auth_flow().start())
    access_token = get_access_token()
    real_name = None
    files = None
    folderdata = None
    dbimageslist = None
    dbimages = None
    if access_token is not None:
        client = DropboxClient(access_token)
        account_info = client.account_info()
        real_name = account_info["display_name"]
        db = get_db()
        userid = get_user_id()
        old_cursor = db.execute("SELECT delta_cursor FROM users WHERE id = ?", [userid]).fetchone()
        delta = client.delta() if old_cursor[0] is None else client.delta(old_cursor[0])
        print delta
        # The first time we retrieve the delta it will consist of a single entry for 
        # the /Images sub folder of our app folder, so ignore this if present
        files = [f[1]["path"] for f in delta["entries"] if f[1]["path"] != "/Images"]

        for path in files:
            filename = os.path.basename(path)
            updates = True
            print "new file in delta, inserting"
            share = client.share(path, short_url=False)
            parts = urlparse.urlparse(share["url"])
            sharekey = parts.path.split("/")[2]
            cursor = db.cursor()
            cursor.execute("INSERT OR IGNORE INTO images (sharekey, path, user_id) VALUES (?, ?, ?)", [sharekey, filename, userid])
            db.commit()
            thumbfile = open(os.path.join(currentpath, "static", "img", "thumbs", str(cursor.lastrowid) + ".jpg"), "wb")
            print path
            thumb = client.thumbnail(path, size="l", format="JPEG")
            thumbfile.write(thumb.read())

        db.execute("UPDATE users SET delta_cursor = ? WHERE id = ?", [delta["cursor"], userid])
        db.commit()

        # Now fetch all the images from the DB
        dbimages = get_db_images(0, 0)

        # share = client.share(files[0], short_url=False)
        # image = re.sub(r"(www\.dropbox\.com)", "dl.dropboxusercontent.com", share["url"])

    return render_template("index.html", user_id=session["user_id"], real_name=real_name, images=dbimages, files=len(dbimages) if dbimages is not None else 0)


@app.route("/import")
def import_images():
    return render_template("index.html")


@app.route("/image/<int:id>")
def image(id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    userid = get_user_id()
    db = get_db()
    row = db.execute("SELECT id, path, sharekey FROM images WHERE id = ? AND user_id = ?", [id, userid]).fetchone()

    return render_template("image.html", image=row)


@app.route("/dropbox-auth-finish")
def dropbox_auth_finish():
    if session.get("user_id") is None:
        abort(403)
    try:
        access_token, user_id, url_state = get_auth_flow().finish(request.args)
    except DropboxOAuth2Flow.BadRequestException, e:
        abort(400)
    except DropboxOAuth2Flow.BadStateException, e:
        abort(400)
    except DropboxOAuth2Flow.CsrfException, e:
        abort(403)
    except DropboxOAuth2Flow.NotApprovedException, e:
        flash("Not approved?  Why not, bro?")
        return redirect(url_for("home"))
    except DropboxOAuth2Flow.ProviderException, e:
        app.logger.exception("Auth error" + e)
        abort(403)
    db = get_db()
    data = [access_token, user_id]
    # Check for user
    existing = db.execute("SELECT id FROM users WHERE id = ?", [user_id]).fetchone()
    if existing is None:
        db.execute("INSERT INTO users (access_token, id) VALUES (?, ?)", data)
    else:
        db.execute("UPDATE users SET access_token = ? WHERE id = ?", data)
    db.commit()

    session["user_id"] = user_id
    client = DropboxClient(access_token)
    try:
        client.file_create_folder("/Images")
    except ErrorResponse:
        print "Folder already exists"
    return redirect(url_for("home"))


@app.route("/dropbox-unlink")
def dropbox_unlink():
    userid = session.get("user_id")
    if userid is None:
        abort(403)
    db = get_db()
    db.execute("UPDATE users SET access_token = NULL WHERE id = ?", [userid])
    db.commit()
    return redirect(url_for("home"))


def get_auth_flow():
    redirect_uri = url_for("dropbox_auth_finish", _external=True)
    return DropboxOAuth2Flow(app.config["DROPBOX_APP_KEY"], app.config["DROPBOX_APP_SECRET"], redirect_uri,
                                       session, "dropbox-auth-csrf-token")


def main():
    init_db()
    app.run()


if __name__ == "__main__":
    main()
