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
        self.chapter_got = False
        self.last_tag = None
        self.root_dir = "/tmp/pp"

        self.tags = []

    def __can_process_none_content_data(self):
        return (not self.chapter_got)

    def __on_html_finished(self, rules):
        if self.__can_process_none_content_data():
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

    def __create_rule(self, css, attribute):
        ret = {
                'css': css,
                'idx':  -1,
                'content': [],
                'attribute': attribute
              }
        ret['ids'] = self.__process_selector(ret['css'])
        return ret

    def __rebuild_ids(self):
        for rule_name in self.rules:
            self.rules[rule_name]['ids'] = self.__process_selector(self.rules[rule_name]['css']) 

    def __process_nth_child_selector(self, sub_selectors, sub):
        # http://dev.w3.org/csswg/selectors3/#nth-child-pseudo
        # 2 -- a; 5 -- b, an+b
        match = re.match(r'([\w-]+)\(((-?\d+)n)?(\+?)(\d+)?\)', sub.replace(' ', ''))
        if not match:
            raise Exception('bad n-child selector')
        sel_name = match.group(1)
        sub_selectors[sel_name] = []

        for i in [3, 5]:
            if match.group(i):
                sub_selectors[sel_name].append(int(match.group(i)))
            else:
                sub_selectors[sel_name].append(match.group(i))

    def __process_attribute_selector(self, sub_selectors, sub):
        m = re.match(r'(\w+)([~|]?)(=?)"?([:/.\w#-]*)"?', sub)
        sub_selectors['attribute'] = m.groups() 

    def __process_selector(self, selector):
        '''
            parse css selector, return a list of list.
            each list contains:
            list[0]: primal selector type, such as tag, id, class
            list[1]: primal selector value
            list[2]: optional secondary selectors. currently include: n-child
        '''

        tmp = selector.split(' ')
        processed = []
        for tc in tmp:
            sub_selectors = {}
            child_sel = None
            if ':' in tc:
                tc, child_sel = tc.split(':')
                self.__process_nth_child_selector(sub_selectors, child_sel)
            elif '[' in tc:
                s_pos1 = tc.index('[')
                s_pos2 = tc.index(']')
                tmp = tc[0:s_pos1]
                child_sel = tc[s_pos1+1:s_pos2]
                tc = tmp
                self.__process_attribute_selector(sub_selectors, child_sel)
            if tc.startswith('#'):
                processed.append(['id', tc[1:], sub_selectors])
            elif tc.startswith('.'):
                processed.append(['class', tc[1:], sub_selectors])
            else:
                processed.append(['tag', tc, sub_selectors])
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

    def __is_sub_selectors_match(self, sub_selectors, attrs):
        if 'nth-child' in sub_selectors:
            a, b = sub_selectors['nth-child'][0], sub_selectors['nth-child'][1]
            nth_child_parent = sub_selectors['nth_child_parent']
            child_idx = nth_child_parent[2]['child_idx']

            if b != None:
                child_idx -= b
            if a == None:
                return (child_idx == 0)
            else:
                return (a * child_idx >= 0) and (child_idx % a == 0)
        elif 'attribute' in sub_selectors:
            for attr in attrs:
                attr_item = sub_selectors['attribute']
                if attr[0] == attr_item[0]:
                    if attr_item[2] == '':
                        return True
                    elif attr_item[1] == '~':
                        return (attr_item[3] in attr[1].split(' '))
                    elif attr_item[1] == '|':
                        tmp = attr[1].split('-')
                        return (len(tmp) > 1 and attr_item[3] == tmp[0])
                    else:
                        return attr_item[3] == attr[1]

        return True

    def __is_primal_selector_match(self, ri, tag, attrs):
        if (ri[0] == 'tag' and tag == ri[1]) \
           or (ri[0] == 'id' and self.is_id_in_attrs(ri[1], attrs)) \
           or (ri[0] == 'class' and self.is_class_in_attrs(ri[1], attrs)):
               return True
        return False

    def __is_selectors_match(self, ri, tag, attrs):
        return self.__is_primal_selector_match(ri, tag, attrs) and \
               self.__is_sub_selectors_match(ri[2], attrs)
    
    def __rule_has_child_selector(self, ids, idx, is_next):
        if is_next:
            idx += 1
        if idx >= len(ids):
            return False

        ri = ids[idx]
        if 'nth-child' in ri[2]:
            return True

        return False

    def handle_starttag(self, tag, attrs):
        self.last_tag = tag
        #print '%s<%s>' % (len(self.tags) * ' ', tag)
        self.tags.append([1, [], {}])
        for n in self.rules:
            rule = self.rules[n]
            if (rule['idx'] + 1) >= len(rule['ids']):
                continue
            ri = rule['ids'][rule['idx'] + 1]

            # count parent children
            if self.__is_primal_selector_match(ri, tag, attrs) and\
               self.__rule_has_child_selector(rule['ids'], rule['idx'], True):
                   ri[2]['nth_child_parent'][2]['child_idx'] += 1

            if self.__is_selectors_match(ri, tag, attrs):
                rule['idx'] += 1
                if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)) \
                    and rule['attribute']:
                    if n == 'content' or self.__can_process_none_content_data():
                        rule['content'].append(self.__get_attribute(rule['attribute'], attrs))
                self.tags[-1][1].append(rule)
                
                if self.__rule_has_child_selector(rule['ids'], rule['idx'], True):
                    self.tags[-1][2]['child_idx'] = 0
                    rule['ids'][rule['idx'] + 1][2]['nth_child_parent'] = self.tags[-1]


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
            rule['idx'] -= 1

        del self.tags[-1]    

        if len(self.tags) == 0:
            self.__on_html_finished(self.rules)

    def handle_data(self, data):
        #print data
        for n in self.rules:
            rule = self.rules[n]
            #print rule
            if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)) \
                and not rule['attribute']:
                if 'start_handler' in rule:
                    rule['start_handler'](self.rules)
                data = data.translate(None, '\r\n')
                if len(data) > 0 and (n == 'content' or self.__can_process_none_content_data()):
                    rule['content'].append(data)

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

    def __clean_process_tmp_data(self):
        for rule_name in self.rules:
            self.rules[rule_name]['idx'] = -1
            for selectors in self.rules[rule_name]['ids']:
                selectors[2] = {}

    def __write_sync_data(self):
        sync_data_file = open(self.__get_sync_data_file_path(), 'w+')
        # FIXME
        self.rules['volume']['start_handler'] = None
        json.dump(self.rules, sync_data_file, indent=True)
        sync_data_file.close()

    def __assign_rule(self, job):
        rule = None
        for website in ExtractBookProcesser.website_rules:
            if website in job.get_joined_link():
                rule = ExtractBookProcesser.website_rules[website]
                break
        if not rule:
            raise Exception('no rule found for job')

        self.rules['title'] = self.__create_rule(rule['title'], None)
        self.rules['chapters'] = self.__create_rule(rule['chapters'], None)
        self.rules['chapter_links'] = self.__create_rule(rule['chapter_links'], 'href')
        self.rules['volume'] = self.__create_rule(rule['volume'], None)
        self.rules['volume']['start_handler'] = self.__on_volume_start
        self.rules['content'] = self.__create_rule(rule['content'], None) 

    def do_process(self, job, c_t, content):
        if c_t not in ['text/html']:
            return

        if not self.rule_assigned:
            self.__assign_rule(job)
            self.rule_assigned = True
        else:
            self.rules['content'] = self.__create_rule(rule['content'], None) 

        if os.path.isfile(self.__get_sync_data_file_path()):
            self.chapter_got = True
            self.rules = json.load(open(self.__get_sync_data_file_path()))
            self.__rebuild_ids()
            self.rules['volume']['start_handler'] = self.__on_volume_start

        content = self.content2UTF8(content)
        #open("/tmp/xxx", "w+").write(content)
        #os._exit(1)

        #self.rules['content'] = self.__create_rule('#content', False, None) 
        #content = open("/tmp/xxx", "r").read();
        content = content.replace('&nbsp;', '');

        self.feed(content);
        #print self.rules

        self.__clean_process_tmp_data()

        #for itm in self.rules['chapter_links']['content']:
        #    print itm
        #print len(self.rules['chapters']['content'])

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
