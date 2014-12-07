#!/usr/bin/env python

# Copyright (c) 2013-2014, dista
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies, 
# either expressed or implied, of the FreeBSD Project.

from Queue import Queue, Empty
from processer import *
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
import pickle
from job import Job
import StringIO
import gzip
import signal

import gc

# for trace memory
#from guppy import hpy
#hp = hpy()

#so i can search keyword debug to remove it
def debug(msg):
    print msg
    
SAFELOCKER = threading.Lock()
def safe_print(msg):
    SAFELOCKER.acquire()
    print msg
    SAFELOCKER.release()
    
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
            if i >= len(b_parts):
                break
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
    href_regex = re.compile(r"(href\s*=\s*([\"'])([^\"']+)\2)", re.IGNORECASE)
    src_regex = re.compile(r"(src\s*=\s*([\"'])([^\"']+)\2)", re.IGNORECASE)
    back_images_regex = re.compile(r"(url\s*\(\s*([\"']*)([^\"'()]+)\2)\)", re.IGNORECASE)
    css_import_regex = re.compile(r"(@import\s*\(\s*([\"']*)([^\"'()]+)\2)\)", re.IGNORECASE)

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

            if t.scheme == 'http' or t.scheme == 'https':
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
        self.memery_place = path.join(memery_place, ".gwd", "mem")
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
            content = f.read().rstrip("\n")

            if content:
                links = content.split("\n")
            else:
                links = []

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

class SaveFileProcesser(Processer):
    def __init__(self, store):
        self.store = store

    def do_process(self, job, c_t, content):
        localpath = Utility.get_local_path(job.get_referer(), job.get_link(), False)
        localpath = os.path.join(self.store.get_store_path(), localpath) 

        dir = os.path.dirname(localpath)
        file_name = os.path.basename(localpath)

        if not os.path.isdir(dir):
            os.makedirs(dir, 0755)

        f = None
        try:
            f = open(localpath, 'w+')
            f.write(content)

        except IOError:
            safe_print("can't write to %s" % localpath)
        finally:
            if f != None:
                f.close()

class Downloader:
    '''
    contains the logic to download from an url
    '''
    white_lists =  ['text/html', 'text/css', 'text/plain', \
                    'text/xml', 'text/javascript', 'image/png', \
                    'image/gif', 'image/jpeg', 'application/x-javascript', \
                    'application/xml', 'application/javascript', \
                    "application/json"]

    """download from an url, it will download all files related with this url"""
    def __init__(self, store, mem_inst):
        self.store = store
        self.parser = Parser()
        self.mem_inst = mem_inst
        self.exit = False
        self.processer = SaveFileProcesser(self.store)
        #self.processer = ExtractBookProcesser(self.store.get_store_path() + "/__book__")

    def kill(self):
        self.exit = True

    def download(self):
        '''
        download routine
        '''
        while not (self.exit or DHManager.all_is_done):
            try:
                job = self.store.get()
            except Empty, e:
                time.sleep(1) 
                continue

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
                    self.store.mark_as_done(job)
                    self.store.task_done()

            link = job.get_joined_link()
            try:
                bechmark_start = datetime.now()
                c, c_t = self.get_content(job)
                bechmark_end = datetime.now()
                safe_print("download %s, takes %s" % (link, bechmark_end - bechmark_start))

                if c_t in ['text/html', 'text/css']:
                    links = self.parser.parse(c, link, self.store.get_store_path())
                    c = self.parser.get_changed_content()
                else:
                    links = []

                self.processer.do_process(job, c_t, c);

                self.mem_inst.remember(job, links)
                for lk in links:
                    self.store.put(Job(lk, link))
                
                self.store.mark_as_done(job)

            except URLError, e:
                safe_print("can't down load from %s %s" % (link, e))
                
                if job.get_retry_times() < 20:
                    new_job = Job(link, link, job.get_retry_times() + 1) 
                    self.store.put(new_job)
                else:
                    safe_print("exceed 20 retry times")
                    #os._exit(1)
            except RememberFailedError, e:
                raise e
            except Exception, e:
                if str(e) == "timed out" and job.get_retry_times() < 100:
                    self.store.put(Job(link, link))
                else:
                    safe_print("exceed 100 retry times")
                    #os._exit(1)
                safe_print("error happended %s" % e)
                #traceback.print_exc()
                #continue
            finally:
                self.store.task_done()

    def __ungzip(self, content):
        cs = StringIO.StringIO(content)
        gzipper = gzip.GzipFile(fileobj=cs)
        return gzipper.read()
            
    def get_content(self, job):
        '''
        use urllib to download the file
        '''
        url = job.get_joined_link()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1667.0 Safari/537.36"}

        request = Request(url, None, headers)

        fh = urllib2.urlopen(request, timeout = 60 * 2)
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

        if ('Content-Encoding' in fh.headers) and (con_type == 'text/html'):
            if fh.headers['Content-Encoding'] == 'gzip':
                content = self.__ungzip(content)

        if con_type in Downloader.white_lists:
            return (content, con_type)
        else:
            safe_print(con_type)
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

class Checker:
    MAX_POOL_SIZE = 1024 * 10
    def __init__(self, checker_place):

        self.checker_place = path.join(checker_place, ".gwd", "checker")
        if not path.isdir(self.checker_place):
            os.makedirs(self.checker_place)

        self.mutex = threading.Lock()  
        self.pool = set()
        self.second_pool = set()
        self.cur_file_num = -1
        self.file_base_name = "checker_file_"
    def add(self, v):
        if self.check(v):
            return

        try:
            self.mutex.acquire()

            if len(self.pool) >= Checker.MAX_POOL_SIZE / len(v):
                if len(self.second_pool) != 0:
                    self.__dump_pool(self.second_pool)
                    gc.collect()
            
                self.second_pool = self.pool
                self.pool = set()

            self.pool.add(v)
        finally:
            self.mutex.release()

    def check(self, v):
        try:
            self.mutex.acquire()

            if v in self.pool or v in self.second_pool:
                return True
            if self.cur_file_num == -1:
                return False

            for i in xrange(self.cur_file_num, -1, -1):
                p = self.__load_pool(i)
                if v in p:
                    return True

            return False
        finally:
            self.mutex.release()

    def __load_pool(self, num):
        f = open(self.__get_file_path(num), 'r')
        ret = pickle.load(f)
        f.close()
        return ret

    def __dump_pool(self, p):
        self.cur_file_num += 1

        f = open(self.__get_file_path(self.cur_file_num), 'w')
        pickle.dump(p, f, pickle.HIGHEST_PROTOCOL)
        f.close()

    def __get_file_path(self, num):
        return path.join(self.checker_place, "%s%d" % (self.file_base_name, num))

class Store(Queue):
    '''
    a wrapper class to Queue.Queue, so we can control the get and put process
    '''
    def __init__(self, store_path):
        Queue.__init__(self)
        self.store_path = store_path
        self.whitelist = WhiteList()
        self.blacklist = BlackList()

        self.checker = Checker(store_path)

    def put(self, job):
        if self.pass_filters(job):
            Queue.put(self, job)

    def get(self):
        while True:
            '''
            if Queue.empty(self):
                raise StoreEmptyError()
            '''

            job = Queue.get(self, True, 0.01)

            if not self.checker.check(job.get_id()):
                return job
            else:
                self.task_done()

    def mark_as_done(self, job):
        self.checker.add(job.get_id())

    def get_store_path(self):
        return self.store_path

    def add_white_filter(self, *args):
        for arg in args:
            if arg == "{image}":
                self.whitelist.add_filter("\.(jpg|jpeg|gif|png)([?#]|$)")
            elif arg == "{css}":
                self.whitelist.add_filter("\.css([?#]|$)")
            elif arg == "{javascript}":
                self.whitelist.add_filter("\.js([?#]|$)")
            else:
                self.whitelist.add_filter(arg)

    def add_black_filter(self, *args):
        for arg in args:
            if arg == "{image}":
                self.blacklist.add_filter("\.(jpg|jpeg|gif|png)([?#]|$)")
            elif arg == "{css}":
                self.blacklist.add_filter("\.css([?#]|$)")
            elif arg == "{javascript}":
                self.blacklist.add_filter("\.js([?#]|$)")
            else:
                self.blacklist.add_filter(arg)

    def pass_filters(self, job):
        link = job.get_joined_link()
        if self.blacklist.passed(link):
            if self.whitelist.passed(link):
                return True
            else:
                return False
        else:
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
            safe_print(e)
            #traceback.print_exc()
            thread.exit()

    def kill(self):
        self.downloader.kill()

class JoinThread(threading.Thread):
    def __init__(self, store):
        Thread.__init__(self)
        self.daemon = True
        self.store = store
        
    def run(self):
        self.store.join()
        DHManager.all_is_done = True

class DHManager:
    '''
    manage download thread. try to brint up exited download thread if the total downloading job is not finished yet
    '''
    bringup_time = 30
    all_is_done = False
    def __init__(self, store, mem_inst, th_count):
        self.dhs = []
        self.original_count = th_count
        self.first_die_time = None
        self.store = store
        self.mem_inst = mem_inst
        self.exit = False
        self.killcmd_issued = False
        self.join_th = JoinThread(self.store)

        for i in range(0, th_count):
            self.dhs.append(DH(store, mem_inst))
            self.dhs[-1].start()

        self.join_th.start()

        safe_print("At %s, we are now downloading..." % (datetime.now().strftime(DATEFMT)))

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
    
            time.sleep(0.1)

    def kill(self):
        for dh in self.dhs:
            dh.kill()

        safe_print("%d thread need to be killed, please wait." % len(self.dhs))

        while True:
            for dh in self.dhs:
                if not dh.is_alive():
                    self.dhs.remove(dh)
                    sys.stdout.write(".")

            if len(self.dhs) == 0:
                break
            time.sleep(0.0001)
        
        safe_print("done")

def main():
    start_time = datetime.now()
    download_path = '../iOS_Library'
    try:
        store = Store(download_path)
    except StoreError, e:
        safe_print(e)
        sys.exit(1)

    mem_inst = Memory(download_path)

    #store.add_white_filter("\.163\.com",
    #                "cache\.netease\.com",
    #                "\.126\.net",
    #                )
    #store.put(Job("http://www.163.com"))

    store.add_white_filter("www\.bxwx\.org\/b\/62\/62724\/",
            "\.css");

    #store.put(Job("http://www.bxwx.org/b/62/62724/index.html"));

    #store.add_white_filter("docs\.python\.org")
    #store.add_black_filter("docs\.python\.org/download")
    #store.put(Job("http://docs.python.org"))

    #store.put(Job("http://docs.python.org"))

    #store.add_white_filter("\.cnbeta\.com", "{image}")
    #store.add_white_filter("www\.lua\.org\/pil\/", "{image}", "\.css")
    #store.put(Job("http://www.lua.org/pil/index.html"))

    store.add_black_filter("\.pdf([?#]|$)", "\.zip([?#]|$)")
    store.add_white_filter("developer\.apple\.com\/library\/ios", "{image}", "{css}", "{javascript}")
    store.put(Job("https://developer.apple.com/library/ios/documentation/LanguagesUtilities/Conceptual/iTunesConnect_Guide/Chapters/About.html#//apple_ref/doc/uid/TP40011225"))

    dh_manager = None
    try:
        dh_manager = DHManager(store, mem_inst, 30)
        dh_manager.wait_for_all_exit()
    except KeyboardInterrupt:
        if dh_manager != None:
            dh_manager.kill()

    end_time = datetime.now()
    safe_print("download finished, takes %s" % (end_time - start_time))

def on_sigint(signum, frame):
    #after = hp.heap()
    #print after
    os._exit(signum)
        
if __name__ == '__main__':
    signal.signal(signal.SIGINT, on_sigint)
    main() 
