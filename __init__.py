# -*- coding: utf-8 -*-

import os
import urlparse
import posixpath
import re

from functools import wraps

from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash, _app_ctx_stack, jsonify
from flask.ext.login import LoginManager, current_user, login_required, \
     login_user, logout_user, UserMixin, confirm_login, fresh_login_required

from dropbox.client import DropboxClient, DropboxOAuth2Flow
from dropbox.rest import ErrorResponse


app = Flask(__name__)
app.config.from_pyfile('config.cfg')

login_manager = LoginManager()
login_manager.init_app(app)

# Set up useful app paths
currentpath = os.path.dirname(os.path.abspath(__file__))
parentpath = os.path.abspath(os.path.join(currentpath, os.pardir))
dbpath = os.path.join(parentpath, "db")

# How many thumbs to show per page
pagesize = 25

# Ensure db directory exists
try:
    os.makedirs(dbpath)
except OSError:
    pass


class User(UserMixin):
    """User class based on Flask-Login UserMixin"""
    def __init__(self, id):
        self.id = id


@login_manager.user_loader
def load_user(userid):
    """Callback to load user from db, called by Flask-Login"""
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", [userid]).fetchone()
    if user is not None:
        return User(user[0])
    return None


@login_manager.unauthorized_handler
def unauthorized():
    """Tell Flask-Login what to do if an unauthorised user_id
    attempts to access a method decorated with @login_required"""
    return redirect(get_auth_flow().start())


def init_db():
    """Create the database tables"""
    with app.app_context():
        db = get_db()
        with app.open_resource("schema.sql", mode="r") as f:
            db.cursor().executescript(f.read())
        db.commit()


def get_db():
    """Open a new database connection if there is none yet
    for the current application context"""
    top = _app_ctx_stack.top
    if not hasattr(top, "sqlite_db"):
        sqlite_db = sqlite3.connect(os.path.join(dbpath, app.config["DATABASE"]))
        sqlite_db.row_factory = sqlite3.Row
        top.sqlite_db = sqlite_db
    return top.sqlite_db


def get_auth_flow():
    """Shortcut function which returns Dropbox auth flow helper"""
    redirect_uri = url_for("dropbox_auth_finish", _external=True)
    return DropboxOAuth2Flow(app.config["DROPBOX_APP_KEY"], 
                             app.config["DROPBOX_APP_SECRET"], 
                             redirect_uri,
                             session, # TODO: What is this now?
                             "dropbox-auth-csrf-token")


def update_db_access_token(db, user_id, access_token):
    db.execute("UPDATE users SET access_token = ? WHERE id = ?", [user_id, access_token])
    db.commit()


def get_db_access_token(db, user_id):
    """Get the OAuth access token for the specified user"""
    row = db.execute("SELECT access_token FROM users WHERE id = ?", [user_id]).fetchone()
    return None if row is None else row[0]


def get_db_images(db, user_id, pagesize, page):
    """Get a user's image records from the db, with paging"""
    sql = """
          SELECT 
              id, 
              path, 
              sharekey, 
              date_added, 
              description,
              tags,
              (SELECT COUNT(id) FROM images where user_id = ?) as total_records
          FROM
              images
          WHERE
              user_id = ?
          AND
              id NOT IN (
                  SELECT
                      id FROM images
                  ORDER BY
                      date_added DESC
                  LIMIT
                      ? -- Start at
              )
          ORDER BY
              date_added DESC
          LIMIT
              ? -- Page Size
          """
    start_at = (page - 1) * pagesize
    cursor = db.cursor()
    rows = cursor.execute(sql, [user_id, user_id, start_at, pagesize]).fetchall()
    cols = [d[0] for d in cursor.description]
    dict_rows = []
    for row in rows:
        dict_rows.append(dict(zip(cols, row)))
    return dict_rows


def get_db_tags(db, user_id):
    """Get a user's tags from the db"""
    return db.execute("SELECT tag FROM tags WHERE user_id = ?", [user_id]).fetchall()


@app.route("/")
@login_required
def home():
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        # Show page 1 if no page query string is supplied
        page = int(request.args.get("page", 1))

        return render_template("index.html", user_id=current_user.id, 
                                             page=page)
    else:
        return redirect(get_auth_flow().start())    

@app.route("/load")
def load():
    if not current_user.is_authenticated():
        abort(403)
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        # Show page 1 if no page query string is supplied
        page = int(request.args.get("page", 1))
        # Now fetch the images from the DB and pass them to the view
        dbimages = get_db_images(db, current_user.id, pagesize, page)

        total_files = dbimages[0]["total_records"] if len(dbimages) is not 0 else 0
        total_pages = total_files / pagesize
        if total_files % pagesize is not 0:
            total_pages += 1

        # Get the tags for this user so we can set up autocompletion
        tags = get_db_tags(db, current_user.id)
        tagstring = ",".join(["'" + tag[0] + "'" for tag in tags])

        return jsonify({ "images": dbimages, 
                         "page": page, 
                         "total_pages": total_pages, 
                         "total_files": total_files, 
                         "tagstring": tagstring })
    else:
        abort(403) 


@app.route("/sync")
def sync():
    if not current_user.is_authenticated():
        abort(403)
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        client = DropboxClient(access_token)
        # Get the previous delta cursor hash (if present) so we only pull
        # down changes which occurred since the last time we updated
        old_cursor = db.execute("SELECT delta_cursor FROM users WHERE id = ?", [current_user.id]).fetchone()
        delta = client.delta() if old_cursor[0] is None else client.delta(old_cursor[0])
        # The first time we retrieve the delta it will consist of a single entry for 
        # the /Images sub folder of our app folder, so ignore this if present
        files = [item for item in delta["entries"] if item[0] != "/images"]
        added_files = 0
        deleted_files = 0
        for f in files:
            # The delta API call returns a list of two-element lists
            # Element 0 is the lowercased file path, element 1 is the file metadata
            fpath = f[0]
            filename = os.path.basename(fpath)
            # If the metadata is empty, it means the file/folder has been deleted
            if f[1] is None:
                # Delete the file
                db.execute("DELETE FROM images WHERE path = ? and user_id = ?", [filename, current_user.id])
                db.commit()
                # TODO: Delete the local thumbnail for the image which was removed
                deleted_files += 1
            else:
                # Get the publically accessible share URL for this file
                share = client.share(fpath, short_url=False)
                parts = urlparse.urlparse(share["url"])
                # We store the share key/hash separately from the file path in
                # case it expires and we need to re-retrieve the share later
                sharekey = parts.path.split("/")[2]
                # Insert or update the file
                imageid = "0"
                existing = db.execute("SELECT id FROM images WHERE path = ?", [filename]).fetchone()
                if existing is None:
                    cursor = db.cursor()
                    cursor.execute("INSERT INTO images (sharekey, path, user_id) VALUES (?, ?, ?)", [sharekey, filename, current_user.id])
                    db.commit()
                    imageid = str(cursor.lastrowid)
                else:
                    imageid = str(existing[0])
                # Grab the thumbnail from Dropbox and save it *locally*, 
                # using the id of the image record we've just inserted
                thumbfile = open(os.path.join(currentpath, "static", "img", "thumbs", imageid + ".jpg"), "wb")
                thumb = client.thumbnail(fpath, size="m", format="JPEG")
                thumbfile.write(thumb.read())         
                added_files += 1       

        # Update the cursor hash stored against the user so we can retrieve
        # a delta of just the changes from this point onward next time we update
        db.execute("UPDATE users SET delta_cursor = ? WHERE id = ?", [delta["cursor"], current_user.id])
        db.commit()

        
        # Now fetch the images from the DB and pass them to the view
        # TODO: Need method to just get record count for user rather than retrieving all data
        dbimages = get_db_images(db, current_user.id, pagesize, 1)

        total_files = dbimages[0]["total_records"] if len(dbimages) is not 0 else 0
        total_pages = total_files / pagesize
        if total_files % pagesize is not 0:
            total_pages += 1

        return jsonify({ "added": added_files, 
                         "deleted": deleted_files, 
                         "total_files": total_files, 
                         "total_pages": total_pages })
    else:
        abort(403) 


@app.route("/save", methods=['POST'])
def save():
    if not current_user.is_authenticated():
        abort(403)
    db = get_db()
    image_id = request.form["imgid"]
    tag_sql = "SELECT tag, id FROM tags WHERE user_id = ?"
    # Get a dictionary of all this user's tags, with tag as key and id as value
    dbtags = { k : v for k, v in db.execute(tag_sql, [current_user.id]).fetchall() }
    # Get a list of the posted tags and the image description
    tags = [tag.strip() for tag in request.form["tags"].split("|")]
    description = request.form["description"]
    page = request.form["page"]
    # Delete all the tag joins for this image
    db.execute("DELETE FROM tags_images WHERE image_id = ?", [image_id])
    # Only return newly added tags
    newtags = []
    # Loop through all the posted tags
    for tag in tags:
        # If a tag isn't already in the db
        if tag not in dbtags:
            cursor = db.cursor()
            cursor.execute("INSERT INTO tags (tag, user_id) VALUES (?, ?)", [tag, current_user.id])
            db.commit();
            # Add the new tag and id to the dbtags dict so we don't have to query for it again
            dbtags[tag] = cursor.lastrowid;
            newtags.append(tag)
        # Insert a join record for this tag/image
        db.execute("INSERT INTO tags_images (tag_id, image_id) VALUES (?, ?)", [dbtags[tag], image_id])
        db.commit();
    # Update the flattened tags field of the image record, for convenience
    db.execute("UPDATE images SET description = ?, tags = ? WHERE id = ?", [description, "|".join(tags), image_id])
    db.commit();
    # return redirect(url_for("home", page=page))
    return jsonify({ "newtags": newtags })


@app.route("/image/<int:id>")
@login_required
def image(id):
    db = get_db()
    row = db.execute("SELECT id, path, sharekey FROM images WHERE id = ? AND user_id = ?", [id, current_user.id]).fetchone()
    return render_template("image.html", image=row)


@app.route("/dropbox-auth-finish")
def dropbox_auth_finish():
    # TODO: Should we log them in before redirecting here?
    # if not current_user.is_authenticated():
    #    abort(403)
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
    # Check for user
    user = load_user(user_id)
    if user is None:
        db.execute("INSERT INTO users (access_token, id) VALUES (?, ?)", [access_token, user_id])
        db.commit()
        user = load_user(user_id)
    else:
        update_db_access_token(db, user_id, access_token)
    
    login_user(user, remember=True)
    client = DropboxClient(access_token)
    # Create the /Images sub folder in the user's app folder
    try:
        client.file_create_folder("/Images")
    except ErrorResponse:
        print "Folder already exists"
    return redirect(url_for("home"))


@app.route("/dropbox-unlink")
@login_required
def dropbox_unlink():
    db = get_db()
    update_db_access_token(db, current_user.id, None)
    logout_user()
    return redirect(url_for("home"))


def main():
    init_db()
    app.run()


if __name__ == "__main__":
    main()
