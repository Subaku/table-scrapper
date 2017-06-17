import re
import random
import string

from utils import ioencode, lprint

_last_updated = "2016-04-18"

_seen_max_len = 50
_fetch_limit = 101

_trash = string.punctuation + string.whitespace

_header_regex = "^(\d+)?[dD](\d+)(.*)"
_line_regex = "^(\d+)(\s*-+\s*\d+)?(.*)"
_summons_regex = "u/roll_one_for_me"

_mentions_attempts = 10
_answer_attempts = 10

_sleep_on_error = 10
_sleep_between_checks = 60

_log_dir = "./logs"

_trivial_passes_per_heartbeat = 30


class Table(object):
    '''Container for a single set of TableItem objects
    A single post will likely contain many Table objects'''
    def __init__(self, text):
        self.text = text
        self.die = None
        self.header = ""
        self.outcomes = []
        self.is_inline = False

        self._parse()

    def __repr__(self):
        return ioencode('<Table with header: {}>'.format(self.header))

    def for_json(self):
        return dict(
            die=self.die,
            header=self.header,
            items=[t.for_json() for t in self.outcomes]
        )

    def _parse(self):
        lines = self.text.split('\n')
        head = lines.pop(0)
        head_match = re.search(_header_regex, head.strip(_trash))
        if head_match:
            self.die = int(head_match.group(2))
            self.header = head_match.group(3)
        self.outcomes = [TableItem(l) for l in lines if re.search(_line_regex, l.strip(_trash))]

    def roll(self):
        try:
            weights = [i.weight for i in self.outcomes]
            total_weight = sum(weights)
            if self.die != total_weight:
                self.header = "[Table roll error: parsed die did not match sum of item wieghts.]  \n" + self.header
            c = random.randint(1, self.die)
            scan = c
            ind = -1
            while scan > 0:
                ind += 1
                scan -= weights[ind]

            R = TableRoll(d=self.die,
                          rolled=c,
                          head=self.header,
                          out=self.outcomes[ind])
            if len(self.outcomes) != self.die:
                R.error('Expected {} items found {}'.format(self.die, len(self.outcomes)))
            return R
        # TODO: Handle errors more gracefully.
        except Exception as e:
            lprint('Exception in Table roll ({}): {}'.format(self, e))
            return None


class TableItem(object):
    '''This class allows simple handling of in-line subtables'''
    def __init__(self, text, w=0):
        self.text = text
        self.inline_table = None
        self.outcome = ""
        self.weight = 0

        self._parse()

        # If parsing fails, particularly in inline-tables, we may want
        # to explicitly set weights
        if w:
            self.weight = w

    def __repr__(self):
        inline_str = "; has inline table" if self.inline_table else ""
        return ioencode('<TableItem: {}{}>'.format(self.outcome, inline_str))

    def for_json(self):
        if self.inline_table:
            return self.inline_table.for_json()
        return dict(
            value=self.outcome,
            weight=self.weight)

    def _parse(self):
        main_regex = re.search(_line_regex, self.text.strip(_trash))
        if not main_regex:
            return
        # Grab outcome
        self.outcome = main_regex.group(3).strip(_trash)
        # Get weight / ranges
        if not main_regex.group(2):
            self.weight = 1
        else:
            try:
                start = int(main_regex.group(1).strip(_trash))
                stop = int(main_regex.group(2).strip(_trash))
                self.weight = stop - start + 1
            except:
                self.weight = 1
        # Identify if there is a subtable
        if re.search("[dD]\d+", self.outcome):
            die_regex = re.search("[dD]\d+", self.outcome)
            try:
                self.inline_table = InlineTable(self.outcome[die_regex.start():])
            except RuntimeError as e:
                lprint("Error in inline_table parsing ; table item full text:")
                lprint(self.text)
                lprint(e)
                self.outcome = self.outcome[:die_regex.start()].strip(_trash)
        # this might be redundant
        self.outcome = self.outcome.strip(_trash)

    def get(self):
        if self.inline_table:
            return self.outcome + self.inline_table.roll()
        else:
            return self.outcome


class InlineTable(Table):
    '''A Table object whose text is parsed in one line, instead of expecting line breaks'''
    def __init__(self, text):
        super(InlineTable, self).__init__(text)
        self.is_inline = True

    def __repr__(self):
        return ioencode('<d{} Inline table>'.format(self.die))

    def _parse(self):
        top = re.search("[dD](\d+)(.*)", self.text)
        if not top:
            return

        self.die = int(top.group(1))
        tail = top.group(2)
        while tail:
            in_match = re.search(_line_regex, tail.strip(_trash))
            if not in_match:
                lprint("Could not complete parsing InlineTable; in_match did not catch.")
                lprint("Returning blank roll area.")
                self.outcomes = [TableItem("1-{}. N/A".format(self.die))]
                return
            this_out = in_match.group(3)
            next_match = re.search(_line_regex[1:], this_out)
            if next_match:
                tail = this_out[next_match.start():]
                this_out = this_out[:next_match.start()]
            else:
                tail = ""

            TI_text = in_match.group(1) + (in_match.group(2) if in_match.group(2) else "") + this_out
            try:
                self.outcomes.append(TableItem(TI_text))
            except Exception as e:
                lprint("Error building TableItem in inline table; item skipped.")
                lprint("Exception:", e)


class TableRoll(object):
    def __init__(self, d, rolled, head, out, err=None):
        self.d = d
        self.rolled = rolled
        self.head = head
        self.out = out
        self.sub = out.inline_table
        self.err = err

        if self.sub:
            self.sob_out = self.sub.roll()

    def __repr__(self):
        return ioencode('<d{} TableRoll: {}>'.format(self.d, self.head))

    def error(self, e):
        self.err = e

    def unpack(self):
        ret = "{}...    \n".format(self.head.strip(_trash))
        ret += "(d{} -> {}) {}.    \n".format(self.d, self.rolled, self.out.outcome)
        if self.sub:
            ret += "Subtable: {}".format(self.sub.roll().unpack())
        ret += "\n\n"
        return ret
