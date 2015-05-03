################################################################################
#
# NOTICE: unmaintained! As of 2015-05-03 I no longer use this App Engine-based
# version of Scanning Cabinet.
#
# The migration of my App Engine instance from Master/Slave datastore to HRD
# failed, so I'm accelerating plans to move this project to be Camlistore-based
# instead. See camlistore.org. This will just be a Camlistore app, using its
# data model.
#
# Old README follows.
#
################################################################################


This is scanningcabinet.

It's my document management system.  Maybe you'll like it too.

Problem statement:

   * I'm a packrat.  Yes, I might need my T-Mobile cellphone bill from
     March 2001 sometime.  Maybe.  (shutup)

   * My filing cabinets are full.

   * It's cold in San Francisco and I want to burn stuff.

   * I can't find tax or insurance documents when I need to anyway,
     because folders suck.  I want tags.  e.g. I can tag that one
     document "audi, insurance, crash, car, state farm, royal motors"
     and be sure I'll find it later.  Which frickin' folder would I
     put that in anyway?  Folders sucks.  Yay tags.

   * I have a scanner.  My friend's scanner is better.  Borrowed that
     one.  It has a sheet feeder.

   * App Engine now has a Blob API: http://bit.ly/8K4FxM

   * It should be easy to get documents online.  Must minimize context
     switching between feeding the scanner and entering metadata.  In fact,
     they should be *entirely separate* tasks.  If I have to enter metadata
     while scanning, I'll probably just end up on reddit.

   * All document metadata entry should be done later.  This includes
     clumping multi-page scans into their logical documents.  I shouldn't
     have to even enter how many pages a document is when I scan it.
     I'll be scanning stacks in the auto-document-feeder anyway.

   * Usually I want to just burn/shred documents, but occasionally
     I'll need the physical document in the future (like for taxes or
     jury duty), so the metadata must include information about the
     document's physical location. (e.g. "Red Folder #1")  Then when
     I need it again, I go linear scan Red Folder #1 looking for it.
     Also, I track the "due date" of the document, and show upcoming
     ones on the main page, so I see pending due taxes get closer and
     closer.  Frickin' taxes.

Anyway, I wrote some software.  (parts are kinda crap because I always
forget Python, but whatevs.)

Some instructions:

* tools/scancab is the client program.  You use it to scan & upload.
  Read its docs & comments.  You'll need to modify the email &
  password later.  But first:

* appengine/ is the AppEngine server component.  Go to
  http://appspot.com/ to make an AppID ("bobscans").  Then get the
  1.3.0 or higher App Engine SDK, tweak
  scanningcabinet/appengine/app.yaml file to match your AppID, then
  appcfg.py update 'appengine' to upload the app to your account.

  -- Now, go to https://<your_appid>.appspot.com/ and login.  This
     makes your UserInfo entity in the database.  That's all.

  -- Now, go back to http://appspot.com/, click your App, then click
     "Datastore Viewer" on the left.  Find your UserInfo entity, click
     it, and modify its "upload_password" to some password you'll use
     for uploading.  Don't use your Google password.  Choose type
     "string".

  -- Now, go put your Google account's email & that password you just
     made up into scanningcabinet/tools/scancab

* Now start scanning stuff.

* Occasionally go add metadata at your app URL.

Enjoy!

Brad
brad@danga.com
