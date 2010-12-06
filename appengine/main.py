#!/usr/bin/env python
#
# scanningcabinet's AppEngine server-side code.
#
# Copyright 2009 Brad Fitzpatrick <brad@danga.com>
# Copyright 2009 Google Inc. (sample app that scanningcabinet is based on)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import cgi
import datetime
import logging
import os
import re
import time
import urllib

from google.appengine.api import images
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template


import wsgiref.handlers

from model import UserInfo
from model import Document
from model import MediaObject

def parse_timestamp(stamp):
  """Parse timestamp to datetime object.

  Datetime parsing is not supported until Python 2.5 and microseconds until
  Python 2.5.

  Args:
    Date/time formatted as Python 2.6 format '%Y-%m-%d %H:%M:%S.%f'.

  Returns:
    datetime object.
  """
  no_microseconds, microseconds = stamp.split('.', 1)
  time_struct = time.strptime(no_microseconds, '%Y-%m-%d %H:%M:%S')
  params = list(time_struct)[:6] + [int(microseconds)]
  return datetime.datetime(*params)


def get_user_info():
  """Get UserInfo for currently logged in user.

  This will insert the new user if it does not already exist in datastore.

  Returns:
    UserInfo record for user if user is logged in, else None.
  """
  user = users.get_current_user()
  if user is None:
    return None
  else:
    return UserInfo.get_or_insert(key_name='user:%s' % user.email())


class MainHandler(webapp.RequestHandler):
  """Handler for main page.

  If the user is logged in it will by default show all their media.

  If the user is not logged in it will by default show nothing, but suggest a
  course of action to the user.

  This page also shows the results of a search for a provided users shared
  media objects.  Only public objects are shown for the searched user. If the
  searched for user does not exist, a message is displayed to that effect.
  """

  def get(self):
    # Provide login/logout URLs.
    user_info = get_user_info()
    if user_info is None:
      login_url = users.create_login_url('/')
    else:
      login_url = users.create_logout_url('/')

    # Collect list of error messages which gets shown to the user.
    error_messages = self.request.params.getall('error_message')
    view_user = user_info  # for now
    did_search = False

    # Fetch media for view user.
    if user_info is None:
      media = []
      docs = []
      untagged_docs = []
      upcoming_due = []
    else:
      media = MediaObject.all().filter('owner', user_info)
      media = media.filter('lacks_document', True)
      media = media.order('creation')
      media = media.fetch(50)
      docs = Document.all().filter('owner', user_info)
      tags = self.request.get("tags")
      if tags:
        did_search = True
        for tag in re.split('\s*,\s*', tags):
          docs = docs.filter("tags", tag)
      docs = docs.fetch(50)

      untagged_docs = Document.all().filter('owner', user_info).filter("no_tags", True).fetch(50)

      upcoming_due = Document.all().filter('owner', user_info)
      upcoming_due = upcoming_due.filter("due_date !=", None)
      upcoming_due = upcoming_due.order("due_date")
      upcoming_due = upcoming_due.fetch(30)

    top_message = ""
    if self.request.get("saved_doc"):
      docid = long(self.request.get("saved_doc"))
      top_message = "Saved <a href='/doc/%d'>doc %d</a>" % (docid, docid)

    # Render view.
    self.response.out.write(template.render('main.html', {
        "did_search": did_search,
        "media": media,
        "docs": docs,
        "untagged_docs": untagged_docs,
        "upcoming_due_docs": upcoming_due,
        "view_user": view_user,
        "login_url": login_url,
        "user_info": user_info,
        "top_message": top_message,
        }, debug=True))


class MakeDocHandler(webapp.RequestHandler):
  def post(self):
    user_info = get_user_info()
    if user_info is None:
      self.redirect('/?error_message=%s' % 'log-in required')
    scan_ids = self.request.get_all("media_id")
    scans = MediaObject.get(scan_ids)
    doc = Document(
        parent=user_info,
        owner=user_info,
        pages=[scan.key() for scan in scans],
        title=None,
        description=None)
    def make_doc():
      db.put(doc)
      for scan in scans:
        scan.lacks_document = False
        scan.document = doc.key()
        db.put(scan)
    db.run_in_transaction(make_doc)
    self.redirect(doc.display_url + "?size=1200")


class UploadFormHandler(webapp.RequestHandler):
  """Handler to display the media object upload page.

  This must be a dynamic page because the upload URL must be generated
  by the Blobstore API.
  """

  def get(self):
    user_info = get_user_info()
    if user_info is None:
      self.redirect(
          '/?error_message=%s' % 'You must be logged in to upload media')

    upload_url = blobstore.create_upload_url(
        '/post')

    self.response.out.write(template.render('upload.html',
                                            locals(),
                                            debug=True))


def lookup_and_authenticate_user(handler, claimed_email, claimed_password):
  if not claimed_email:
    return None
  claimed_user = UserInfo.get_by_key_name('user:%s' % claimed_email)
  if not claimed_user:
    return None
  if claimed_email == 'test@example.com' and \
        handler.request.headers["Host"] == "localhost:8080":
    # No auth for testing.
    return claimed_user
  if claimed_user.upload_password and \
        claimed_user.upload_password == claimed_password:
    return claimed_user
  return None


class UploadUrlHandler(webapp.RequestHandler):
  """Handler to return a URL for a script to get an upload URL.

  This must be a dynamic page because the upload URL must be generated
  by the Blobstore API.
  """

  def get(self):
    claimed_email = self.request.get("user_email")
    effective_user = lookup_and_authenticate_user(self, claimed_email,
                                                  self.request.get("password"))

    if effective_user:
      self.response.headers['Content-Type'] = 'text/plain'
      upload_url = blobstore.create_upload_url('/post')
      self.response.out.write(upload_url)
    else:
      self.error(403)


class UploadPostHandler(blobstore_handlers.BlobstoreUploadHandler):
  """Handle blobstore post, as forwarded by notification agent."""

  def store_media(self, upload_files, error_messages):
    """Store media information.

    Writes a MediaObject to the datastore for the uploaded file.

    Args:
      upload_files: List of BlobInfo records representing the uploads.
      error_messages: Empty list for storing error messages to report to user.
    """
    if not upload_files:
      error_messages.append('Form is missing upload file field')

    if len(upload_files) != 1:
      error_messages.append('Form has more than one image.')

    def get_param(name, error_message=None):
      """Convenience function to get a parameter from request.

      Returns:
        String value of field if it exists, else ''.  If the key does not exist
        at all, it will return None.
      """
      try:
        value = self.request.params[name]
        if isinstance(value, cgi.FieldStorage):
          value = value.value
        return value or ''
      except KeyError:
        #error_messages.append(error_message)
        return None

    # Check that title, description and share fields provided.  Do additional
    # constraint check on share to make sure it is valid.
    width = get_param('width')
    height = get_param('height')

    # title and description are only legit for single-page doc
    is_doc = get_param('is_doc')  # is a stand-alone single-page doc?
    title = get_param('title')
    description = get_param('description')
    tags = get_param('tags')  # comma-separated

    # Make sure user is logged in.
    user = users.get_current_user()
    user_email = ''
    if user is None:
      claimed_email = get_param("user_email")
      effective_user = lookup_and_authenticate_user(self, claimed_email, get_param('password'))
      if not effective_user:
        error_messages.append("No user or correct 'password' argument.")
      user_email = claimed_email
    else:
      user_email = user.email()

    if error_messages:
      return

    blob_info, = upload_files

    def store_media():
      """Store media object info in datastore.

      Also updates the user-info record to keep count of media objects.

      This function is run as a transaction.
      """
      user_info = UserInfo.get_by_key_name('user:%s' % user_email)
      if user_info is None:
        error_messages.append('User record has been deleted.  '
                              'Try uploading again')
        return

      media = MediaObject(
          parent=user_info,
          owner=user_info,
          blob=blob_info.key(),
          creation=blob_info.creation,
          content_type=blob_info.content_type,
          filename=blob_info.filename,
          size=int(blob_info.size),
          lacks_document=True)

      user_info.media_objects += 1
      db.put(user_info)
      db.put(media)

      if bool(is_doc) and is_doc != "0":
        tag_list = []
        if tags is not None:
          tag_list = [x for x in re.split('\s*,\s*', tags) if x]

        doc = Document(
            parent=user_info,
            owner=user_info,
            pages=[media.key()],
            title=title,
            description=description,
            no_tags=(len(tag_list)==0),
            tags=tag_list)
        db.put(doc)
        media.document = doc.key()
        media.lacks_document = False
        db.put(media)
    db.run_in_transaction(store_media)

  def post(self):
    """Do upload post."""
    error_messages = []

    upload_files = self.get_uploads('file')

    self.store_media(upload_files, error_messages)

    error_messages = tuple(urllib.quote(m) for m in error_messages)
    error_messages = tuple('error_message=%s' % m for m in error_messages)
    self.redirect('/?%s' % '&'.join(error_messages))

    # Delete all blobs upon error.
    if error_messages:
      blobstore.delete(upload_files)


class ShowDocHandler(webapp.RequestHandler):
  def get(self, docid):
    user_info = get_user_info()
    if user_info is None:
      self.redirect('/?error_message=%s' % 'login required to view docs')
    docid = long(docid)
    doc = Document.get_by_id(docid, parent=user_info)
    if doc is None:
      self.response.out.write("Docid %d not found." % (docid))
      return
    pages = MediaObject.get(doc.pages)
    size = self.request.get("size")
    if not size:
      size = 1200
    show_single_list = long(size) > 600
    self.response.out.write(template.render('doc.html',
                                            {"doc": doc,
                                             "pages": pages,
                                             "user_info": user_info,
                                             "size": size,
                                             "show_single_list": show_single_list},
                                            debug=True))


def break_and_delete_doc(user, doc):
  """Deletes the document, marking all the images in it as un-annotated."""
  def tx():
    db.delete(doc)
    scans = MediaObject.get(doc.pages)
    for scan in scans:
      scan.lacks_document = True
      scan.document = None
      db.put(scan)
  db.run_in_transaction(tx)
  return True


def delete_doc_and_images(user, doc):
  """Deletes the document and its images."""
  scans = MediaObject.get(doc.pages)
  for scan in scans:
    blobstore.delete(scan.blob.key())
  def tx():
    db.delete(doc)
    scans = MediaObject.get(doc.pages)
    for scan in scans:
      user.media_objects -= 1
      db.delete(scan)
    db.put(user)
  db.run_in_transaction(tx)
  return True


class ChangeDocHandler(webapp.RequestHandler):
  def post(self):
    user_info = get_user_info()
    if user_info is None:
      self.redirect('/?error_message=%s' % 'login required to view docs')
    docid = long(self.request.get("docid"))
    doc = Document.get_by_id(docid, parent=user_info)
    if doc is None:
      self.response.out.write("Docid %d not found." % (docid))
      return

    mode = self.request.get("mode")
    if mode == "break":
      break_and_delete_doc(user_info, doc)
      self.response.out.write("[&lt;&lt; <a href='/'>Back</a>] Docid %d deleted and images broken out as un-annotated." % docid)
      return
    if mode == "delete":
      delete_doc_and_images(user_info, doc)
      self.response.out.write("[&lt;&lt; <a href='/'>Back</a>] Docid %d and its images deleted." % docid)
      return

    # Simple properties:
    doc.physical_location = self.request.get("physical_location")
    doc.title = self.request.get("title")

    # Tags
    doc.tags = [x for x in re.split('\s*,\s*', self.request.get("tags")) if x]
    doc.no_tags = (len(doc.tags) == 0)

    # Document Date
    date = self.request.get("date")
    if date:
      doc.doc_date = datetime.datetime.strptime(date, "%Y-%m-%d")
      doc.no_date = False
    else:
      doc.doc_date = None
      doc.no_date = True

    # Due date
    due_date_str = self.request.get("due_date")
    doc.due_date = None
    if due_date_str:
      doc.due_date = datetime.datetime.strptime(due_date_str, "%Y-%m-%d")

    def store():
      db.put(doc)
    db.run_in_transaction(store)
    self.redirect("/?saved_doc=" + str(docid))


class ResourceHandler(blobstore_handlers.BlobstoreDownloadHandler):
  """For when user requests media object.  Actually serves blob."""

  def get(self, media_id, unused_filename):
    user_info = get_user_info()
    if user_info is None:
      self.redirect('/?error_message=%s' % 'log-in required')
    media_object = MediaObject.get_by_id(long(media_id), parent=user_info)
    if media_object is None:
      self.redirect('/?error_message=Unidentified+object')
      return

    last_modified_string = media_object.creation.strftime("%a, %d %b %Y %H:%M:%S GMT")
    self.response.headers['Cache-Control'] = "public, max-age=31536000"
    self.response.headers['Content-Type'] = str(media_object.guessed_type)
    self.response.headers['Last-Modified'] = last_modified_string
    expires = media_object.creation + datetime.timedelta(days=30)
    self.response.headers['Expires'] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")

    # Caching
    if self.request.headers.has_key("If-Modified-Since"):
      ims = self.request.headers.get("If-Modified-Since")
      if ims == last_modified_string:
        self.error(304)
        return
      modsince = datetime.datetime.strptime(ims, "%a, %d %b %Y %H:%M:%S %Z")
      if modsince >= media_object.creation:
        self.error(304)
        return

    blob_key = media_object.blob.key()

    resize = self.request.get('resize')
    if resize:
      image = images.Image(blob_key=str(blob_key))
      image.resize(width=int(resize), height=int(resize))
      self.response.out.write(image.execute_transforms())
      return

    if 'Range' in self.request.headers:
      self.response.headers['Range'] = self.request.headers['Range']

    self.send_blob(blob_key, str(media_object.guessed_type))


class GarbageCollectMediaHandler1(webapp.RequestHandler):
  def get(self):
    if not users.is_current_user_admin():
      self.redirect('/?error_message=%s' % 'log-in required')

    used = set()
    for d in Document.all():
      used |= set(d.pages)

    dead = dict()
    for i in MediaObject.all():
      if i.key() not in used:
        dead[i.key()] = i

    for k in dead:
      dead[k].delete()

    self.redirect('/')

class GarbageCollectMediaHandler2(webapp.RequestHandler):
  def get(self):
    if not users.is_current_user_admin():
      self.redirect('/?error_message=%s' % 'log-in required')

    used = set()
    for i in MediaObject.all():
      used.add(i.blob.key())

    for b in blobstore.BlobInfo.all():
      if b.key() not in used:
        b.delete()

    self.redirect('/')

def main():
  application = webapp.WSGIApplication(
      [('/', MainHandler),
       ('/uploadurl', UploadUrlHandler),  # returns a new upload URL
       #('/upload', UploadFormHandler),    # for humans
       ('/post', UploadPostHandler),      # for machine or humans to upload
       ('/makedoc', MakeDocHandler),
       ('/doc/(\d+)', ShowDocHandler),
       ('/changedoc', ChangeDocHandler),
       ('/resource/(\d+)(/.*)?', ResourceHandler),
       #('/gc_media1', GarbageCollectMediaHandler1),
       #('/gc_media2', GarbageCollectMediaHandler2),
       ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
