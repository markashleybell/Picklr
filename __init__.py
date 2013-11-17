# -*- coding: utf-8 -*-

import os
import urlparse
import posixpath
import re
import shutil
import urllib2

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
pagesize = 10

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

def api_login_required(method):
    """Return 403 Unauthorized if user not authed"""
    @wraps(method)
    def f(*args, **kwargs):
        if not current_user.is_authenticated():
            abort(403)
        return method(*args, **kwargs)
    return f


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
    """Update the OAuth access token for the specified user"""
    db.execute("UPDATE users SET access_token = ? WHERE id = ?", [user_id, access_token])
    db.commit()


def get_db_access_token(db, user_id):
    """Get the OAuth access token for the specified user"""
    row = db.execute("SELECT access_token FROM users WHERE id = ?", [user_id]).fetchone()
    return None if row is None else row[0]


def get_db_file_count(db, user_id):
    """Get the total number of files for the specified user"""
    row = db.execute("SELECT COUNT(id) FROM files WHERE user_id = ?", [user_id]).fetchone()
    return None if row is None else row[0]


def get_db_files(db, user_id, pagesize, page, query=None):
    """Get a user's file records from the db, with paging"""
    paging_sql = """
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
                             f3.user_id = ?
                     ) as total_records
                 FROM
                     files f1
                 WHERE
                     f1.user_id = ?
                 AND
                     f1.id NOT IN (
                         SELECT
                             f2.id
                         FROM
                             files f2
                         WHERE
                             f2.user_id = ?
                         ORDER BY
                             f2.date_added DESC
                         LIMIT
                             ? -- Start at
                     )
                 ORDER BY
                     f1.date_added DESC
                 LIMIT
                     ? -- Page Size
                 """

    search_paging_sql = """
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
                                        f3.user_id = ?
                                    AND
                                        m3.tag_id = t3.id
                                    AND
                                        (t3.tag IN ({0}))
                                    AND
                                        f3.id = m3.file_id
                                    GROUP BY
                                        f3.id
                                    HAVING
                                        COUNT(f3.id) = {1}
                                )
                          ) as total_records
                        FROM
                            files f1, tags_files m1, tags t1
                        WHERE
                            f1.user_id = ?
                        AND
                            m1.tag_id = t1.id
                        AND
                            (t1.tag IN ({0}))
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
                                    f2.user_id = ?
                                AND
                                    m2.tag_id = t2.id
                                AND
                                    (t2.tag IN ({0}))
                                AND
                                    f2.id = m2.file_id
                                GROUP BY
                                    f2.id
                                HAVING
                                    COUNT(f2.id) = {1}
                                ORDER BY
                                    f2.date_added DESC
                                LIMIT
                                    ? -- Start at
                            )
                        GROUP BY
                            f1.id
                        HAVING
                            COUNT(f1.id) = {1}
                        ORDER BY
                            f1.date_added DESC
                        LIMIT
                            ? -- Page Size
                        """

    start_at = (page - 1) * pagesize
    cursor = db.cursor()

    if query is None:
        sql = paging_sql
        params = [user_id, user_id, user_id, start_at, pagesize]
    else:
        # Try and tidy up the tag query terms a bit
        query_terms = [s.lower().strip() for s in query.split('|') if s.strip() is not '']
        # Create parameter placeholders for IN clauses
        in_list = ','.join('?' for s in query_terms)
        # Subsitute the placeholders in the SQL string with the correct values
        sql = search_paging_sql.format(in_list, len(query_terms))
        # Slightly unwieldy, but safe way of supplying the param list
        params = [user_id]
        params.extend(query_terms)
        params.append(user_id)
        params.extend(query_terms)
        params.append(user_id)
        params.extend(query_terms)
        params.append(start_at)
        params.append(pagesize)

    # Get all results and return them as a dictionary with column names as keys
    rows = cursor.execute(sql, params).fetchall()
    cols = [d[0] for d in cursor.description]
    dict_rows = []
    for row in rows:
        dict_rows.append(dict(zip(cols, row)))
    return dict_rows


def get_db_tags(db, user_id):
    """Get a user's tags from the db"""
    return db.execute("SELECT tag FROM tags WHERE user_id = ?", [user_id]).fetchall()


@app.route("/")
@app.route("/<int:page>")
@login_required
def page(page=None):
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        return render_template("page.html", user_id=current_user.id, 
                                            page=page or 1)
    else:
        return redirect(get_auth_flow().start())    


@app.route("/load/<int:page>")
@api_login_required
def load(page):
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        # Now fetch the files from the DB and pass them to the view
        query = request.args.get('query')
        dbfiles = get_db_files(db, current_user.id, pagesize, page, query)

        # Get paging info
        total_files = dbfiles[0]["total_records"] if len(dbfiles) is not 0 else 0
        total_pages = total_files / pagesize
        if total_files % pagesize is not 0:
            total_pages += 1

        # Get the tags for this user so we can set up autocompletion
        tags = get_db_tags(db, current_user.id)
        tagstring = "|".join([tag[0] for tag in tags])
        
        # URLencode all the filenames which will get written out as data attributes
        # TODO: Is there a tidier way to do this?
        for f in dbfiles:
            f['path'] = urllib2.quote(f['path'].encode("utf8"))

        return jsonify({ "files": dbfiles, 
                         "page": page, 
                         "total_pages": total_pages, 
                         "total_files": total_files, 
                         "tags": tagstring })
    else:
        abort(403) 


@app.route("/sync")
@api_login_required
def sync():
    db = get_db()
    access_token = get_db_access_token(db, current_user.id)
    if access_token is not None:
        client = DropboxClient(access_token)
        # Get the previous delta cursor hash (if present) so we only pull
        # down changes which occurred since the last time we updated
        old_cursor = db.execute("SELECT delta_cursor FROM users WHERE id = ?", [current_user.id]).fetchone()
        delta = client.delta() if old_cursor[0] is None else client.delta(old_cursor[0])
        # The first time we retrieve the delta it will consist of a single entry for 
        # the /Files sub folder of our app folder, so ignore this if present
        files = [item for item in delta["entries"] if item[0] != "/files"]
        added_files = 0
        deleted_files = 0
        for f in files:
            # The delta API call returns a list of two-element lists
            # Element 0 is the *lowercased* file path, element 1 is the file metadata
            fpath = f[0]
            filename = os.path.basename(fpath)
            # If the metadata is empty, it means the file/folder has been deleted
            if f[1] is None:
                # Delete the file
                thumb_id = db.execute("SELECT id FROM files WHERE path = ? and user_id = ?", [filename, current_user.id]).fetchone()
                if thumb_id is not None:
                    db.execute("DELETE FROM files WHERE id = ? and user_id = ?", [thumb_id[0], current_user.id])
                    db.commit()
                    # Delete the local thumbnail file
                    os.remove(os.path.join(currentpath, "static", "img", "thumbs", str(thumb_id[0]) + ".jpg"))
                    deleted_files += 1
            else:
                # Get the publically accessible share URL for this file
                share = client.share(fpath, short_url=False)
                parts = urlparse.urlparse(share["url"])
                # We store the share key/hash separately from the file path in
                # case it expires and we need to re-retrieve the share later
                sharekey = parts.path.split("/")[2]
                # Insert or update the file
                fileid = "0"
                existing = db.execute("SELECT id FROM files WHERE path = ?", [filename]).fetchone()
                if existing is None:
                    cursor = db.cursor()
                    cursor.execute("INSERT INTO files (sharekey, path, user_id) VALUES (?, ?, ?)", [sharekey, filename, current_user.id])
                    db.commit()
                    fileid = str(cursor.lastrowid)
                else:
                    fileid = str(existing[0])
                thumbpath = os.path.join(currentpath, "static", "img", "thumbs", fileid + ".jpg")
                try:
                    # Grab the thumbnail from Dropbox and save it *locally*, 
                    # using the id of the file record we've just inserted
                    thumbfile = open(thumbpath, "wb")
                    thumb = client.thumbnail(fpath, size="m", format="JPEG")
                    thumbfile.write(thumb.read())         
                except ErrorResponse:
                    # Copy a placeholder file over
                    error_thumb = os.path.join(currentpath, "static", "img", "thumb-error.jpg")
                    shutil.copyfile(error_thumb, thumbpath)
                added_files += 1       

        # Update the cursor hash stored against the user so we can retrieve
        # a delta of just the changes from this point onward next time we update
        db.execute("UPDATE users SET delta_cursor = ? WHERE id = ?", [delta["cursor"], current_user.id])
        db.commit()

        # Get paging info
        total_files = get_db_file_count(db, current_user.id)
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
@api_login_required
def save():
    db = get_db()
    file_id = request.form["fileid"]
    tag_sql = "SELECT tag, id FROM tags WHERE user_id = ?"
    # Get a dictionary of all this user's tags, with tag as key and id as value
    dbtags = { k : v for k, v in db.execute(tag_sql, [current_user.id]).fetchall() }
    # Get a list of the posted tags and the file description
    tags = [tag.strip() for tag in request.form["tags"].split("|")]
    description = request.form["description"]
    page = request.form["page"]
    # Delete all the tag joins for this file
    db.execute("DELETE FROM tags_files WHERE file_id = ?", [file_id])
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
        # Insert a join record for this tag/file
        db.execute("INSERT INTO tags_files (tag_id, file_id) VALUES (?, ?)", [dbtags[tag], file_id])
        db.commit();
    # Update the flattened tags field of the file record, for convenience
    db.execute("UPDATE files SET description = ?, tags = ? WHERE id = ?", [description, "|".join(tags), file_id])
    db.commit();
    # Only return the newly added tags to add to the client-side 
    # autocompletion array (others will already be present)
    return jsonify({ "newtags": newtags })


@app.route("/file/<int:id>")
@login_required
def viewer(id):
    db = get_db()
    row = db.execute("SELECT id, path, sharekey FROM files WHERE id = ? AND user_id = ?", [id, current_user.id]).fetchone()
    return render_template("viewer.html", file=row)


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
        return redirect(url_for("page"))
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
    # Create the /Files sub folder in the user's app folder
    try:
        client.file_create_folder("/Files")
    except ErrorResponse:
        print "Folder already exists"
    return redirect(url_for("page"))


@app.route("/dropbox-unlink")
@login_required
def dropbox_unlink():
    db = get_db()
    update_db_access_token(db, current_user.id, None)
    logout_user()
    return redirect(url_for("page"))


def main():
    init_db()
    app.run()


if __name__ == "__main__":
    main()
