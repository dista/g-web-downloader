from processer import Processer
from HTMLParser import HTMLParser
import sys
import re
import os
from job import Job
import json

class ExtractBookProcesser(Processer, HTMLParser):

    content_encoding_regex = re.compile(r" charset=(\w+)")
    current_dir = os.path.dirname(os.path.realpath(__file__))
    website_rules = json.load(open('%s/website_rules.json' % current_dir, 'r'))

    def __init__(self):
        HTMLParser.__init__(self)
        self.rule_assigned = False
        self.rules = {}
        #self.rules['title'] = self.__create_rule('#maininfo #info h1', True, None)
        #self.rules['chapters'] = self.__create_rule('#list dd a', False, None)
        #self.rules['chapter_links'] = self.__create_rule('#list dd a', False, 'href')
        #self.rules['volume'] = self.__create_rule('#list dt', False, None)

        self.chapter_got = False
        self.last_tag = None
        self.root_dir = "/tmp/pp"

        self.tags = []

    def __on_html_finished(self, rules):
        rule = rules['volume']
        chapters_rule = rules['chapters']

        if 'chapters' in rule and len(rule['chapters']) > 0:
            last = rule['chapters'][-1]
            if last['end'] == -1:
                last['end'] = len(chapters_rule['content']) - 1

    def __on_volume_start(self, rules):
        rule = rules['volume']
        chapters_rule = rules['chapters']
        if not 'chapters' in rule:
            rule['chapters'] = []

        last = None
        if len(rule['chapters']) > 0:
            last = rule['chapters'][-1]

        if last:
            last['end'] = len(chapters_rule['content']) - 1

        new_volume = {"start": len(chapters_rule['content']), "end": -1}

        rule['chapters'].append(new_volume)

    def __create_rule(self, css, match_once, attribute):
        ret = {
                'css': css,
                'idx':  -1,
                'content': [],
                'match_once': match_once,
                'attribute': attribute
              }
        ret['ids'] = self.__process_selector(ret['css'])
        return ret

    def __process_selector(self, selector):
        tmp = selector.split(' ')
        processed = []
        for tc in tmp:
            if tc.startswith('#'):
                processed.append(('id', tc[1:]))
            elif tc.startswith('.'):
                processed.append(('class', tc[1:]))
            else:
                processed.append(('tag', tc))
        return processed

    def is_id_in_attrs(self, m, attrs):
        return self.is_item_in_attrs(m, attrs, 'id')

    def is_class_in_attrs(self, m, attrs):
        return self.is_item_in_attrs(m, attrs, 'class')

    def is_item_in_attrs(self, m, attrs, t):
        for attr in attrs:
            if attr[0] != t:
                continue
            if m in attr[1].split(' '):
                return True

        return False

    def __get_attribute(self, attr, attrs):
        for item in attrs:
            if item[0] == attr:
                return item[1]

        return None

    def handle_starttag(self, tag, attrs):
        self.last_tag = tag
        #print '%s<%s>' % (len(self.tags) * ' ', tag)
        self.tags.append([1, []])
        for n in self.rules:
            rule = self.rules[n]
            if rule['idx'] == -2:
                continue
            if (rule['idx'] + 1) >= len(rule['ids']):
                continue
            ri = rule['ids'][rule['idx'] + 1]
            if (ri[0] == 'tag' and tag == ri[1]) \
               or (ri[0] == 'id' and self.is_id_in_attrs(ri[1], attrs)) \
               or (ri[0] == 'class' and self.is_class_in_attrs(ri[1], attrs)):
                rule['idx'] += 1
                if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)) \
                    and rule['attribute']:
                    rule['content'].append(self.__get_attribute(rule['attribute'], attrs))
                    if rule['match_once']:
                        rule['idx'] = -2
                self.tags[-1][1].append(rule)

    def handle_endtag(self, tag):
        #invalid tag
        if tag != self.last_tag:
            return
        #print '%s</%s>' % ((len(self.tags) - 1) * ' ', tag)
        tag = self.tags[-1]
        #print tag
        tag[0] -= 1

        if tag[0] != 0:
            return

        for rule in tag[1]:
            if rule['idx'] != -2:
                rule['idx'] -= 1

        del self.tags[-1]    

        if len(self.tags) == 0:
            self.__on_html_finished(self.rules)

    def handle_data(self, data):
        print data
        for n in self.rules:
            rule = self.rules[n]
            #print rule
            if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)) \
                and not rule['attribute']:
                if 'start_handler' in rule:
                    rule['start_handler'](self.rules)
                data = data.translate(None, '\r\n')
                if len(data) > 0:
                    rule['content'].append(data)
                if rule['match_once']:
                    rule['idx'] = -2

    def get_content_encoding(self, content):
        match = ExtractBookProcesser.content_encoding_regex.search(content)

        if match:
            return match.group(1).upper()
        else:
            return "UTF-8"

    def content2UTF8(self, content):
        charset = self.get_content_encoding(content)
        if charset != "UTF-8":
            content = content.decode(charset).encode('UTF-8')

        return content

    def __post_process_volumes(self, job):
        if len(self.rules['chapter_links']['content']) > 0:
            self.chapter_got = True
        for i in xrange(len(self.rules['chapter_links']['content'])):
            link = self.rules['chapter_links']['content'][i]
            inner_job = Job(link, job.get_joined_link())
            self.rules['chapter_links']['content'][i] = inner_job.get_joined_link()

        self.__write_catalog()

    def __write_catalog(self):
        volume_index = 0
        write_chapters = []
        cc = self.rules['chapters']['content']
        cl = self.rules['chapter_links']['content']

        f = open(self.root_dir + '/' + 'catelog', 'w+')
        volume_chapters = []
        vc_len = len(self.rules['volume']['content'])
        for volume in self.rules['volume']['content']:
            #if volume_index == 0:
            #    volume_index += 1
            #    continue

            f.write(volume + '\n')
            
            if not os.path.isdir("%s/%s" % (self.root_dir, volume)):
                os.mkdir("%s/%s" % (self.root_dir, volume))

            chapters = self.rules['volume']['chapters'][volume_index]

            volume_chapters = []
            for i in xrange(chapters['start'], chapters['end']):
                if not cc[i] in write_chapters:
                    write_chapters.append(cc[i])
                    volume_chapters.append(cc[i])

            #if volume_index != (vc_len - 1):
            #    f.write("%d\n" % len(volume_chapters))
            #    for c in volume_chapters:
            #        f.write("%s\n" % c)
            f.write("%d\n" % len(volume_chapters))
            for c in volume_chapters:
                f.write("%s\n" % c)
            volume_index += 1
        
        '''
        if volume_index != 0:
            chapters = self.rules['volume']['chapters'][0]
            for i in xrange(chapters['start'], chapters['end']):
                if not cc[i] in write_chapters:
                    write_chapters.append(cc[i])
                    volume_chapters.append(cc[i])
            f.write("%d\n" % len(volume_chapters))
            for c in volume_chapters:
                f.write("%s\n" % c)
        '''

        f.close()

    def __get_content_path(self, ct_idx):
        cn = self.rules['chapters']['content'][ct_idx]
        cc = None
        for ci in xrange(len(self.rules['volume']['chapters'])):
            c = self.rules['volume']['chapters'][ci]
            vn = self.rules['volume']['content'][ci]
            if (ct_idx >= c['start']) and (ct_idx <= c['end']):
                #if ci == 0:
                #    cc = self.rules['volume']['content'][-1]
                #else:
                #    cc = vn
                cc = vn
                break

        if cc == None:
            raise Exception('error in get_content_path')
        return "%s/%s/%s" % (self.root_dir, cc, cn)

    def __post_process_content(self, job, content):
        try:
            pos = self.rules['chapter_links']['content'].index(job.get_joined_link())
            content_path = self.__get_content_path(pos)
            print content_path
            f = open(content_path, 'w+')
            for i in self.rules['content']['content']:
                f.write('%s\n' % i)
            f.close()
                
        except ValueError:
            pass

    def __get_sync_data_file_path(self):
        return '%s/%s' % (self.root_dir, 'sync.json')

    def __write_sync_data(self):
        sync_data_file = open(self.__get_sync_data_file_path(), 'w+')
        # FIXME
        self.rules['volume']['start_handler'] = None
        json.dump(self.rules, sync_data_file)
        sync_data_file.close()

    def __assign_rule(self, job):
        rule = None
        for website in ExtractBookProcesser.website_rules:
            if website in job.get_joined_link():
                rule = ExtractBookProcesser.website_rules[website]
                break
        if not rule:
            raise Exception('no rule found for job')

        self.rules['title'] = self.__create_rule(rule['title'], True, None)
        self.rules['chapters'] = self.__create_rule(rule['chapters'], False, None)
        self.rules['chapter_links'] = self.__create_rule(rule['chapter_links'], False, 'href')
        self.rules['volume'] = self.__create_rule(rule['volume'], False, None)
        self.rules['volume']['start_handler'] = self.__on_volume_start
        self.rules['content'] = self.__create_rule(rule['content'], False, None) 

    def do_process(self, job, c_t, content):
        if c_t not in ['text/html']:
            return

        if not self.rule_assigned:
            self.__assign_rule(job)
            self.rule_assigned = True

        if os.path.isfile(self.__get_sync_data_file_path()):
            self.chapter_got = True
            self.rules = json.load(open(self.__get_sync_data_file_path()))
            self.rules['volume']['start_handler'] = self.__on_volume_start

        content = self.content2UTF8(content)
        #open("/tmp/xxx", "w+").write(content)
        #sys.exit(1)

        #self.rules['content'] = self.__create_rule('#content', False, None) 
        #content = open("/tmp/xxx", "r").read();
        content = content.replace('&nbsp;', '');

        self.feed(content);
        #print self.rules
        #print self.rules['chapters']

        if not self.chapter_got:
            self.__post_process_volumes(job)
            self.__write_sync_data() 
        else:
            self.__post_process_content(job, content)

'''
from urllib2 import *
import hashlib
class Job:
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

p = ExtractBookProcesser();
p.do_process(Job('http://www.bxwx.org/0_82/', None), 'text/html', '');
'''
