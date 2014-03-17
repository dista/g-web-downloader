from processer import Processer
from HTMLParser import HTMLParser
import sys
import re

class ExtractBookProcesser(Processer, HTMLParser):

    content_encoding_regex = re.compile(r" charset=(\w+)")

    def __init__(self):
        HTMLParser.__init__(self)
        self.rules = {}
        self.rules['title'] = {
                'css': '#maininfo #info h1',
                'idx':  -1,
                'content': [],
                'match_once': True
                }
        self.rules['title']['ids'] = self.process_selector(self.rules['title']['css'])

        self.tags = []

    def process_selector(self, selector):
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
            if m in attrs.split(' '):
                return True

        return False

    def handle_starttag(self, tag, attrs):
        self.tags.append((1, []))
        for n,rule in self.rules:
            if rule['idx'] == -2:
                continue
            if (rule['idx'] + 1) >= len(rule['ids']):
                continue
            ri = rule['ids'][rule['idx'] + 1]
            if (ri[0] == 'tag' and tag == ri[1]) \
               or (ri[0] == 'id' and is_id_in_attrs(attrs)) \
               or (ri[0] == 'class' and is_class_in_attrs(attrs)):
                rule['idx'] += 1
                self.tags[-1][1].append(rule)

    def handle_endtag(self, tag):
        tag = self.tags[-1]
        tag[0] -= 1

        if tag[0] != 0:
            return

        for rule in tag[1]:
            if rule['idx'] != -2:
                rule['idx'] -= 1

        del self.tags[-1]    

    def handle_data(self, data):
        for n, rule in self.rules:
            if (len(rule['ids']) > 0) and (rule['idx'] == (len(rule['ids']) - 1)):
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

        content = self.content2UTF8(content)

        open("/tmp/xxx", "w+").write(content)

        self.feed(content);
        sys.exit(0) 
