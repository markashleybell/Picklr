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
    if not hasattr(top, 'sqlite_db'):
        sqlite_db = sqlite3.connect(os.path.join(dbpath, app.config['DATABASE']))
        sqlite_db.row_factory = sqlite3.Row
        top.sqlite_db = sqlite_db

    return top.sqlite_db

def get_access_token():
    username = session.get('user')
    if username is None:
        return None
    db = get_db()
    row = db.execute('SELECT access_token FROM users WHERE username = ?', [username]).fetchone()
    if row is None:
        return None
    return row[0]

def get_user_id():
    username = session.get('user')
    if username is None:
        return None
    db = get_db()
    row = db.execute('SELECT id FROM users WHERE username = ?', [username]).fetchone()
    if row is None:
        return None
    return row[0]

def get_db_images():
    username = session.get('user')
    if username is None:
        return None
    db = get_db()
    userid = db.execute('SELECT id FROM users WHERE username = ?', [username]).fetchone()
    if userid is None:
        return None
    rows = db.execute('SELECT id, path, sharekey FROM images WHERE user_id = ?', [userid[0]]).fetchall()
    if rows is None:
        return None
    return rows

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    access_token = get_access_token()
    real_name = None
    files = None
    folderdata = None
    dbimageslist = None
    dbimages = None
    # print(access_token)
    if access_token is not None:
        client = DropboxClient(access_token)
        account_info = client.account_info()
        real_name = account_info["display_name"]
        folderdata = client.metadata('/Images', list=True, file_limit=25000, hash=None, rev=None, include_deleted=False)
        files = [f['path'] for f in folderdata['contents']]
        dbimages = get_db_images()
        userid = get_user_id()
        dbimageslist = [item[1] for item in dbimages]
        # print dbimageslist
        db = get_db()
        updates = False
        for path in files:
            filename = os.path.basename(path)
            # print path
            # print filename
            #print (filename,)
            #print (filename,) in dbimages # WHY IS THIS FALSE???
            #if (filename,) not in dbimages:
            if filename not in dbimageslist:
                updates = True
                print 'not in db, inserting'
                share = client.share(path, short_url=False)
                parts = urlparse.urlparse(share['url'])
                sharekey = parts.path.split('/')[2]
                cursor = db.cursor()
                cursor.execute('INSERT OR IGNORE INTO images (sharekey, path, user_id) VALUES (?, ?, ?)', [sharekey, filename, userid])
                db.commit()
                thumbfile = open(os.path.join(currentpath, 'static', 'img', 'thumbs', str(cursor.lastrowid) + '.jpg'), "wb")
                thumb = client.thumbnail(path, size='l', format='JPEG')
                thumbfile.write(thumb.read())

        # If new images have been added, re-fetch the images from the database
        if updates:
            dbimages = get_db_images()

        # share = client.share(files[0], short_url=False)
        # image = re.sub(r"(www\.dropbox\.com)", "dl.dropboxusercontent.com", share['url'])

    return render_template('index.html', real_name=real_name, images=dbimages)

@app.route('/image/<int:id>')
def image(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    userid = get_user_id()
    db = get_db()
    row = db.execute('SELECT id, path, sharekey FROM images WHERE id = ? AND user_id = ?', [id, userid]).fetchone()

    return render_template('image.html', image=row)

@app.route('/dropbox-auth-finish')
def dropbox_auth_finish():
    username = session.get('user')
    if username is None:
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
        flash('Not approved?  Why not, bro?')
        return redirect(url_for('home'))
    except DropboxOAuth2Flow.ProviderException, e:
        app.logger.exception("Auth error" + e)
        abort(403)
    db = get_db()
    data = [access_token, username]
    db.execute('UPDATE users SET access_token = ? WHERE username = ?', data)
    db.commit()
    client = DropboxClient(access_token)
    try:
        client.file_create_folder('/Images')
    except ErrorResponse:
        print 'Folder already exists'
    return redirect(url_for('home'))

@app.route('/dropbox-auth-start')
def dropbox_auth_start():
    if 'user' not in session:
        abort(403)
    return redirect(get_auth_flow().start())

@app.route('/dropbox-unlink')
def dropbox_unlink():
    username = session.get('user')
    if username is None:
        abort(403)
    db = get_db()
    db.execute('UPDATE users SET access_token = NULL WHERE username = ?', [username])
    db.commit()
    return redirect(url_for('home'))

def get_auth_flow():
    redirect_uri = url_for('dropbox_auth_finish', _external=True)
    return DropboxOAuth2Flow(app.config['DROPBOX_APP_KEY'], app.config['DROPBOX_APP_SECRET'], redirect_uri,
                                       session, 'dropbox-auth-csrf-token')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        if username:
            db = get_db()
            db.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', [username])
            db.commit()
            session['user'] = username
            flash('You were logged in')
            return redirect(url_for('home'))
        else:
            flash("You must provide a username")
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You were logged out')
    return redirect(url_for('home'))


def main():
    init_db()
    app.run()


if __name__ == '__main__':
    main()
