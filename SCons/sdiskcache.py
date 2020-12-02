# MIT License
#
# Copyright The SCons Foundation
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""SConsign support for diskcache. """

import diskcache
import os
import time

DISKCACHE_SUFFIX = '.d'
DEBUG = True

class Diskcache:
    """Processing of sconsign databases using diskcache.

    This is derived from the SCons dblite module, but much simpler,
    because there's no exit processing needed - diskcache keeps a
    consistent sqlite database under the covers.  This doesn't map
    perfectly, since the implementation leaks through into the model:
    plenty of code expects the in-memory sconsign DB to not
    be backed to disk _except_ on close.

    Most of this is a thin wrapper around a diskcache.Index,
    which is stored in the _dict attribute - the "in-memory" copy.

    We do want to add a few behaviors: some instances can be
    read-only (e.g. if they are found in a repository we don't update);
    to mirror the dbm/dblite behavior of open flags, "r" and "w"
    expect the DB file to actually exist while "n" means it should
    be emptied (that is, "new"); and we want to make sure there's
    a keys method at least.

    Arguments:
        file_base_name: name of db, will get .d suffix if not present
        flag: opening mode, see Python dbm.open for description
        mode: UNIX-style mode of DB files (see dbm.open), unused in this module
    """

    _open = open  # for the exercise code to use

    def __init__(self, file_base_name: str, flag: str, mode: int):
        assert flag in (None, "r", "w", "c", "n")
        if flag is None:
            flag = "r"

        if file_base_name.endswith(DISKCACHE_SUFFIX):
            # There's already a suffix on the file name, don't add one.
            self._dir_name = file_base_name
        else:
            self._dir_name = file_base_name + DISKCACHE_SUFFIX

        if not os.path.isdir(self._dir_name) and flag in ('r', 'w'):
            raise FileNotFoundError("No such sconsign database: %s" % self._dir_name)
        self._dict = diskcache.Index(self._dir_name)
        self._writable: bool = flag not in ("r", )
        if DEBUG:
            print(f"DEBUG: opened an Index file {self._dir_name} (writable={self._writable})")
        if flag == "n":
            self.clear()

    def check(self, fix=False, retry=False):
        """Call disckache 'check' routine to verify DB."""
        self._dict.check(fix, retry)

    def close(self):
        #self._dict.close()
        pass

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        # just skip setting if db is "read-only"
        # should we raise an error instead?
        if self._writable:
            self._dict[key] = value

    def keys(self):
        #return iter(self._dict.keys())
        yield from self._dict

    def items(self):
        #return iter(self._dict.items())
        for key in self._dict:
            yield (key, self._dict[key])

    def values(self):
        #return iter(self._dict.values())
        for key in self._dict:
            yield self._dict[key]

    def has_key(self, key) -> bool:
        return key in self._dict

    def __contains__(self, key) -> bool:
        return key in self._dict

    __iter__ = keys

    def __len__(self) -> int:
        return len(self._dict)

    def clear(self):
        return self._dict.clear()

    def volume(self):
        return self._dict.volume()

    def stats(self):
        return self._dict.stats()

    def expire(self, now=None, retry=False):
        return self._dict.expir(now, retry)


def open(file, flag=None, mode=None):
    return Diskcache(file, flag, mode)


def _exercise():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # reading a nonexistent file with mode 'r' should fail
        try:
            db = open(tmp + "_", "r")
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("FileNotFoundError exception expected")

        # create mode creates db
        db = open(tmp, "c")
        assert len(db) == 0, len(db)
        db["bar"] = "foo"
        assert db["bar"] == "foo"
        assert len(db) == 1, len(db)
        db.close()

        # new database should be empty
        db = open(tmp, "n")
        assert len(db) == 0, len(db)
        db["foo"] = "bar"
        assert db["foo"] == "bar"
        assert len(db) == 1, len(db)
        db.close()

        # write mode is just normal
        db = open(tmp, "w")
        assert len(db) == 1, len(db)
        assert db["foo"] == "bar"
        db["bar"] = "foo"
        assert len(db) == 2, len(db)
        assert db["bar"] == "foo"
        db.close()

        # read-only database should silently fail to add
        db = open(tmp, "r")
        assert len(db) == 2, len(db)
        assert db["foo"] == "bar"
        assert db["bar"] == "foo"
        db["ping"] = "pong"
        assert len(db) == 2, len(db)
        try:
            v = db["ping"]
        except KeyError:
            pass
        else:
            raise RuntimeError("KeyError exception expected")
        db.close()

        # test iterators
        db = open(tmp, 'w')
        db["foobar"] = "foobar"
        assert len(db) == 3, len(db)
        expected = {"foo": "bar", "bar": "foo", "foobar": "foobar"}
        #k = [key for key in db]
        #e = sorted(expected.keys())
        #assert k == e, f"{k} != {e}"
        #k = sorted(db.keys())
        #assert k == e, f"{k} != {e}"
        #k = sorted(db.values())
        #e = sorted(expected.values())
        #assert k == e, f"{k} != {e}"
        #k = sorted(db.items())
        #e = sorted(expected.items())
        #assert k == e, f"{k} != {e}"
        k = sorted([key for key in db])
        e = sorted(expected.keys())
        assert k == e, f"{k} != {e}"
        k = sorted(db.keys())
        assert k == e, f"{k} != {e}"
        k = sorted(db.values())
        e = sorted(expected.values())
        assert k == e, f"{k} != {e}"
        k = sorted(db.items())
        e = sorted(expected.items())
        assert k == e, f"{k} != {e}"
        db.close()

    print("Completed _exercise()")


if __name__ == "__main__":
    _exercise()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
