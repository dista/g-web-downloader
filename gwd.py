#!/usr/bin/env python

from Queue import Queue
import urllib2
from urllib2 import *
import threading
from threading import Thread
import re
import hashlib
import urlparse
import os
import traceback
import sys
import thread
from os import path
from datetime import datetime
import time

#so i can search keyword debug to remove it
def debug(msg):
    print msg

DATEFMT = "%Y-%m-%d %H:%M:%S"

class Utility:
    @staticmethod
    def get_local_path(refer, url, is_relative = True):
        if Utility.is_js_label(url):
            return url
        if refer == None:
            refer = ""
        url = urlparse.urljoin(refer, url)
        ret = urlparse.urlparse(url)  
        
        path = ret.path
        if ret.path in ['/', '']:
            path = '/index.html'
        elif ret.path[-1] == '/':
            path = ret.path + 'index.html'
        query_str = ret.query.replace('?', '-').replace('=', '-').replace('&', '-').replace("://", '-').replace('.', '-')

        if len(url) > 200:
            query_str = hashlib.md5(query_str).hexdigest() 

        path_comps = path.split('/')
        last_piece = path_comps[-1]

        if '.' in last_piece:
            sps = last_piece.rsplit('.', 1)

            if len(sps) == 2:
                path_comps[-1] = sps[0] + query_str + '.' + sps[1]

         
        retval = "%s%s" % (ret.netloc.replace('.', '-'), '/'.join(path_comps))

        if not is_relative:
            return retval
        else:
            ref_abs = Utility.get_local_path("", refer, False)
            return Utility.get_relative_path(ref_abs, retval)

    @staticmethod
    def get_relative_path(a, b):
        ''' 
        b relative to a
        example:
        /root/x/1.html; /root/y/2.html
        the result is ../../y/2.html
        '''
        a_parts = a.split("/")
        b_parts = b.split("/")

        for i in xrange(len(a_parts)):
            if a_parts[i] != b_parts[i]:
                break
        
        return "../" * (len(a_parts) - i - 1) + "/".join(b_parts[i:])


    @staticmethod
    def is_js_label(url):
        '''
        javascript label may exist in src attribute, test for that.
        '''
        if url.strip().startswith('javascript:'):
            return True
        return False

class Parser:
    '''
    parse html, css documents to find urls in them
    '''

    #href, src, url, import from which an url appears
    href_regex = re.compile(r"(href\s*=\s*([\"'])([^\"']+)\2)")
    src_regex = re.compile(r"(src\s*=\s*([\"'])([^\"']+)\2)")
    back_images_regex = re.compile(r"(url\s*\(\s*([\"']*)([^\"'()]+)\2)\)")
    css_import_regex = re.compile(r"(@import\s*\(\s*([\"']*)([^\"'()]+)\2)\)")

    def parse(self, content, url, store_path):
        self.store_path = store_path.rstrip('/')
        self.content = content
        self.url = url

        links = []
        for rx, link_pos in [(Parser.href_regex, 2), (Parser.src_regex, 2), (Parser.back_images_regex, 2), (Parser.css_import_regex, 2)]:
            links += self.replace_url_in_content(rx, link_pos)

        return links

    def replace_url_in_content(self, regex, link_pos):
        '''
        file will be store in local disk, so we need to replace the original urls in them with the one using file: schemal
        '''
        founded = regex.findall(self.content)

        links = []
        for fd in founded:
            full = fd[0]
            link = fd[link_pos]
            #print link

            ps_ret = urlparse.urlparse(link)
            t = urlparse.urlparse(urlparse.urljoin(self.url, link))

            if t.scheme == 'http':
                new_full = full.replace(link, "%s#%s" % (Utility.get_local_path(self.url, link), ps_ret.fragment))
                self.content = self.content.replace(full, new_full) 
                links.append(link)

        return links

    def get_changed_content(self):
        return self.content

class RememberFailedError(Exception):
    pass

#Store will make sure that there won't be two thread write to one memery place
class Memory:
    '''
    provide an interface the remember the downloaded files. also we can query if the url has been downloaded from this class
    '''
    def __init__(self, memery_place):
        self.memery_place = path.join(memery_place, ".mem")
        if not path.isdir(self.memery_place):
            os.makedirs(self.memery_place)
    def remember(self, job, links):
        '''
        remember the downloaded urls
        '''
        f = None
        try:
            f = open(self.get_memery_place(job), 'w')
            for link in links:
                new_job = Job(link, job.get_joined_link())
                f.write(new_job.get_joined_link() + "\n")
        except IOError, e:
            raise RememberFailedError(e)
        finally:
            if f != None:
                f.close()

    def remembered(self, job):
        '''
        query if the url(job) has been downloaded(done)
        '''
        f = None
        try:
            mem_place = self.get_memery_place(job)

            if not os.path.isfile(mem_place):
                return None
            f = open(mem_place, 'r')
            content = f.read()
            links = content.split("\n")

            jobs = []
            for link in links:
                jobs.append(Job(link, ""))
            return jobs
        except IOError, e:
            raise RememberFailedError(e)
        finally:
            if f != None:
                f.close()

    def get_memery_place(self, job):
        return path.join(self.memery_place, job.get_id())
        
class Downloader:
    '''
    contains the logic to download from an url
    '''
    white_lists =  ['text/html', 'text/css', 'text/plain', 
                    'text/xml', 'text/javascript', 'image/png', 
                    'image/gif', 'image/jpeg', 'application/x-javascript', 
                    'application/xml', 'application/javascript']

    """download from an url, it will download all files related with this url"""
    def __init__(self, store, mem_inst):
        self.store = store
        self.parser = Parser()
        self.mem_inst = mem_inst
        self.encount_empty_time = 0
        self.exit = False

    def kill(self):
        self.exit = True

    def download(self):
        '''
        download routine
        '''
        while True:
            if self.exit:
                break

            if self.store.empty():
                self.encount_empty_time += 1
                time.sleep(1)

            if self.encount_empty_time == 10:
                break;

            try:
                job = self.store.get()
            except StoreEmptyError, e:
                continue

            self.encount_empty_time = 0

            #print job
            if Utility.is_js_label(job.get_link()):
                self.store.task_done()
                continue


            mem_jobs = self.mem_inst.remembered(job)
            if mem_jobs != None:
                try:
                    for mem_job in mem_jobs:
                        self.store.put(mem_job)
                    continue
                except RememberFailedError, e:
                    raise e
                finally:
                    self.store.task_done()
                
            link = job.get_joined_link()
            try:
                bechmark_start = datetime.now()
                c, c_t = self.get_content(job)
                bechmark_end = datetime.now()
                print("download '%s' takes %s" %( job.get_joined_link(), (bechmark_end - bechmark_start)))

                if c_t in ['text/html', 'text/css']:
                    links = self.parser.parse(c, link, self.store.get_store_path())
                    c = self.parser.get_changed_content()
                else:
                    links = []
                   
                localpath = Utility.get_local_path(job.get_referer(), job.get_link(), False)
                localpath = os.path.join(self.store.get_store_path(), localpath) 

                dir = os.path.dirname(localpath)
                file_name = os.path.basename(localpath)

                if not os.path.isdir(dir):
                    os.makedirs(dir, 0755)

                try:
                    f = open(localpath, 'w+')
                    f.write(c)

                    self.mem_inst.remember(job, links)
                    for lk in links:
                        self.store.put(Job(lk, link))
                except IOError:
                    print "can't write to %s" % localpath
                finally:
                    if f != None:
                        f.close()
            except URLError:
                print "can't down load from %s" % link
            except RememberFailedError, e:
                raise e
            except Exception, e:
                print "error happended %s" % e
                traceback.print_exc()
            finally:
                self.store.task_done()
            
    def get_content(self, job):
        '''
        use urllib to download the file
        '''
        url = job.get_joined_link()

        request = Request(url)

        fh = urllib2.urlopen(request)
        content = fh.read()

        ct = fh.headers['Content-Type']
        match = re.match(r'(.*);', ct)

        if match != None:
            con_type = match.groups()[0]
        else:
            if 'charset' not in ct:
                con_type = ct.rstrip(';')
            else:   
                con_type = ct

        if con_type in Downloader.white_lists:
            return (content, con_type)
        else:
            print con_type
            return ("", con_type)

class Filter:
    '''
    tell us what kind of file should be downloaded and what should not be
    '''
    def __init__(self):
        self.ft = set()

    def add_filter(self, *args):
        '''
        add filter rules
        '''
        for filter in args:
            self.ft.add(filter)

    def passed(self):
        '''
        check if passed
        '''
        if len(self.ft) == 0:
            return True
        else:
            return False

class WhiteList(Filter):
    def passed(self, url):
        if  Filter.passed(self):
            return True

        else:
            for filter in self.ft:
                if re.search(filter, url):
                    return True
            return False

class BlackList(Filter):
    def passed(self, url):
        if  Filter.passed(self):
            return True

        else:
            for filter in self.ft:
                if re.search(filter, url):
                    return False
            return True

class StoreError(Exception):
    pass

class StoreEmptyError(StoreError):
    pass
     
class Store(Queue):
    '''
    a wrapper class to Queue.Queue, so we can control the get and put process
    '''
    def __init__(self, store_path):
        Queue.__init__(self)
        self.store_path = store_path
        self.whitelist = WhiteList()
        self.blacklist = BlackList()
        self.image_free_pass = False

        self.stored_job_ids = set()

    def put(self, job):
        if self.pass_filters(job):
            Queue.put(self, job)

    def get(self):
        while True:
            if Queue.empty(self):
                raise StoreEmptyError()

            job = Queue.get(self)
            if job.get_id() not in self.stored_job_ids:
                self.stored_job_ids.add(job.get_id())
                return job
            else:
                self.task_done()

    def get_store_path(self):
        return self.store_path

    def add_white_filter(self, *args):
        for arg in args:
            if arg == "{image}":
                self.image_free_pass = True
            else:
                self.whitelist.add_filter(arg) 

    def add_black_filter(self, *args):
        self.blacklist.add_filter(*args) 

    def pass_filters(self, job):
        if self.is_picture(job) and self.image_free_pass:
            return True

        link = job.get_joined_link()
        if self.blacklist.passed(link):
            if self.whitelist.passed(link):
                return True
            else:
                return False
        else:
            return False
    def is_picture(self, job):
        link = job.get_link()
        if '.jpg' in link \
            or '.jpeg' in link \
            or '.png' in link:
            return True

        return False

class DH(threading.Thread):
    '''
    download thread
    '''
    def __init__(self, store, mem_inst):
        Thread.__init__(self)
        self.downloader = Downloader(store, mem_inst)
        
    def run(self):
        try:
            self.downloader.download()
        except Exception, e:
            print e
            traceback.print_exc()
            thread.exit()

    def kill(self):
        self.downloader.kill()


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

class DHManager:
    '''
    manage download thread. try to brint up exited download thread if the total downloading job is not finished yet
    '''
    bringup_time = 30
    def __init__(self, store, mem_inst, th_count):
        self.dhs = []
        self.original_count = th_count
        self.first_die_time = None
        self.store = store
        self.mem_inst = mem_inst
        self.exit = False
        self.killcmd_issued = False

        for i in range(0, th_count):
            self.dhs.append(DH(store, mem_inst))
            self.dhs[-1].start()

        print "At %s, we are now downloading..." % (datetime.now().strftime(DATEFMT))

    def wait_for_all_exit(self):
        while True:
            if len(self.dhs) == 0:
                break

            if self.first_die_time != None and (datetime.now() - self.first_die_time).seconds > DHManager.bringup_time:
                for i in range(len(self.dhs), self.original_count):
                    self.dhs.append(DH(self.store, self.mem_inst))
                    self.dhs[-1].start()
                self.first_die_time = None

            for dh in self.dhs:
                if not dh.is_alive():
                    self.dhs.remove(dh)
                    if self.first_die_time == None:
                        self.first_die_time = datetime.now()
    
            time.sleep(1)

    def kill(self):
        for dh in self.dhs:
            dh.kill()

        print "%d thread need to be killed, please wait." % len(self.dhs)

        while True:
            for dh in self.dhs:
                if not dh.is_alive():
                    self.dhs.remove(dh)
                    print len(self.dhs)

            if len(self.dhs) == 0:
                break
            time.sleep(1)
        
        print "done"

def main():
    start_time = datetime.now()
    download_path = '/root/lua-book'
    try:
        store = Store(download_path)
    except StoreError, e:
        print e
        sys.exit(1)

    mem_inst = Memory(download_path)

    #store.add_filter("\.163\.com",
    #                "cache\.netease\.com",
    #                "\.126\.net",
    #                )
    #store.put(Job("http://www.163.com"))

    #store.add_white_filter("docs\.python\.org")
    #store.add_black_filter("docs\.python\.org/download")
    #store.put(Job("http://docs.python.org"))

    #store.put(Job("http://docs.python.org"))

    #store.add_white_filter("\.cnbeta\.com", "{image}")
    store.add_white_filter("www\.lua\.org\/pil\/")
    store.put(Job("http://www.lua.org/pil/index.html"))
    
    dh_manager = None
    try:
        dh_manager = DHManager(store, mem_inst, 10)
        dh_manager.wait_for_all_exit()
    except KeyboardInterrupt:
        if dh_manager != None:
            dh_manager.kill()

    end_time = datetime.now()
    print("download finished, takes %s" % (end_time - start_time))
        
if __name__ == '__main__':
    main() 
