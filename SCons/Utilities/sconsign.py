#! /usr/bin/env python
#
# SCons - a Software Constructor
#
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

"""Utility script to dump information from SCons signature database."""

import getopt
import importlib
import os
import sys
from dbm import whichdb

import time
import pickle

import SCons.compat
import SCons.SConsign

DEBUG = False


def my_whichdb(filename: str) -> str:
    """Try to detect sconsign db flavor, and return the type.

    We have a couple of quick local heuristics, else fall back
    to dbm.whichdb, which can only recognize Python stdlib types.
    """
    if filename.endswith('.dblite'):
        return "SCons.dblite"
    elif filename.endswith('.sqlite') or os.path.isdir(filename + ".sqlite"):
        return "SCons.sdiskcache"
    try:
        with open(filename + ".dblite", "rb"):
            return "SCons.dblite"
    except OSError:
        pass
    return whichdb(filename)


class Flagger:
    default_value = True

    def __setitem__(self, item, value) -> None:
        self.__dict__[item] = value
        self.default_value = False

    def __getitem__(self, item):
        return self.__dict__.get(item, self.default_value)


Do_Call = None
Print_Directories = []
Print_Entries = []
Print_Flags = Flagger()
Verbose = False
Readable = False
Warns = 0
Convert_To_Diskcache = False


def default_mapper(entry, name) -> str:
    """Stringify an entry that doesn't have an explicit mapping.

    Args:
        entry:  entry
        name: field name
    """
    try:
        val = eval("entry." + name)
    except AttributeError:
        val = None
    return str(val)


def map_action(entry, _) -> str:
    """Stringify an action entry and signature.

    Args:
        entry: action entry
        second argument is not used
    """
    try:
        bact = entry.bact
        bactsig = entry.bactsig
    except AttributeError:
        return None
    return '%s [%s]' % (bactsig, bact)


def map_timestamp(entry, _) -> str:
    """Stringify a timestamp entry.

    Args:
        entry: timestamp entry
        second argument is not used
    """
    try:
        timestamp = entry.timestamp
    except AttributeError:
        timestamp = None
    if Readable and timestamp:
        return "'" + time.ctime(timestamp) + "'"
    else:
        return str(timestamp)


def map_bkids(entry, _) -> str:
    """Stringify an implicit entry.

    Args:
        entry:
        second argument is not used
    """
    try:
        bkids = entry.bsources + entry.bdepends + entry.bimplicit
        bkidsigs = entry.bsourcesigs + entry.bdependsigs + entry.bimplicitsigs
    except AttributeError:
        return None

    if len(bkids) != len(bkidsigs):
        global Warns
        Warns += 1
        # add warning to result rather than direct print so it will line up
        msg = "Warning: missing information, {} ids but {} sigs"
        result = [msg.format(len(bkids), len(bkidsigs))]
    else:
        result = []
    result += [nodeinfo_string(bkid, bkidsig, "        ")
               for bkid, bkidsig in zip(bkids, bkidsigs)]
    if not result:
        return None
    return "\n        ".join(result)


map_field = {
    'action'    : map_action,
    'timestamp' : map_timestamp,
    'bkids'     : map_bkids,
}

map_name = {
    'implicit'  : 'bkids',
}


def field(name, entry, verbose=Verbose):
    if not Print_Flags[name]:
        return None
    fieldname = map_name.get(name, name)
    mapper = map_field.get(fieldname, default_mapper)
    val = mapper(entry, name)
    if verbose:
        val = name + ": " + val
    return val


def nodeinfo_raw(name, ninfo, prefix: str=""):
    """
    This just formats the dictionary, which we would normally use str()
    to do, except that we want the keys sorted for deterministic output.
    """
    d = ninfo.__getstate__()
    try:
        keys = ninfo.field_list + ['_version_id']
    except AttributeError:
        keys = sorted(d.keys())
    values = []
    for key in keys:
        values.append('%s: %s' % (repr(key), repr(d.get(key))))
    if '\n' in name:
        name = repr(name)
    return name + ': {' + ', '.join(values) + '}'


def nodeinfo_cooked(name, ninfo, prefix: str=""):
    try:
        field_list = ninfo.field_list
    except AttributeError:
        field_list = []
    if '\n' in name:
        name = repr(name)
    outlist = [name + ':'] + [
        f for f in [field(x, ninfo, Verbose) for x in field_list] if f
    ]
    if Verbose:
        sep = '\n    ' + prefix
    else:
        sep = ' '
    return sep.join(outlist)


nodeinfo_string = nodeinfo_cooked


def printfield(name, entry, prefix: str="") -> None:
    outlist = field("implicit", entry, 0)
    if outlist:
        if Verbose:
            print("    implicit:")
        print("        " + outlist)
    outact = field("action", entry, 0)
    if outact:
        if Verbose:
            print("    action: " + outact)
        else:
            print("        " + outact)


def printentries(entries, location) -> None:
    if Print_Entries:
        for name in Print_Entries:
            try:
                entry = entries[name]
            except KeyError:
                err = "sconsign: no entry `%s' in `%s'\n" % (name, location)
                sys.stderr.write(err)
            else:
                try:
                    ninfo = entry.ninfo
                except AttributeError:
                    print(name + ":")
                else:
                    print(nodeinfo_string(name, entry.ninfo))
                printfield(name, entry.binfo)
    else:
        #print(f"{__file__}/printentries: {entries=}")
        for name in sorted(entries.keys()):
            entry = entries[name]
            try:
                entry.ninfo
            except AttributeError:
                print(name + ":")
            else:
                print(nodeinfo_string(name, entry.ninfo))
            printfield(name, entry.binfo)


class Do_SConsignDB:
    def __init__(self, dbm_name, dbm_type, dbm) -> None:
        self.dbm_name = dbm_name
        self.dbm_type = dbm_type
        if DEBUG:
            print(f"DEBUG: Do_SConsignDB.__init__({dbm_name}, {dbm_type}, dbm)")
        self.dbm = dbm

    def __call__(self, fname):
        # The *dbm modules stick their own file suffixes on the names
        # that are passed in, but the diskcache scheme does not
        # (although by convention it uses a directory suffixed .d)
        # This causes us to jump through some # hoops here.
        if DEBUG:
            print(f"DEBUG: Do_SConsignDB.__call__({fname}), type is {self.dbm_type}")
        try:
            # Try opening the specified file name.  Example:
            #   SPECIFIED                  OPENED BY self.dbm.open()
            #   ---------                  -------------------------
            #   .sconsign               => .sconsign.dblite
            #   .sconsign.dblite        => .sconsign.dblite.dblite
            db = self.dbm.open(fname, "r")
        except OSError as e:
            print_e = e
            try:
                # That didn't work, so try opening the base name,
                # so that if they actually passed in 'sconsign.dblite'
                # (for example), the dbm module will put the suffix back
                # on for us and open it anyway.
                db = self.dbm.open(os.path.splitext(fname)[0], "r")
            except OSError:
                # That didn't work either.  See if the file name
                # they specified even exists (independent of the dbm
                # suffix-mangling).
                try:
                    with open(fname, "rb"):
                        pass  # this is a touch only, we don't use it here.
                except OSError as e:
                    # Nope, that file doesn't even exist, so report that
                    # fact back.
                    print_e = e
                sys.stderr.write("sconsign: %s\n" % print_e)
                return
        except KeyboardInterrupt:
            raise
        except pickle.UnpicklingError:
            sys.stderr.write("sconsign: ignoring invalid `%s' file `%s'\n"
                             % (self.dbm_name, fname))
            return
        except Exception as e:
            sys.stderr.write("sconsign: ignoring invalid `%s' file `%s': %s\n"
                             % (self.dbm_name, fname, e))
            exc_type, _, _ = sys.exc_info()
            if exc_type.__name__ == "ValueError":
                sys.stderr.write("unrecognized pickle protocol.\n")
            return

        if Convert_To_Diskcache and self.dbm_type != 'SCons.sdiskcache':
            import SCons.sdiskcache
            if fname.endswith('.dblite'):
                dirname = fname[:-len('.dblite')]
            else:
                dirname = fname
            dirname = dirname + '.sqlite'
            newdb = SCons.sdiskcache.open(dirname, flags='n')
            for d in sorted(db.keys()):
                newdb[d] = pickle.loads(db[d])
            print(f"Converted {self.dbm_name} '{fname}' to diskcache in '{dirname}'")
            return

        if Print_Directories:
            for dir in Print_Directories:
                try:
                    val = db[dir]
                except KeyError:
                    err = "sconsign: no dir `%s' in `%s'\n" % (dir, args[0])
                    sys.stderr.write(err)
                else:
                    self.printentries(dir, val)
        else:
            for dir in sorted(db.keys()):
                self.printentries(dir, db[dir])

    def printentries(self, dir, val) -> None:
        try:
            print('=== ' + dir + ':')
        except TypeError:
            print('=== ' + dir.decode() + ':')
        try:
            printentries(pickle.loads(val), dir)
        except TypeError:
            printentries(val, dir)


def Do_SConsignDir(name):
    try:
        with open(name, 'rb') as fp:
            try:
                sconsign = SCons.SConsign.Dir(fp)
            except KeyboardInterrupt:
                raise
            except pickle.UnpicklingError:
                err = "sconsign: ignoring invalid .sconsign file `%s'\n" % name
                sys.stderr.write(err)
                return
            except Exception as e:
                err = "sconsign: ignoring invalid .sconsign file `%s': %s\n" % (name, e)
                sys.stderr.write(err)
                return
            printentries(sconsign.entries, args[0])
    except OSError as e:
        sys.stderr.write("sconsign: %s\n" % e)
        return


##############################################################################
def main() -> None:
    global Do_Call
    global nodeinfo_string
    global args
    global Verbose
    global Readable
    global Convert_To_Diskcache

    helpstr = """\
Usage: sconsign [OPTIONS] [FILE ...]

Options:
  -a, --act, --action         Print build action information.
  -c, --csig                  Print content signature information.
  --convert                   Create diskcache version of database.
  -d DIR, --dir=DIR           Print only info about DIR.
  -e ENTRY, --entry=ENTRY     Print only info about ENTRY.
  -f FORMAT, --format=FORMAT  FILE is in the specified FORMAT.
  -h, --help                  Print this message and exit.
  -i, --implicit              Print implicit dependency information.
  -r, --readable              Print timestamps in human-readable form.
  --raw                       Print raw Python object representations.
  -s, --size                  Print file sizes.
  -t, --timestamp             Print timestamp information.
  -v, --verbose               Verbose, describe each field.
"""
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            'acd:e:f:hirstv',
            [
                'act',
                'action',
                'convert',
                'csig',
                'dir=',
                'entry=',
                'format=',
                'help',
                'implicit',
                'raw',
                'readable',
                'size',
                'timestamp',
                'verbose',
            ],
        )
    except getopt.GetoptError as err:
        sys.stderr.write(str(err) + '\n')
        print(helpstr)
        sys.exit(2)

    for o, a in opts:
        if o in ('-a', '--act', '--action'):
            Print_Flags['action'] = True
        elif o in ('-c', '--csig'):
            Print_Flags['csig'] = True
        elif o in ('--convert'):
            Convert_To_Diskcache = True
        elif o in ('-d', '--dir'):
            Print_Directories.append(a)
        elif o in ('-e', '--entry'):
            Print_Entries.append(a)
        elif o in ('-f', '--format'):
            # Try to map the given DB format to a known module
            # name, that we can then try to import...
            Module_Map = {
                'dblite': 'SCons.dblite',
                'diskcache': 'SCons.sdiskcache',
                'sconsign': None,
            }
            dbm_type = Module_Map.get(a, a)
            if dbm_type:
                if DEBUG:
                    print(f"DEBUG: asked for {a}, which is {dbm_type}")
                try:
                    if dbm_type == "SCons.dblite":
                        import SCons.dblite as dbm
                        # Ensure that we don't ignore corrupt DB files
                        SCons.dblite.IGNORE_CORRUPT_DBFILES = False
                    elif dbm_type == "SCons.sdiskcache":
                        import SCons.sdiskcache as dbm
                    else:
                        dbm = importlib.import_module(dbm_name)
                except ImportError:
                    sys.stderr.write("sconsign: illegal file format `%s'\n" % a)
                    print(helpstr)
                    sys.exit(2)
                Do_Call = Do_SConsignDB(a, dbm_type, dbm)
            else:
                if DEBUG:
                    print(f"DEBUG: asked for {dbm_type}")
                Do_Call = Do_SConsignDir
        elif o in ('-h', '--help'):
            print(helpstr)
            sys.exit(0)
        elif o in ('-i', '--implicit'):
            Print_Flags['implicit'] = True
        elif o in ('--raw',):
            nodeinfo_string = nodeinfo_raw
        elif o in ('-r', '--readable'):
            Readable = True
        elif o in ('-s', '--size'):
            Print_Flags['size'] = True
        elif o in ('-t', '--timestamp'):
            Print_Flags['timestamp'] = True
        elif o in ('-v', '--verbose'):
            Verbose = True

    if Do_Call:
        for a in args:
            Do_Call(a)
    else:
        if not args:
            #args = [".sconsign.dblite"]
            args = [".sconsign"]
        for a in args:
            dbm_type = my_whichdb(a)
            if DEBUG:
                print(f"DEBUG: back from my_whichdb, dbm is {dbm_type}")
            if dbm_type:
                Map_Module = {
                    'SCons.dblite': 'dblite',
                    'SCons.sdiskcache': 'diskcache'
                }
                if dbm_type == "SCons.dblite":
                    import SCons.dblite as dbm
                    # Ensure that we don't ignore corrupt DB files,
                    SCons.dblite.IGNORE_CORRUPT_DBFILES = False
                elif dbm_type == "SCons.sdiskcache":
                    import SCons.sdiskcache as dbm
                else:
                    dbm = importlib.import_module(dbm_name)
                Do_SConsignDB(Map_Module.get(dbm_type, dbm_type), dbm_type, dbm)(a)
            else:
                Do_SConsignDir(a)

        if Warns:
            print("NOTE: there were %d warnings, please check output" % Warns)


if __name__ == "__main__":
    main()
    sys.exit(0)

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
