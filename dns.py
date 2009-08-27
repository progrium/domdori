from google.appengine.ext import db

class Zone(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    domain  = db.StringProperty(required=True)
    ttl     = db.IntegerProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)

class ResourceRecord(db.Model):
    zone    = db.ReferenceProperty(Zone)
    name    = db.StringProperty(required=True)
    type    = db.StringProperty(required=True)
    ttl     = db.IntegerProperty(required=False)
    data    = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)