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

import mimetypes

from google.appengine.ext import blobstore
from google.appengine.ext import db


class MigratingBlobReferenceProperty(db.Property):
  """Migrates pre-1.3.0 blob str props to real blobkey references."""

  data_type = blobstore.BlobInfo

  def get_value_for_datastore(self, model_instance):
    """Translate model property to datastore value."""
    blob_info = getattr(model_instance, self.name)
    if blob_info is None:
      return None
    return blob_info.key()

  def make_value_from_datastore(self, value):
    """Translate datastore value to BlobInfo."""
    if value is None:
      return None

    # The two lines of difference of MigratingBlobReferenceProperty:
    if isinstance(value, basestring):
      value = blobstore.BlobKey(value)

    return blobstore.BlobInfo(value)

  def validate(self, value):
    """Validate that assigned value is BlobInfo.

    Automatically converts from strings and BlobKey instances.
    """
    if isinstance(value, (basestring)):
      value = blobstore.BlobInfo(blobstore.BlobKey(value))
    elif isinstance(value, blobstore.BlobKey):
      value = blobstore.BlobInfo(value)
    return super(MigratingBlobReferenceProperty, self).validate(value)


class UserInfo(db.Model):
  """Information about a particular user and their media library."""
  user = db.UserProperty(auto_current_user_add=True)
  media_objects = db.IntegerProperty(default=0)
  upload_password = db.StringProperty()

  # non_owner is set if a helper (e.g. Brad's brother) is helping him
  # tag
  non_owner = False
  real_email = ""    # real user's email

class Document(db.Model):
  """A document with 1 or more media objects (1+ pages, 0/1 preview)"""
  owner = db.ReferenceProperty(UserInfo, required=True)

  pages = db.ListProperty(db.Key, required=True)
  preview = db.ListProperty(db.Key)  # preview images, if pages is a PDF

  doc_date = db.DateTimeProperty()
  no_date = db.BooleanProperty(required=True, default=True)

  creation = db.DateTimeProperty(auto_now_add=True)

  title = db.StringProperty()
  description = db.TextProperty()

  tags = db.StringListProperty()
  no_tags = db.BooleanProperty(required=True, default=True)

  # To find the paper document back later:
  physical_location = db.StringProperty()

  # Things I need to get to (taxes, etc.)
  due_date = db.DateTimeProperty()

  starred = db.BooleanProperty()

  @property
  def display_url(self):
    return '/doc/%s' % self.key().id()

  @property
  def tag_comma_separated(self):
    return ", ".join(self.tags)

  @property
  def date_yyyy_mm_dd(self):
    """Or empty string."""
    if self.doc_date:
      return str(self.doc_date)[0:10]
    return ""

  @property
  def due_yyyy_mm_dd(self):
    """Or empty string."""
    if self.due_date:
      return str(self.due_date)[0:10]
    return ""

  @property
  def title_or_empty_string(self):
    """The real title, or the empty string if none."""
    if not self.title:
      return ""
    return self.title

  @property
  def some_title(self):
    if self.title:
      return self.title
    if self.tags:
      return ", ".join(self.tags)
    return self.title


class MediaObject(db.Model):
  """Information about media object uploaded by user.

  Does not contain the actual object, which is in blobstore.  Contains duplicate
  meta-information about blob for searching purposes.
  """
  owner = db.ReferenceProperty(UserInfo, required=True)

  blob = MigratingBlobReferenceProperty()

  creation = db.DateTimeProperty()
  content_type = db.StringProperty()

  filename = db.StringProperty()  # foo.jpg
  original_path = db.StringProperty()  # scan/tax/2009/foo.jpg
  size = db.IntegerProperty()

  # If known:
  width = db.IntegerProperty()
  height = db.IntegerProperty()

  # If part of a document yet, a reference (db.Key) to a media object.
  document = db.ReferenceProperty(Document, required=False)
  lacks_document = db.BooleanProperty()

  @property
  def thumb_url(self):
    return '/resource/%d/%s?resize=300' % (self.key().id(), self.filename)

  @property
  def url_resize(self):
    return '/resource/%s/%s?resize=' % (self.key().id(), self.filename)

  @property
  def url_path(self):
    return '/resource/%s/%s' % (self.key().id(), self.filename)

  @property
  def guessed_type(self):
    """A guess for the content type of this media object.

    This is currently necessary because the production version of the
    Blobstore API does not try to detect content types of uploads.
    """
    if self.content_type == 'application/octet-stream':
      # Try to guess.  Useful for backward compatibility with older objects
      # that had not content type detection.
      mime_type, unused_parameters = mimetypes.guess_type(self.filename)
      return mime_type or 'text/plain'
    else:
      return self.content_type or 'text/plain'

  @property
  def is_image(self):
    """Returns True if this media object is an image."""
    image_types = frozenset([
        'image/png', 'image/jpeg', 'image/tiff', 'image/gif', 'image/bmp'])
    return self.guessed_type in image_types

  def delete(self):
    """Also delete associated media blob and decrement users media count."""
    super(MediaObject, self).delete()
    self.owner.media_objects -= 1
    self.owner.put()
    self.blob.delete()
