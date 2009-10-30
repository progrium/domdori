import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.api import users
from google.appengine.ext.webapp import template

from main import Domain

class DomainsHandler(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            domains = Domain.get_all_by_user(user)
            logout_url = users.create_logout_url("/")
            self.response.out.write(template.render('templates/domains.html', locals()))
        else:
            self.redirect('/')
    

def main():
    application = webapp.WSGIApplication([('/domains', DomainsHandler),], debug=True)
    wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
    main()