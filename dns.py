from google.appengine.ext import db
from django.utils import simplejson
import time

class Zone(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    domain  = db.StringProperty(required=True)
    ttl     = db.IntegerProperty(required=True, default=3600)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    
    @classmethod
    def get_by_domain(cls, domain):
        return cls.all().filter('domain =', domain).get()
    
    @classmethod
    def get_all_by_user(cls, user):
        return cls.all().filter('user =', user)
    
    def qname(self):
        return '%s.' % self.domain
    
    def serial(self):
        return int(time.mktime(self.updated.timetuple()))
    
    def soa_record(self):
        return {
            'name': self.qname(),
            'type': 'SOA',
            'rdata': 'ns1.domdori.com. %s. %s' % (
                self.user.email().replace('@', '.'),
                ' '.join(map(str, [
                    self.serial(),
                    3600,   # refresh
                    600,    # retry
                    86400,  # expire
                    3600,   # minimum
                ]))),
            'ttl': 0,
            'class': 'IN',}

class ResourceRecord(db.Model):
    zone    = db.ReferenceProperty(Zone)
    name    = db.StringProperty(required=True)
    type    = db.StringProperty(required=True)
    ttl     = db.IntegerProperty(required=False)
    data    = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    
    @classmethod
    def get_all_by_zone(cls, zone):
        return cls.all().filter('zone =', zone)
    
    @classmethod
    def get_all_by_name(cls, name):
        return cls.all().filter('name =', name)
    
    def __str__(self):
        return ' '.join([self.name, self.type, self.data])
        
    def qname(self):
        return '%s.' % self.name
    
    def put(self):
        if self.name[-1] == '.':
            self.name = self.name[:-1]
        db.Model.put(self)
        self._touch_zone()
    
    def delete(self):
        db.Model.delete(self)
        self._touch_zone()
    
    def _touch_zone(self):
        self.zone.updated = self.updated
        self.zone.put()
    
    def __json__(self):
        return {
            'name': self.qname(), 
            'type': self.type.upper(), 
            'rdata': self.data,
            'ttl': self.ttl if self.ttl else self.zone.ttl,
            'class': 'IN',}

class BetterJSONEncoder(simplejson.JSONEncoder):
    def default(self, o):
        if getattr(o, '__iter__', False):
            return [e.__json__() for e in o]
        return o.__json__()

import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.api import users
from google.appengine.ext.webapp import template

class DomainHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            zones = Zone.get_all_by_user(user)
            logout_url = users.create_logout_url("/")
            self.response.out.write(template.render('templates/dns.html', locals()))
        else:
            self.redirect('/')
    
    def post(self):
        domain = self.request.POST.get('domain', None)
        if domain:
            z = Zone(domain=domain)
            z.put()
        self.redirect('/dns')

class ApiHandler(webapp.RequestHandler):
    def get(self):
        domain = self.request.path.split('/')[-1]
        records = ResourceRecord.get_all_by_name(domain)
        type = self.request.GET.get('type', None)
        if type and not type == 'ANY':
            if type == 'SOA' and domain == records[0].zone.domain:
                records = [records[0].zone.soa_record()]
            elif type == 'SOA':
                records = [{'name': domain, 'type': 'CNAME', 'rdata': records[0].zone.domain, 'ttl': 1, 'class': 'IN',}]
            else:
                records = records.filter('type =', type)
        self.response.out.write(simplejson.dumps(records, cls=BetterJSONEncoder))

class RecordsHandler(webapp.RequestHandler):
    def get(self):
        domain = self.request.path.split('/')[-1]
        zone = Zone.get_by_domain(domain)
        user = users.get_current_user()
        if user and zone.user == user:
            if 'delete' in self.request.GET:
                r = ResourceRecord.get_by_id(int(self.request.GET['delete']))
                if r and r.zone.user == user:
                    r.delete()
                    self.redirect('/dns/%s' % domain)
            records = ResourceRecord.get_all_by_zone(zone)
            logout_url = users.create_logout_url("/")
            self.response.out.write(template.render('templates/records.html', locals()))
        else:
            self.redirect('/')
    
    def post(self):
        domain = self.request.path.split('/')[-1]
        zone = Zone.get_by_domain(domain)
        user = users.get_current_user()
        if user and zone.user == user:
            ttl = self.request.POST.get('ttl', None)
            name = self.request.POST['name']
            if name in ['', '@']:
                name = domain
            else:
                if not domain in name:
                    name = '.'.join([name, domain])
            record = ResourceRecord(
                zone=zone,
                name=name,
                type=self.request.POST['type'],
                data=self.request.POST['data'],
                ttl=int(ttl) if ttl else None,
            )
            record.put()
            self.redirect('/dns/%s' % domain)
        else:
            self.redirect('/')

def main():
    application = webapp.WSGIApplication([
        ('/dns', DomainHandler), 
        ('/dns/records.*', ApiHandler),
        ('/dns.*', RecordsHandler),
    ], debug=True)
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
    main()
