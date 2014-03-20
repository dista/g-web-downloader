from processer import Processer
from HTMLParser import HTMLParser
import sys
import re

class ExtractBookProcesser(Processer, HTMLParser):

    content_encoding_regex = re.compile(r" charset=(\w+)")

    def __init__(self):
        HTMLParser.__init__(self)
        self.rules = {}
        self.rules['title'] = self.__create_rule('#maininfo #info h1', True)
        self.rules['chapters'] = self.__create_rule('#list dd a', False)

        self.tags = []

    def __create_rule(self, css, match_once):
        ret = {
                'css': css,
                'idx':  -1,
                'content': [],
                'match_once': match_once
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

    def handle_starttag(self, tag, attrs):
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
                self.tags[-1][1].append(rule)

    def handle_endtag(self, tag):
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

    def handle_data(self, data):
        for n in self.rules:
            rule = self.rules[n]
            #print rule
            if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)):
                print data
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

    def do_process(self, job, c_t, content):
        if c_t not in ['text/html']:
            return

        #content = self.content2UTF8(content)

        #open("/tmp/xxx", "w+").write(content)

        content = open("/tmp/xxx", "r").read();
        #content = content.replace('&nbsp;', ' ');

        self.feed(content);
        #print self.rules
        sys.exit(0)

p = ExtractBookProcesser();
p.do_process({}, 'text/html', '');
