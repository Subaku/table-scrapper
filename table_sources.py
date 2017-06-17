import re
import pickle

import praw

from tables import Table, _trash, _header_regex, _summons_regex
from utils import ioencode, get_post_text, lprint, fdate


class TableSource(object):
    def __init__(self, praw_ref, descriptor):
        self.source = praw_ref
        self.desc = descriptor
        self.tables = []

        self._parse()

    def __repr__(self):
        return ioencode('<TableSource from {}>'.format(self.desc))

    def roll(self):
        instance = [T.roll() for T in self.tables]
        # Prune failed rolls
        instance = [x for x in instance if x]
        if instance:
            ret = "From {}...\n\n".format(self.desc)
            for item in instance:
                ret += item.unpack()
            return ret
        return None

    def has_tables(self):
        return 0 < len(self.tables)

    def _parse(self):
        indices = []
        text = get_post_text(self.source)
        lines = text.split("\n")
        for line_num in range(len(lines)):
            l = lines[line_num]
            if re.search(_header_regex, l.strip(_trash)):
                indices.append(line_num)
        # TODO: if no headers found?
        if len(indices) == 0:
            return None

        table_text = []
        for i in range(len(indices) - 1):
            table_text.append("\n".join(lines[indices[i]:indices[i+1]]))
        table_text.append("\n".join(lines[indices[-1]:]))

        self.tables = [Table(t) for t in table_text]


class TableSourceFromText(TableSource):
    def __init__(self, text, descriptor):
        self.text = text
        self.desc = descriptor
        self.tables = []

        self._parse()

    # This is nearly identical to TableSource._parse ; if this is ever
    # used outside of testing, it behooves me to make a single
    # unifying method
    def _parse(self):
        indices = []
        text = self.text
        lines = text.split("\n")
        for line_num in range(len(lines)):
            l = lines[line_num]
            if re.search(_header_regex, l.strip(_trash)):
                indices.append(line_num)
        if len(indices) == 0:
            return None
        table_text = []
        for i in range(len(indices) - 1):
            table_text.append("\n".join(lines[indices[i]:indices[i+1]]))
        table_text.append("\n".join(lines[indices[-1]:]))
        self.tables = [Table(t) for t in table_text]


class Request:
    def __init__(self, praw_ref, r):
        self.origin = praw_ref
        self.reddit = r
        self.tables_sources = []
        self.outcome = None

        self._parse()

    def __repr__(self):
        return ioencode("<Request from >".format(str(self)))

    def __str__(self):
        if type(self.origin) == praw.models.Comment:
            via = "mention in {}".format(self.origin.submission.title)
        elif type(self.origin) == praw.models.Message:
            via = "private message"
        else:
            via = "a mystery!"
        return "/u/{} via {}".format(self.origin.author, via)

    def _parse(self):
        '''Fetches text of submission and top-level comments from thread
        containing this Request.  Builds a TableSource for each, and
        attempts to parse each for tables.

        '''
        # Default behavior: OP and top-level comments, as applicable
        if re.search("\[.*?\]\s*\(.*?\)", self.origin.body):
            self.get_link_sources()
        else:
            self.get_default_sources()

    def _maybe_add_source(self, source, desc):
        '''Looks at PRAW submission and adds it if tables can be found.'''
        table_source = TableSource(source, desc)
        if table_source.has_tables():
            self.tables_sources.append(table_source)

    def get_link_sources(self):
        links = re.findall("\[.*?\]\s*\(.*?\)", self.origin.body)
        for item in links:
            desc, href = re.search("\[(.*?)\]\s*\((.*?)\)", item).groups()
            href = href.strip()
            if "reddit.com" in href.lower():
                lprint("Fetching href: {}".format(href.lower()))
                if "m.reddit" in href.lower():
                    lprint("Removing mobile 'm.'")
                    href = href.lower().replace("m.reddit", "reddit", 1)
                if ".json" in href.lower():
                    lprint("Pruning .json and anything beyond.")
                    href = href[:href.find('.json')]
                if not 'www' in href.lower():
                    lprint("Injecting 'www.' to href")
                    href = href[:href.find("reddit.com")] + 'www.' + href[href.find("reddit.com"):]
                href = href.rstrip("/")
                lprint("Processing href: {}".format(href))
                self._maybe_add_source(
                    self.reddit.get_submission(href),
                    desc)

    def get_default_sources(self):
        '''Default sources are OP and top-level comments'''
        try:
            # Add OP
            self._maybe_add_source(self.origin.submission, "this thread's original post")
            # Add Top-level comments
            top_level_comments = self.reddit.get_submission(None, self.origin.submission.id).comments
            for item in top_level_comments:
                self._maybe_add_source(item, "[this]({}) comment by {}".format(item.permalink, item.author) )
        except:
            lprint("Could not add default sources.  (PM without links?)")

    def roll(self):
        instance = [TS.roll() for TS in self.tables_sources]
        instance = [x for x in instance if x]
        return "\n\n-----\n\n".join(instance)

    def reply(self, reply_text):
        self.origin.reply(reply_text)

    def is_summons(self):
        return re.search(_summons_regex, get_post_text(self.origin).lower())

    def is_PM(self):
        return type(self.origin) == praw.models.Message

    def log(self, log_dir):
        filename = "{}/rofm-{}-{}.log".format(log_dir, self.origin.author, self.origin.fullname)
        with open(filename, 'w') as f:
            f.write("Time    :  {}\n".format(fdate() ))
            f.write("Author  :  {}\n".format(self.origin.author))
            try:
                f.write("Link    :  {}\n".format(self.origin.permalink))
            except:
                f.write("Link    :  Unavailable (PM?)\n")
            f.write("Type    :  {}\n".format(type(self.origin)))
            try:
                f.write("Body    : (below)\n[Begin body]\n{}\n[End body]\n".format( get_post_text(self.origin)))
            except:
                f.write("Body    : Could not resolve message body.")
            f.write("\n")
            try:
                f.write("Submission title : {}\n".format(self.origin.submission.title))
                f.write("Submission body  : (below)\n[Begin selftext]\n{}\n[End selftext]\n".format(self.origin.submission.selftext))
            except:
                f.write("Submission: Could not resolve submission.")
        filename = filename.rstrip("log") + "pickle"
        with open(filename, 'wb') as f:
            pickle.dump(self, f)

    # This function is unused, but may be useful in future logging
    def describe_source(self):
        return "From [this]({}) post by user {}...".format(self.source.permalink, self.source.author)

