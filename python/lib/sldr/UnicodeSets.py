#!/usr/bin/python
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the University nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

import re

hexescre = re.compile(ur"(?:\\(?:ux)\{([0-9a-fA-F]+)\}|\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})|\\x([0-9a-fA-F]{2}))")
hexgre = re.compile(ur"\\u\{([0-9a-fA-F]+)\}")
simpleescs = {
    'a' : u"\u0007",
    'b' : u"\u0008",
    't' : u"\u0009",
    'v' : u"\u000B",
    'f' : u"\u000C",
    'r' : u"\u000D",
    'n' : u"\u0010",
    '\\' : u"\u005C"
}
simpleescsre = re.compile(ur"\\([^0-9])")
groupsre = re.compile(ur"\\([0-9]+)")

def escapechar(s):
    return u"\\"+ s if s in '[]{}\\&-|^$:' else s

class UnicodeSetSequence(list):

    def __init__(self, *p, **kw):
        super(list, self).__init__(*p, **kw)
        self.groups = []

    def reverse(self):
        new = UnicodeSetSequence(self)
        l = len(self)
        new.groups = [(l-x[0], l-x[1]) for x in self.groups]
        return new


class UnicodeSet(set):
    '''A UnicodeSet is a simple set of characters also a negative attribute'''
    def __init__(self):
        self.negative = False
        self.isclass = False
        self.startgroup = False
        self.endgroup = False

    def negate(self, state):
        self.negative = state

    def setclass(self, state):
        self.isclass = state


def _expand(p, vals, ind, indval):
    if vals[i][x].startswith("\\"):
        g = p.group(int(vals[i][x][1]))
        return "".join(_expand(p, vals, i, indices[i]) for i in range(g[0], g[1]))
    else:
        return vals[i][x]

def flatten(s):
    p = parse(s)
    vals = map(sorted, p)
    lens = map(len, vals)
    num = len(vals)
    indices = [0] * num
    while True:
        for i in range(num):
            if indices[i] == lens[i] - 1:
                indices[i] = 0
            else:
                indices[i] += 1
                break
        else:
            return
        res = []
        yield u"".join(_expand(p, vals, i, x) for i, x in enumerate(indices))

def struni(s, groups):
    s = hexescre.sub(lambda m:escapechar(unichr(int(m.group(m.lastindex), 16))), s)
    s = simpleescsre.sub(lambda m:simpleescs.get(m.group(1), m.group(1)), s)
    s = groupsre.sub(lambda m:groups[int(m.group(1)) - 1], s)
    return s

def parse(s):
    '''Returns a sequence of UnicodeSet'''
    # convert escapes
    s = hexescre.sub(lambda m:escapechar(unichr(int(m.group(m.lastindex), 16))), s)
    # don't flatten \\ escapes here since we need to differentiate with action chars {}[]
    s = hexgre.sub(lambda m:"{"+u"".join(escapechar(unichr(int(x, 16))) for x in m.group(1).split())+"}", s)
    s = s.replace(' ', '')
    res = UnicodeSetSequence()
    i = 0
    currgroup = -1
    while i < len(s):
        (i, item, nextitem) = parseitem(s, i, None, len(s))
        # a sequence can't have binary operators in it
        if nextitem.startgroup:
            currgroup = len(res)
        elif nextitem.endgroup:
            res.groups.append((currgroup, len(res)))
        if len(nextitem):
            res.append(nextitem)
    return res

def parseitem(s, ind, lastitem, end):
    '''Parses a single UnicodeSet or character. Doesn't handle property sets or variables, yet.'''
    if ind == end:
        return (end, lastitem, None)
    res = UnicodeSet()
    if s[ind] == '[':
        ind += 1
        if s[ind] == '^':
            res.negate(True)
            ind += 1
        item = None
        res.setclass(True)
        e = s.index(']', ind+1)
        while e > 0 and s[e-1] == '\\':
            e = s.index(']', e+1)
        while ind < e:
            (ind, item, nextitem) = parseitem(s, ind, item, e)
            if item:
                res.update(item)
            item = nextitem
        if item:
            res.update(item)
        ind += 1
    elif s[ind] in '|&-':
        op = s[ind]
        ind += 1
        if lastitem is None:        # treat as char
            res.add(op)
        else:
            (ind, _, item) = parseitem(s, ind, None, end)
            if op == '|' and lastitem and item:
                if lastitem.negative:
                    if item.negative:
                        res = lastitem & item
                    else:
                        res = lastitem - item
                elif item.negative:
                    res = item - lastitem
                    res.negate(True)
                else:
                    res = item + lastitem
                lastitem = None
            elif op == '&' and lastitem and item:
                if lastitem.negative:
                    if item.negative:
                        res = item + lastitem
                    else:
                        res = item - lastitem
                elif item.negative:
                    res = lastitem - item
                else:
                    res = item & lastitem
                lastitem = None
            elif op == '-':
                # set difference
                if lastitem and item and lastitem.isclass and item.isclass:
                    if lastitem.negative:
                        if item.negative:
                            res = item - lastitem
                        else:
                            res = lastitem | item
                    elif item.negative:
                        res = lastitem & item
                    else:
                        res = lastitem - item
                    lastitem = None
                # char range
                elif lastitem and item and len(lastitem) == 1 and len(item) == 1:
                    for x in range(ord(lastitem.pop()), ord(item.pop())):
                        res.add(unichr(x))
                    lastitem = None
                else:
                    res.add(u"-")
            else:
                res.add(op)
    elif s[ind] == '{':
        e = s.index('}', ind+1)
        while e > 0 and s[e-1] == '\\':
            e = s.index('}', e+1)
        res.add(simpleescsre.sub(lambda m:simpleescs.get(m.group(1), m.group(1)), s))
        ind = e + 1
    elif s[ind] == '\\':
        x = s[ind+1]
        try:
            y = int(x)
            res.add(u"\\"+x)
        except:
            res.add(simpleescs.get(x, x))
        ind += 2
    elif s[ind] == '(':
        res.startgroup = True
        ind += 1
    elif s[ind] == ')':
        res.endgroup = True
        ind += 1
    else:
        res.add(s[ind])
        ind += 1
    return (ind, lastitem, res)

