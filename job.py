from urllib2 import urlparse
import hashlib
import re

class Job:
    '''
    job contains all the information downloader need to know to download
    '''
    def __init__(self, url, referer = None):
        self.url = url
        self.referer = referer

    def get_link(self):
        return self.url

    def get_referer(self):
        return self.referer

    def get_joined_link(self):
        if self.referer == None:
            return self.url
        else:
            return urlparse.urljoin(self.referer, self.url)
    
    def get_id(self):
        return hashlib.md5(re.sub(r"#.*$", "", self.get_joined_link())).hexdigest() 

    def __str__(self):
        return self.url
