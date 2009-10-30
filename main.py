import wsgiref.handlers

from google.appengine.ext import webapp
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template
from google.appengine.ext import db

import urllib

# These only work if your IP is allowed
import keys
ENOM_UID = keys.enom_uid
ENOM_PASS = keys.enom_pass
ENOM_HOST = keys.enom_host
NS1 = 'ns1.domdori.com'
NS2 = 'ns2.domdori.com'

class Domain(db.Model):
    user    = db.UserProperty(auto_current_user_add=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    name    = db.StringProperty(required=True)
    
    @classmethod
    def get_all_by_user(cls, user):
        return cls.all().filter('user =', user)
    

def parse_response(body):
    return dict([kvp.split('=') for kvp in body.split('\r\n') if len(kvp) and not kvp[0] == ';'])

class RegisterHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write(template.render('templates/main.html', locals()))
    
    def post(self):
        domain = self.request.POST['domain']
        sld, tld = domain.split('.')
        url = "http://%s/Interface.asp?command=Purchase&UID=%s&PW=%s&SLD=%s&TLD=%s&NS1=%s&NS2=%s" % (ENOM_HOST, ENOM_UID, ENOM_PASS, sld, tld, NS1, NS2)
        resp = urlfetch.fetch(url)
        resp = parse_response(resp.content)
        if resp['RRPCode'] == '200':
            d = Domain(name=domain)
            d.put()
            self.response.headers.add_header('Set-Cookie', 'flash=%s' % urllib.quote("You successfully registered %s!" % domain))
            self.redirect('/domains')
        else:
            self.response.out.write(resp['RRPText'])

class MainHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            logout_url = users.create_logout_url("/")
        else:
            login_url = users.create_login_url('/')
        self.response.out.write(template.render('templates/main.html', locals()))

class CheckHandler(webapp.RequestHandler):
    def get(self):
        domain = self.request.GET['domain']
        if '.' in domain:
            sld, tld = domain.split('.')
        else:
            sld = domain
            tld = '@'
        url = "http://%s/interface.asp?Command=Check&UID=%s&PW=%s&SLD=%s&TLD=%s" % (ENOM_HOST, ENOM_UID, ENOM_PASS, sld, tld)
        resp = urlfetch.fetch(url)
        resp = parse_response(resp.content)
        domains = {}
        if tld == '@':
            for n in range(3):
                index = str(n+1)
                domains[resp['Domain%s' % index]] = resp['RRPText%s' % index]
        else:
            domains[domain] = resp['RRPText']
        self.response.out.write(str(domains))

class SplashHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write("Be patient...")

def main():
    application = webapp.WSGIApplication([('/', SplashHandler), ('/main', MainHandler), ('/check', CheckHandler), ('/register', RegisterHandler)], debug=True)
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
    main()
