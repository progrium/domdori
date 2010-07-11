from google.appengine.ext import db
from django.utils import simplejson
import time

def sld(domain):
    return '.'.join(domain.split('.')[-2:])

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
    def exists(cls, domain):
        return cls.all().filter('domain =', domain).get() or \
            cls.all().filter('domain =', sld(domain)).get()
    
    @classmethod
    def get_all_by_user(cls, user):
        return cls.all().filter('user =', user)
    
    def qname(self):
        return '%s.' % self.domain
    
    def serial(self):
        return int(time.mktime(self.updated.timetuple()))
    
    def soa_cname(self, name):
        return {'name': name, 'type': 'CNAME', 'rdata': self.domain, 'ttl': 1, 'class': 'IN',}
    
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
            'ttl': 3600,
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
        records = cls.all().filter('name =', name)
        if records.count() == 0:
            records = cls.all().filter('name =', '*.' + name.split('.', 1)[1])
        return records
    
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

class DNSMessage(object):
    
    def __init__(self):
        self.header     = {}
        self.answer     = []
        self.authority  = []
        self.additional = []
    
    @classmethod
    def query(cls, name, type):
        records = ResourceRecord.get_all_by_name(name)
        if records.count() > 0:
            zone = records[0].zone
        else:
            zone = None
        if type == 'ANY':
            query = records.fetch(1000)
        else:
            if type == 'SOA' and zone:
                if name == zone.domain:
                    query = [zone.soa_record()]
                else:
                    query = [zone.soa_cname(name)]
            elif type == 'AXFR' and zone:
                if name == zone.domain:
                    query = zone.resourcerecord_set.fetch(1000)
                    query.insert(0, zone.soa_record())
                else:
                    query = [zone.soa_cname(name)]
            else:
                query = records.filter('type =', type).fetch(1000)
                if not len(query) and type == 'A':
                    query = ResourceRecord.get_all_by_name(name).filter('type =', 'CNAME').fetch(1000)
        # Resolve wildcards
        for record in query:
            if isinstance(record, dict):
                if '*' in record['name']:
                    record['name'] = name
            else:
                if '*' in record.name:
                    record.name = name
        return cls.create(name, query, zone)
    
    @classmethod
    def create(cls, name, query, zone=None):
        message = cls()
        message.answer = query
        if len(query):
            # Query succeeds
            message.header['rcode'] = 'NOERROR'   
        else:
            if zone:
                # Domain exists, query fails (none of this type)
                message.header['rcode'] = 'NOERROR'   
                message.authority.append(zone.soa_record())
            else:
                exists = Zone.exists(name)
                if not exists:
                    # Domain is not hosted here
                    message.header['rcode'] = 'REFUSED'
                else:
                    # Query failed, domain not found, but likely hosted here
                    message.header['rcode'] = 'NXDOMAIN'
                    message.authority.append(exists.soa_record())
        return message
    
    def __json__(self):
        return dict(
            answer      =self.answer,
            authority   =self.authority,
            additional  =self.additional,
            header      =self.header,)

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

class WebDNSHandler(webapp.RequestHandler):
    def get(self, name, type='ANY'):
        message = DNSMessage.query(name, type)
        if not message.answer:
            self.response.set_status(404)
        self.response.out.write(simplejson.dumps(message, cls=BetterJSONEncoder))

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
        ('/dns/IN/(.+)/(.*)', WebDNSHandler),
        ('/dns.*', RecordsHandler),
    ], debug=True)
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
    main()
