import time
from pprint import PrettyPrinter

import praw


pp = PrettyPrinter(indent=1, depth=8)


def lprint(l):
    '''Prints, prepending time to message'''
    t = time.strftime("%y %m (%b) %d (%a) %H:%M:%S")
    print ("{}: {}".format(t, l))


def pprint(obj):
    pp.pprint(obj)


def ioencode(s):
    return s.encode('utf8')


def fdate():
    return "-".join(str(x) for x in time.gmtime()[:6])


# Used by both Request and TableSource ; should perhaps depricate this
# and give each class its own method
def get_post_text(post):
    '''Returns text to parse from either Comment or Submission'''
    if type(post) == praw.models.Comment:
        return post.body
    elif type(post) == praw.models.Submission:
        return post.selftext
    else:
        lprint("Attempt to get post text from"
               " non-Comment / non-Submission post; returning empty string")
        return ""
