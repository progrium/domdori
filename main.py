#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
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




import wsgiref.handlers


from google.appengine.ext import webapp
from google.appengine.api import urlfetch
from google.appengine.ext.webapp import template

# These only work if your IP is allowed
ENOM_UID = 'fihn'
ENOM_PASS = ''

def parse_response(body):
    return dict([kvp.split('=') for kvp in body.split('\r\n') if len(kvp) and not kvp[0] == ';'])

class RegisterHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write(template.render('templates/main.html', locals()))

class MainHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write(template.render('templates/main.html', locals()))

class CheckHandler(webapp.RequestHandler):
    def get(self):
        domain = self.request.GET['domain']
        if '.' in domain:
            sld, tld = domain.split('.')
        else:
            sld = domain
            tld = '@'
        url = "http://resellertest.enom.com/interface.asp?Command=Check&UID=%s&PW=%s&SLD=%s&TLD=%s" % (ENOM_UID, ENOM_PASS, sld, tld)
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


def main():
    application = webapp.WSGIApplication([('/', MainHandler), ('/check', CheckHandler), ('/register', RegisterHandler)], debug=True)
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
    main()
