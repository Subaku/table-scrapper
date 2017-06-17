# -*- coding: utf-8 -*-

# Incomming messages will differentiate by type: Mentions are
# praw.objects.Comment.  PM will me praw.objects.Message.  (And OP
# items will be praw.objects.Submission)

# If a link is to a comment, get_submission resolves the OP with one
# comment (the actual comment linked), even if it is greater than one
# generation deep in comments.

# To add: Look for tables that are actual tables.
# Look for keyword ROLL in tables and scan for arbitrary depth

from __future__ import unicode_literals
# try:
#     import simplejson as json
# except ImportError:
import json

import sys
import os
import time
import re

import praw
from utils import lprint, pprint
from table_sources import TableSource, Request

try:
    full_path = os.path.abspath(__file__)
    root_dir = os.path.dirname(full_path)
    os.chdir(root_dir)
except:
    pass

##################
# Some constants #
##################
# TODO: This should be a config file.
_version="1.4.1"
_last_updated="2016-04-18"

_seen_max_len = 50
_fetch_limit = 1000

_log_dir = "./logs"

_trivial_passes_per_heartbeat = 30


def main(debug=False, search_word=''):
    '''main(debug=False)
    Logs into Reddit, looks for unanswered user mentions, and
    generates and posts replies

    '''
    # Initialize
    lprint("Begin main()")
    seen_by_sentinel = []
    # Core loop
    while True:
        try:
            lprint("Signing into Reddit.")
            r = sign_in()
            lprint('Read only mode? {}'.format(r.read_only))
            # print r.user.me()
            trivial_passes_count = _trivial_passes_per_heartbeat - 1
            while True:
                # was_mail = process_mail(r)
                was_mail = False
                was_sub = scan_submissions(seen_by_sentinel, r, search_word)
                trivial_passes_count += 1 if not was_mail and not was_sub else 0
                if trivial_passes_count == _trivial_passes_per_heartbeat:
                    lprint("Heartbeat.  {} passes without incident (or first pass).".format(_trivial_passes_per_heartbeat))
                    trivial_passes_count = 0
                time.sleep(_sleep_between_checks)
        except Exception as e:
            lprint("Top level.  Allowing to die for cron to revive.")
            lprint("Error: {}".format(e))
            raise
        # We would like to avoid large caching and delayed logging.
        sys.stdout.flush()


# Returns true if anything happened
def scan_submissions(seen, r, search_word):
    '''This function groups the following:
    * Get the newest submissions to /r/DnDBehindTheStreen
    * Attempt to parse the item as containing tables
    * If tables are detected, post a top-level comment requesting that
      table rolls be performed there for readability
    # * Update list of seen tables
    # * Prune seen tables list if large.

    '''
    try:
        # keep_it_tidy_reply = (
        #     "It looks like this post has some tables I might be able to parse."
        #     "  To keep things tidy and not detract from actual discussion"
        #     " of these tables, please make your /u/roll_one_for_me requests"
        #     " as children to this comment." +
        #     BeepBoop() )
        BtS = r.subreddit('DnDBehindTheScreen')
        new_subs = BtS.new(limit=_fetch_limit)
        saw_something_said_something = False
        for item in new_subs:
            TS = TableSource(item, "scan")
            if TS.tables:
                lprint('Found tables, maybe, for submission {}'
                       .format(TS.source.url))
                if search_word:
                    lprint('Searching found tables for search word {}'
                           .format(search_word))

                matching_table = get_table(TS.tables, search_word)
                if matching_table:
                    lprint('Found table for search word {}'.format(search_word))
                    lprint(matching_table.for_json())
                # lprint(TS.tables)
                top_level_authors = [com.author for com in TS.source.comments]
                # Check if I have already replied
                if not TS.source in seen:
                    seen.append(TS.source)
                    # if not r.user in top_level_authors:
                        # lprint('DEBUG: Not adding comment to post.')
                        # item.add_comment(keep_it_tidy_reply)
                        # lprint("Adding organizational comment to thread with title: {}".format(TS.source.title))
                        # saw_something_said_something = True

        # Prune list to max size
        seen[:] = seen[-_seen_max_len:]
        return saw_something_said_something
    except Exception as e:
        lprint("Error during submissions scan: {}".format(e))
        raise


def get_table(tables, search_term):
    if not search_term:
        return None

    for table in tables:
        # Case insensitive search
        if re.search(search_term, table.header, re.I):
            return table


def find_table(r, search_term, sub_id=None):
    if sub_id:
        submission = r.submission(id=sub_id)
        TS = TableSource(submission, "scan")
        if TS.tables:
            table = get_table(TS.tables, search_term)
            if table:
                return table
    else:
        BtS = r.subreddit('DnDBehindTheScreen')
        new_subs = BtS.new(limit=_fetch_limit)
        for item in new_subs:
            TS = TableSource(item, "scan")
            if TS.tables:
                # for table in TS.tables:
                #     pprint(table.for_json())
                table = get_table(TS.tables, search_term)
                if table:
                    return table


# returns True if anything processed
def process_mail(r):
    '''Processes notifications.  Returns True if any item was processed.'''
    my_mail = list(r.get_unread(unset_has_mail=False))
    to_process = [Request(x, r) for x in my_mail]
    for item in to_process:
        if item.is_summons() or item.is_PM():
            reply_text = item.roll()
            okay = True
            if not reply_text:
                reply_text = ("I'm sorry, but I can't find anything"
                              " that I know how to parse.\n\n")
                okay = False
            reply_text += BeepBoop()
            if len(reply_text) > 10000:
                addition = ("\n\n**This reply would exceed 10000 characters"
                            " and has been shortened.  Chaining replies is an"
                            " intended future feature.")
                clip_point = 10000 - len(addition) - len(BeepBoop()) - 200
                reply_text = reply_text[:clip_point] + addition + BeepBoop()
            item.reply(reply_text)
            lprint("{} resolving request: {}.".format(
                "Successfully" if okay else "Questionably", item))
            if not okay:
                item.log(_log_dir)
        else:
            lprint("Mail is not summons or error.  Logging item.")
            item.log(_log_dir)
        item.origin.mark_as_read()
    return ( 0 < len(to_process))


def BeepBoop():
    '''Builds and returns reply footer "Beep Boop I'm a bot..."'''
    s = "\n\n-----\n\n"
    s += ("*Beep boop I'm a bot."
          "  You can find usage and known issue details about me,"
          " as well as my source code, on"
          " [GitHub](https://github.com/PurelyApplied/roll_one_for_me)."
          "  I am maintained by /u/PurelyApplied.*" )
    s += "\n\n^(v{}; code base last updated {})".format(_version, _last_updated)
    return s


def sign_in():
    return praw.Reddit(user_agent='AWS:Table Genie:v0.0.1 (by /u/TableGenie')


def test(mens=True):
    '''test(return_mentions=True)
    if return_mentions, returns tuple (reddit_handle, list_of_all_mail, list_of_mentions)
    else, returns tuple (reddit_handle, list_of_all_mail, None)
    '''
    r = sign_in()
    my_mail = list(r.get_unread(unset_has_mail=False))
    if mens:
        mentions = list(r.get_mentions())
    else:
        mentions = None
    return r, my_mail, mentions


#TODO: Each class is poorly commented.

####################
# classes
'''Class definitions for the roll_one_for_me bot

A Request fetches the submission and top-level comments of the appropraite thread.
Each of these items become a TableSource.
A TableSource is parsed for Tables.
A Table contains many TableItems.
When a Table is rolled, the appropraite TableItems are identified.
These are then built into TableRoll objects for reporting.
'''


####################
# Some testing items
_test_table = "https://www.reddit.com/r/DnDBehindTheScreen/comments/4aqi2l/fashion_and_style/"
_test_request = "https://www.reddit.com/r/DnDBehindTheScreen/comments/4aqi2l/fashion_and_style/d12wero"
T = "This has a d12 1 one 2 two 3 thr 4 fou 5-6 fiv/six 7 sev 8 eig 9 nin 10 ten 11 ele 12 twe"

if __name__=="__main__":
    print("Current working directory:", os.getcwd() )

    if len(sys.argv) > 1:
        r = sign_in()
        # table = find_table(r, sys.argv[1])
        table = find_table(r, "caravan", "3re16q")
        print json.loads(json.dumps(table.for_json()))
        # if table:
        #     pprint(table.for_json())
        # main(search_word=sys.argv[1])
    # elif 'y' in input("Run main? >> ").lower():
        # main()
