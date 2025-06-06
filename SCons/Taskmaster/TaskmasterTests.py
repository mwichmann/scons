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

import SCons.compat

import sys
import unittest

import SCons.Taskmaster
import SCons.Errors

import TestCommon

built_text = None
cache_text = []
visited_nodes = []
executed = None
scan_called = 0


class Node:
    def __init__(self, name, kids=[], scans=[]) -> None:
        self.name = name
        self.kids = kids
        self.scans = scans
        self.cached = False
        self.scanned = False
        self.scanner = None
        self.targets = [self]
        self.prerequisites = None

        class Builder:
            def targets(self, node):
                return node.targets

        self.builder = Builder()
        self.bsig = None
        self.csig = None
        self.state = SCons.Node.no_state
        self.prepared = None
        self.ref_count = 0
        self.waiting_parents = set()
        self.waiting_s_e = set()
        self.side_effect = False
        self.side_effects = []
        self.alttargets = []
        self.postprocessed = None
        self._bsig_val = None
        self._current_val = 0
        self.always_build = None

    def disambiguate(self):
        return self

    def push_to_cache(self) -> bool:
        pass

    def retrieve_from_cache(self) -> bool:
        global cache_text
        if self.cached:
            cache_text.append(self.name + " retrieved")
        return self.cached

    def make_ready(self) -> None:
        pass

    def prepare(self) -> None:
        self.prepared = 1
        self.get_binfo()

    def build(self) -> None:
        global built_text
        built_text = self.name + " built"

    def remove(self) -> None:
        pass

    # The following four methods new_binfo(), del_binfo(),
    # get_binfo(), clear() as well as its calls have been added
    # to support the cached_execute() test (issue #2720).
    # They are full copies (or snippets) of their actual
    # counterparts in the Node class...
    def new_binfo(self):
        binfo = "binfo"
        return binfo

    def del_binfo(self) -> None:
        """Delete the build info from this node."""
        try:
            delattr(self, 'binfo')
        except AttributeError:
            pass

    def get_binfo(self):
        """Fetch a node's build information."""
        try:
            return self.binfo
        except AttributeError:
            pass

        binfo = self.new_binfo()
        self.binfo = binfo

        return binfo

    def clear(self) -> None:
        # The del_binfo() call here isn't necessary for normal execution,
        # but is for interactive mode, where we might rebuild the same
        # target and need to start from scratch.
        self.del_binfo()

    def built(self) -> None:
        global built_text
        if not self.cached:
            built_text = built_text + " really"

        # Clear the implicit dependency caches of any Nodes
        # waiting for this Node to be built.
        for parent in self.waiting_parents:
            parent.implicit = None

        self.clear()

    def release_target_info(self) -> None:
        pass

    def has_builder(self) -> bool:
        return self.builder is not None

    def is_derived(self) -> bool:
        return self.has_builder or self.side_effect

    def alter_targets(self):
        return self.alttargets, None

    def visited(self) -> None:
        global visited_nodes
        visited_nodes.append(self.name)

    def children(self):
        if not self.scanned:
            self.scan()
            self.scanned = True
        return self.kids

    def scan(self) -> None:
        global scan_called
        scan_called = scan_called + 1
        self.kids = self.kids + self.scans
        self.scans = []

    def scanner_key(self):
        return self.name

    def add_to_waiting_parents(self, node) -> int:
        wp = self.waiting_parents
        if node in wp:
            return 0
        wp.add(node)
        return 1

    def get_state(self):
        return self.state

    def set_state(self, state) -> None:
        self.state = state

    def set_bsig(self, bsig) -> None:
        self.bsig = bsig

    def set_csig(self, csig) -> None:
        self.csig = csig

    def store_csig(self) -> None:
        pass

    def store_bsig(self) -> None:
        pass

    def is_up_to_date(self) -> bool:
        return self._current_val

    def __str__(self) -> str:
        return self.name

    def postprocess(self) -> None:
        self.postprocessed = 1
        self.waiting_parents = set()

    def get_executor(self):
        if not hasattr(self, 'executor'):
            class Executor:
                def prepare(self) -> None:
                    pass

                def get_action_targets(self):
                    return self.targets

                def get_all_targets(self):
                    return self.targets

                def get_all_children(self):
                    result = []
                    for node in self.targets:
                        result.extend(node.children())
                    return result

                def get_all_prerequisites(self):
                    return []

                def get_action_side_effects(self):
                    return []

            self.executor = Executor()
            self.executor.targets = self.targets
        return self.executor

    def get_internal_path(self):
        """
        Should only be used (currently) by TaskmasterTestCase.test_cached_execute_target_unlink_fails
        """
        return str(self)


class OtherError(Exception):
    pass


class MyException(Exception):
    pass


class TaskmasterTestCase(unittest.TestCase):

    def test_next_task(self) -> None:
        """Test fetching the next task
        """
        global built_text

        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster([n1, n1])
        t = tm.next_task()
        t.prepare()
        t.execute()
        t = tm.next_task()
        assert t is None

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])

        tm = SCons.Taskmaster.Taskmaster([n3])

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n1 built", built_text
        t.executed()
        t.postprocess()

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n2 built", built_text
        t.executed()
        t.postprocess()

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n3 built", built_text
        t.executed()
        t.postprocess()

        assert tm.next_task() is None

        built_text = "up to date: "
        top_node = n3

        class MyTask(SCons.Taskmaster.AlwaysTask):
            def execute(self) -> None:
                global built_text
                if self.targets[0].get_state() == SCons.Node.up_to_date:
                    if self.top:
                        built_text = self.targets[0].name + " up-to-date top"
                    else:
                        built_text = self.targets[0].name + " up-to-date"
                else:
                    self.targets[0].build()

        n1.set_state(SCons.Node.no_state)
        n1._current_val = 1
        n2.set_state(SCons.Node.no_state)
        n2._current_val = 1
        n3.set_state(SCons.Node.no_state)
        n3._current_val = 1
        tm = SCons.Taskmaster.Taskmaster(targets=[n3], tasker=MyTask)

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n1 up-to-date", built_text
        t.executed()
        t.postprocess()

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n2 up-to-date", built_text
        t.executed()
        t.postprocess()

        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n3 up-to-date top", built_text
        t.executed()
        t.postprocess()

        assert tm.next_task() is None

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])
        n4 = Node("n4")
        n5 = Node("n5", [n3, n4])
        tm = SCons.Taskmaster.Taskmaster([n5])

        t1 = tm.next_task()
        assert t1.get_target() == n1

        t2 = tm.next_task()
        assert t2.get_target() == n2

        t4 = tm.next_task()
        assert t4.get_target() == n4
        t4.executed()
        t4.postprocess()

        t1.executed()
        t1.postprocess()
        t2.executed()
        t2.postprocess()
        t3 = tm.next_task()
        assert t3.get_target() == n3

        t3.executed()
        t3.postprocess()
        t5 = tm.next_task()
        assert t5.get_target() == n5, t5.get_target()
        t5.executed()
        t5.postprocess()

        assert tm.next_task() is None

        n4 = Node("n4")
        n4.set_state(SCons.Node.executed)
        tm = SCons.Taskmaster.Taskmaster([n4])
        assert tm.next_task() is None

        n1 = Node("n1")
        n2 = Node("n2", [n1])
        tm = SCons.Taskmaster.Taskmaster([n2, n2])
        t = tm.next_task()
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert tm.next_task() is None

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1], [n2])
        tm = SCons.Taskmaster.Taskmaster([n3])
        t = tm.next_task()
        target = t.get_target()
        assert target == n1, target
        t.executed()
        t.postprocess()
        t = tm.next_task()
        target = t.get_target()
        assert target == n2, target
        t.executed()
        t.postprocess()
        t = tm.next_task()
        target = t.get_target()
        assert target == n3, target
        t.executed()
        t.postprocess()
        assert tm.next_task() is None

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])
        n4 = Node("n4", [n3])
        n5 = Node("n5", [n3])
        global scan_called
        scan_called = 0
        tm = SCons.Taskmaster.Taskmaster([n4])
        t = tm.next_task()
        assert t.get_target() == n1
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n2
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n3
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n4
        t.executed()
        t.postprocess()
        assert tm.next_task() is None
        assert scan_called == 4, scan_called

        tm = SCons.Taskmaster.Taskmaster([n5])
        t = tm.next_task()
        assert t.get_target() == n5, t.get_target()
        t.executed()
        assert tm.next_task() is None
        assert scan_called == 5, scan_called

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3")
        n4 = Node("n4", [n1, n2, n3])
        n5 = Node("n5", [n4])
        n3.side_effect = True
        n1.side_effects = n2.side_effects = n3.side_effects = [n4]
        tm = SCons.Taskmaster.Taskmaster([n1, n2, n3, n4, n5])
        t = tm.next_task()
        assert t.get_target() == n1
        assert n4.state == SCons.Node.executing, n4.state
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n2
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n3
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n4
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n5
        assert not tm.next_task()
        t.executed()
        t.postprocess()

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3")
        n4 = Node("n4", [n1, n2, n3])

        def reverse(dependencies):
            dependencies.reverse()
            return dependencies

        tm = SCons.Taskmaster.Taskmaster([n4], order=reverse)
        t = tm.next_task()
        assert t.get_target() == n3, t.get_target()
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n2, t.get_target()
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n1, t.get_target()
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n4, t.get_target()
        t.executed()
        t.postprocess()

        n5 = Node("n5")
        n6 = Node("n6")
        n7 = Node("n7")
        n6.alttargets = [n7]

        tm = SCons.Taskmaster.Taskmaster([n5])
        t = tm.next_task()
        assert t.get_target() == n5
        t.executed()
        t.postprocess()

        tm = SCons.Taskmaster.Taskmaster([n6])
        t = tm.next_task()
        assert t.get_target() == n7
        t.executed()
        t.postprocess()
        t = tm.next_task()
        assert t.get_target() == n6
        t.executed()
        t.postprocess()

        n1 = Node("n1")
        n2 = Node("n2", [n1])
        n1.set_state(SCons.Node.failed)
        tm = SCons.Taskmaster.Taskmaster([n2])
        assert tm.next_task() is None

        n1 = Node("n1")
        n2 = Node("n2")
        n1.targets = [n1, n2]
        n1._current_val = 1
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()
        t.executed()
        t.postprocess()

        s = n1.get_state()
        assert s == SCons.Node.executed, s
        s = n2.get_state()
        assert s == SCons.Node.executed, s

    def test_make_ready_out_of_date(self) -> None:
        """Test the Task.make_ready() method's list of out-of-date Nodes
        """
        ood = []

        def TaskGen(tm, targets, top, node, ood=ood):
            class MyTask(SCons.Taskmaster.AlwaysTask):
                def make_ready(self) -> None:
                    SCons.Taskmaster.Task.make_ready(self)
                    self.ood.extend(self.out_of_date)

            t = MyTask(tm, targets, top, node)
            t.ood = ood
            return t

        n1 = Node("n1")
        c2 = Node("c2")
        c2._current_val = 1
        n3 = Node("n3")
        c4 = Node("c4")
        c4._current_val = 1
        a5 = Node("a5")
        a5._current_val = 1
        a5.always_build = 1
        tm = SCons.Taskmaster.Taskmaster(targets=[n1, c2, n3, c4, a5],
                                         tasker=TaskGen)

        del ood[:]
        t = tm.next_task()
        assert ood == [n1], ood

        del ood[:]
        t = tm.next_task()
        assert ood == [], ood

        del ood[:]
        t = tm.next_task()
        assert ood == [n3], ood

        del ood[:]
        t = tm.next_task()
        assert ood == [], ood

        del ood[:]
        t = tm.next_task()
        assert ood == [a5], ood

    def test_make_ready_exception(self) -> None:
        """Test handling exceptions from Task.make_ready()
        """

        class MyTask(SCons.Taskmaster.AlwaysTask):
            def make_ready(self):
                raise MyException("from make_ready()")

        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster(targets=[n1], tasker=MyTask)
        t = tm.next_task()
        exc_type, exc_value, exc_tb = t.exception
        assert exc_type == MyException, repr(exc_type)
        assert str(exc_value) == "from make_ready()", exc_value

    def test_needs_execute(self) -> None:
        """Test that we can't instantiate a Task subclass without needs_execute

        We should be getting:
          TypeError: Can't instantiate abstract class MyTask with abstract methods needs_execute
        """

        class MyTask(SCons.Taskmaster.Task):
            pass

        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster(targets=[n1], tasker=MyTask)
        with self.assertRaises(TypeError):
            _ = tm.next_task()

    def test_make_ready_all(self) -> None:
        """Test the make_ready_all() method"""

        class MyTask(SCons.Taskmaster.AlwaysTask):
            make_ready = SCons.Taskmaster.Task.make_ready_all

        n1 = Node("n1")
        c2 = Node("c2")
        c2._current_val = 1
        n3 = Node("n3")
        c4 = Node("c4")
        c4._current_val = 1

        tm = SCons.Taskmaster.Taskmaster(targets=[n1, c2, n3, c4])

        t = tm.next_task()
        target = t.get_target()
        assert target is n1, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is c2, target
        assert target.state == SCons.Node.up_to_date, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is n3, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is c4, target
        assert target.state == SCons.Node.up_to_date, target.state
        t = tm.next_task()
        assert t is None

        n1 = Node("n1")
        c2 = Node("c2")
        n3 = Node("n3")
        c4 = Node("c4")

        tm = SCons.Taskmaster.Taskmaster(targets=[n1, c2, n3, c4],
                                         tasker=MyTask)

        t = tm.next_task()
        target = t.get_target()
        assert target is n1, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is c2, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is n3, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        target = t.get_target()
        assert target is c4, target
        assert target.state == SCons.Node.executing, target.state
        t = tm.next_task()
        assert t is None

    def test_children_errors(self) -> None:
        """Test errors when fetching the children of a node.
        """

        class StopNode(Node):
            def children(self):
                raise SCons.Errors.StopError("stop!")

        class ExitNode(Node):
            def children(self) -> None:
                sys.exit(77)

        n1 = StopNode("n1")
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()
        exc_type, exc_value, exc_tb = t.exception
        assert exc_type == SCons.Errors.StopError, repr(exc_type)
        assert str(exc_value) == "stop!", exc_value

        n2 = ExitNode("n2")
        tm = SCons.Taskmaster.Taskmaster([n2])
        t = tm.next_task()
        exc_type, exc_value = t.exception
        assert exc_type == SCons.Errors.ExplicitExit, repr(exc_type)
        assert exc_value.node == n2, exc_value.node
        assert exc_value.status == 77, exc_value.status

    def test_cycle_detection(self) -> None:
        """Test detecting dependency cycles
        """
        n1 = Node("n1")
        n2 = Node("n2", [n1])
        n3 = Node("n3", [n2])
        n1.kids = [n3]

        tm = SCons.Taskmaster.Taskmaster([n3])
        try:
            t = tm.next_task()
        except SCons.Errors.UserError as e:
            assert str(e) == "Dependency cycle: n3 -> n1 -> n2 -> n3", str(e)
        else:
            assert 'Did not catch expected UserError'

    def test_next_top_level_candidate(self) -> None:
        """Test the next_top_level_candidate() method
        """
        n1 = Node("n1")
        n2 = Node("n2", [n1])
        n3 = Node("n3", [n2])

        tm = SCons.Taskmaster.Taskmaster([n3])
        t = tm.next_task()
        assert t.targets == [n1], t.targets
        t.fail_stop()
        assert t.targets == [n3], list(map(str, t.targets))
        assert t.top == 1, t.top

    def test_stop(self) -> None:
        """Test the stop() method

        Both default and overridden in a subclass.
        """
        global built_text

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])

        tm = SCons.Taskmaster.Taskmaster([n3])
        t = tm.next_task()
        t.prepare()
        t.execute()
        assert built_text == "n1 built", built_text
        t.executed()
        t.postprocess()
        assert built_text == "n1 built really", built_text

        tm.stop()
        assert tm.next_task() is None

        class MyTM(SCons.Taskmaster.Taskmaster):
            def stop(self) -> None:
                global built_text
                built_text = "MyTM.stop()"
                SCons.Taskmaster.Taskmaster.stop(self)

        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])

        built_text = None
        tm = MyTM([n3])
        tm.next_task().execute()
        assert built_text == "n1 built"

        tm.stop()
        assert built_text == "MyTM.stop()"
        assert tm.next_task() is None

    def test_executed(self) -> None:
        """Test when a task has been executed
        """
        global built_text
        global visited_nodes

        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()
        built_text = "xxx"
        visited_nodes = []
        n1.set_state(SCons.Node.executing)

        t.executed()

        s = n1.get_state()
        assert s == SCons.Node.executed, s
        assert built_text == "xxx really", built_text
        assert visited_nodes == ['n1'], visited_nodes

        n2 = Node("n2")
        tm = SCons.Taskmaster.Taskmaster([n2])
        t = tm.next_task()
        built_text = "should_not_change"
        visited_nodes = []
        n2.set_state(None)

        t.executed()

        s = n2.get_state()
        assert s is None, s
        assert built_text == "should_not_change", built_text
        assert visited_nodes == ['n2'], visited_nodes

        n3 = Node("n3")
        n4 = Node("n4")
        n3.targets = [n3, n4]
        tm = SCons.Taskmaster.Taskmaster([n3])
        t = tm.next_task()
        visited_nodes = []
        n3.set_state(SCons.Node.up_to_date)
        n4.set_state(SCons.Node.executing)

        t.executed()

        s = n3.get_state()
        assert s == SCons.Node.up_to_date, s
        s = n4.get_state()
        assert s == SCons.Node.executed, s
        assert visited_nodes == ['n3', 'n4'], visited_nodes

    def test_prepare(self):
        """Test preparation of multiple Nodes for a task
        """
        n1 = Node("n1")
        n2 = Node("n2")
        tm = SCons.Taskmaster.Taskmaster([n1, n2])
        t = tm.next_task()
        # This next line is moderately bogus.  We're just reaching
        # in and setting the targets for this task to an array.  The
        # "right" way to do this would be to have the next_task() call
        # set it up by having something that approximates a real Builder
        # return this list--but that's more work than is probably
        # warranted right now.
        n1.get_executor().targets = [n1, n2]
        t.prepare()
        assert n1.prepared
        assert n2.prepared

        n3 = Node("n3")
        n4 = Node("n4")
        tm = SCons.Taskmaster.Taskmaster([n3, n4])
        t = tm.next_task()
        # More bogus reaching in and setting the targets.
        n3.set_state(SCons.Node.up_to_date)
        n3.get_executor().targets = [n3, n4]
        t.prepare()
        assert n3.prepared
        assert n4.prepared

        # If the Node has had an exception recorded while it was getting
        # prepared, then prepare() should raise that exception.
        class MyException(Exception):
            pass

        built_text = None
        n5 = Node("n5")
        tm = SCons.Taskmaster.Taskmaster([n5])
        t = tm.next_task()
        t.exception_set((MyException, "exception value"))
        exc_caught = None
        exc_actually_caught = None
        exc_value = None
        try:
            t.prepare()
        except MyException as e:
            exc_caught = 1
            exc_value = e
        except Exception as exc_actually_caught:
            pass
        assert exc_caught, "did not catch expected MyException: %s" % exc_actually_caught
        assert str(exc_value) == "exception value", exc_value
        assert built_text is None, built_text

        # Regression test, make sure we prepare not only
        # all targets, but their side effects as well.
        n6 = Node("n6")
        n7 = Node("n7")
        n8 = Node("n8")
        n9 = Node("n9")
        n10 = Node("n10")

        n6.side_effects = [n8]
        n7.side_effects = [n9, n10]

        tm = SCons.Taskmaster.Taskmaster([n6, n7])
        t = tm.next_task()
        # More bogus reaching in and setting the targets.
        n6.get_executor().targets = [n6, n7]
        t.prepare()
        assert n6.prepared
        assert n7.prepared
        assert n8.prepared
        assert n9.prepared
        assert n10.prepared

        # Make sure we call an Executor's prepare() method.
        class ExceptionExecutor:
            def prepare(self):
                raise Exception("Executor.prepare() exception")

            def get_all_targets(self):
                return self.nodes

            def get_all_children(self):
                result = []
                for node in self.nodes:
                    result.extend(node.children())
                return result

            def get_all_prerequisites(self):
                return []

            def get_action_side_effects(self):
                return []

        n11 = Node("n11")
        n11.executor = ExceptionExecutor()
        n11.executor.nodes = [n11]
        tm = SCons.Taskmaster.Taskmaster([n11])
        t = tm.next_task()
        try:
            t.prepare()
        except Exception as e:
            assert str(e) == "Executor.prepare() exception", e
        else:
            raise AssertionError("did not catch expected exception")

    def test_execute(self) -> None:
        """Test executing a task
        """
        global built_text
        global cache_text

        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()
        t.execute()
        assert built_text == "n1 built", built_text

        def raise_UserError():
            raise SCons.Errors.UserError

        n2 = Node("n2")
        n2.build = raise_UserError
        tm = SCons.Taskmaster.Taskmaster([n2])
        t = tm.next_task()
        try:
            t.execute()
        except SCons.Errors.UserError:
            pass
        else:
            self.fail("did not catch expected UserError")

        def raise_BuildError():
            raise SCons.Errors.BuildError

        n3 = Node("n3")
        n3.build = raise_BuildError
        tm = SCons.Taskmaster.Taskmaster([n3])
        t = tm.next_task()
        try:
            t.execute()
        except SCons.Errors.BuildError:
            pass
        else:
            self.fail("did not catch expected BuildError")

        # On a generic (non-BuildError) exception from a Builder,
        # the target should throw a BuildError exception with the
        # args set to the exception value, instance, and traceback.
        def raise_OtherError():
            raise OtherError

        n4 = Node("n4")
        n4.build = raise_OtherError
        tm = SCons.Taskmaster.Taskmaster([n4])
        t = tm.next_task()
        try:
            t.execute()
        except SCons.Errors.BuildError as e:
            assert e.node == n4, e.node
            assert e.errstr == "OtherError : ", e.errstr
            assert len(e.exc_info) == 3, e.exc_info
            exc_traceback = sys.exc_info()[2]
            assert isinstance(e.exc_info[2], type(exc_traceback)), e.exc_info[2]
        else:
            self.fail("did not catch expected BuildError")

        built_text = None
        cache_text = []
        n5 = Node("n5")
        n6 = Node("n6")
        n6.cached = True
        tm = SCons.Taskmaster.Taskmaster([n5])
        t = tm.next_task()
        # This next line is moderately bogus.  We're just reaching
        # in and setting the targets for this task to an array.  The
        # "right" way to do this would be to have the next_task() call
        # set it up by having something that approximates a real Builder
        # return this list--but that's more work than is probably
        # warranted right now.
        t.targets = [n5, n6]
        t.execute()
        assert built_text == "n5 built", built_text
        assert cache_text == [], cache_text

        built_text = None
        cache_text = []
        n7 = Node("n7")
        n8 = Node("n8")
        n7.cached = True
        n8.cached = True
        tm = SCons.Taskmaster.Taskmaster([n7])
        t = tm.next_task()
        # This next line is moderately bogus.  We're just reaching
        # in and setting the targets for this task to an array.  The
        # "right" way to do this would be to have the next_task() call
        # set it up by having something that approximates a real Builder
        # return this list--but that's more work than is probably
        # warranted right now.
        t.targets = [n7, n8]
        t.execute()
        assert built_text is None, built_text
        assert cache_text == ["n7 retrieved", "n8 retrieved"], cache_text

    def test_cached_execute(self) -> None:
        """Test executing a task with cached targets
        """
        # In issue #2720 Alexei Klimkin detected that the previous
        # workflow for execute() led to problems in a multithreaded build.
        # We have:
        #    task.prepare()
        #    task.execute()
        #    task.executed()
        #        -> node.visited()
        # for the Serial flow, but
        #    - Parallel -           - Worker -
        #      task.prepare()
        #      requestQueue.put(task)
        #                           task = requestQueue.get()
        #                           task.execute()
        #                           resultQueue.put(task)
        #      task = resultQueue.get()
        #      task.executed()
        #        ->node.visited()
        # in parallel. Since execute() used to call built() when a target
        # was cached, it could unblock dependent nodes before the binfo got
        # restored again in visited(). This resulted in spurious
        # "file not found" build errors, because files fetched from cache would
        # be seen as not up to date and wouldn't be scanned for implicit
        # dependencies.
        #
        # The following test ensures that execute() only marks targets as cached,
        # but the actual call to built() happens in executed() only.
        # Like this, the binfo should still be intact after calling execute()...
        global cache_text

        n1 = Node("n1")
        # Mark the node as being cached
        n1.cached = True
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()
        t.prepare()
        t.execute()
        assert cache_text == ["n1 retrieved"], cache_text
        # If no binfo exists anymore, something has gone wrong...
        has_binfo = hasattr(n1, 'binfo')
        assert has_binfo, has_binfo

    def test_cached_execute_target_unlink_fails(self) -> None:
        """Test executing a task with cached targets where unlinking one of the targets fail
        """
        global cache_text
        import SCons.Warnings

        cache_text = []
        n1 = Node("n1")
        n2 = Node("not-cached")

        class DummyFS:
            def unlink(self, _):
                raise IOError

        n1.fs = DummyFS()

        # Mark the node as being cached
        n1.cached = True
        # Add n2 as a target for n1
        n1.targets.append(n2)
        # Explicitly mark n2 as not cached
        n2.cached = False

        # Save SCons.Warnings.warn so we can mock it and catch it being called for unlink failures
        _save_warn = SCons.Warnings.warn
        issued_warnings = []

        def fake_warnings_warn(clz, message) -> None:
            nonlocal issued_warnings
            issued_warnings.append((clz, message))
        SCons.Warnings.warn = fake_warnings_warn

        tm = SCons.Taskmaster.Taskmaster([n1, n2])
        t = tm.next_task()
        t.prepare()
        t.execute()

        # Restore saved warn
        SCons.Warnings.warn = _save_warn

        self.assertTrue(len(issued_warnings) == 1,
                        msg='More than expected warnings (1) were issued %d' % len(issued_warnings))
        self.assertEqual(issued_warnings[0][0], SCons.Warnings.CacheCleanupErrorWarning,
                         msg='Incorrect warning class')
        self.assertEqual(issued_warnings[0][1],
                         'Failed copying all target files from cache, Error while attempting to remove file n1 retrieved from cache: ')
        self.assertEqual(cache_text, ["n1 retrieved"], msg=cache_text)


    def test_exception(self) -> None:
        """Test generic Taskmaster exception handling

        """
        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster([n1])
        t = tm.next_task()

        t.exception_set((1, 2))
        exc_type, exc_value = t.exception
        assert exc_type == 1, exc_type
        assert exc_value == 2, exc_value

        t.exception_set(3)
        assert t.exception == 3

        try:
            1 // 0
        except:
            # Moved from below
            t.exception_set(None)
            # pass

        # Having this here works for python 2.x,
        # but it is a tuple (None, None, None) when called outside
        # an except statement
        # t.exception_set(None)

        exc_type, exc_value, exc_tb = t.exception
        assert exc_type is ZeroDivisionError, "Expecting ZeroDevisionError got:%s" % exc_type
        exception_values = [
            "integer division or modulo",
            "integer division or modulo by zero",
            "integer division by zero",  # PyPy2
            "division by zero",  # Python 3.14+
        ]
        assert str(exc_value) in exception_values, exc_value

        class Exception1(Exception):
            pass

        # Previously value was None, but while PY2 None = "", in Py3 None != "", so set to ""
        t.exception_set((Exception1, ""))
        try:
            t.exception_raise()
        except:
            exc_type, exc_value = sys.exc_info()[:2]
            assert exc_type == Exception1, exc_type
            assert str(exc_value) == '', "Expecting empty string got:%s (type %s)" % (exc_value, type(exc_value))
        else:
            assert 0, "did not catch expected exception"

        class Exception2(Exception):
            pass

        t.exception_set((Exception2, "xyzzy"))
        try:
            t.exception_raise()
        except:
            exc_type, exc_value = sys.exc_info()[:2]
            assert exc_type == Exception2, exc_type
            assert str(exc_value) == "xyzzy", exc_value
        else:
            assert 0, "did not catch expected exception"

        class Exception3(Exception):
            pass

        try:
            1 // 0
        except:
            tb = sys.exc_info()[2]
        t.exception_set((Exception3, "arg", tb))
        try:
            t.exception_raise()
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            assert exc_type == Exception3, exc_type
            assert str(exc_value) == "arg", exc_value
            import traceback
            x = traceback.extract_tb(tb)[-1]
            y = traceback.extract_tb(exc_tb)[-1]
            assert x == y, "x = %s, y = %s" % (x, y)
        else:
            assert 0, "did not catch expected exception"

    def test_postprocess(self) -> None:
        """Test postprocessing targets to give them a chance to clean up
        """
        n1 = Node("n1")
        tm = SCons.Taskmaster.Taskmaster([n1])

        t = tm.next_task()
        assert not n1.postprocessed
        t.postprocess()
        assert n1.postprocessed

        n2 = Node("n2")
        n3 = Node("n3")
        tm = SCons.Taskmaster.Taskmaster([n2, n3])

        assert not n2.postprocessed
        assert not n3.postprocessed
        t = tm.next_task()
        t.postprocess()
        assert n2.postprocessed
        assert not n3.postprocessed
        t = tm.next_task()
        t.postprocess()
        assert n2.postprocessed
        assert n3.postprocessed

    def test_trace(self) -> None:
        """Test Taskmaster tracing
        """
        import io

        trace = io.StringIO()
        n1 = Node("n1")
        n2 = Node("n2")
        n3 = Node("n3", [n1, n2])
        tm = SCons.Taskmaster.Taskmaster([n1, n1, n3], trace=trace)
        t = tm.next_task()
        t.prepare()
        t.execute()
        t.postprocess()
        n1.set_state(SCons.Node.executed)
        t = tm.next_task()
        t.prepare()
        t.execute()
        t.postprocess()
        n2.set_state(SCons.Node.executed)
        t = tm.next_task()
        t.prepare()
        t.execute()
        t.postprocess()
        t = tm.next_task()
        assert t is None

        value = trace.getvalue()
        expect = """\

Taskmaster: Looking for a node to evaluate
Taskmaster:     Considering node <no_state   0   'n1'> and its children:
Taskmaster: Evaluating <pending    0   'n1'>

Task.make_ready_current(): node <pending    0   'n1'>
Task.prepare():      node <executing  0   'n1'>
Task.execute():      node <executing  0   'n1'>
Task.postprocess():  node <executing  0   'n1'>

Taskmaster: Looking for a node to evaluate
Taskmaster:     Considering node <executed   0   'n1'> and its children:
Taskmaster:        already handled (executed)
Taskmaster:     Considering node <no_state   0   'n3'> and its children:
Taskmaster:        <executed   0   'n1'>
Taskmaster:        <no_state   0   'n2'>
Taskmaster:      adjusted ref count: <pending    1   'n3'>, child 'n2'
Taskmaster:     Considering node <no_state   0   'n2'> and its children:
Taskmaster: Evaluating <pending    0   'n2'>

Task.make_ready_current(): node <pending    0   'n2'>
Task.prepare():      node <executing  0   'n2'>
Task.execute():      node <executing  0   'n2'>
Task.postprocess():  node <executing  0   'n2'>
Task.postprocess():  removing <executing  0   'n2'>
Task.postprocess():  adjusted parent ref count <pending    0   'n3'>

Taskmaster: Looking for a node to evaluate
Taskmaster:     Considering node <pending    0   'n3'> and its children:
Taskmaster:        <executed   0   'n1'>
Taskmaster:        <executed   0   'n2'>
Taskmaster: Evaluating <pending    0   'n3'>

Task.make_ready_current(): node <pending    0   'n3'>
Task.prepare():      node <executing  0   'n3'>
Task.execute():      node <executing  0   'n3'>
Task.postprocess():  node <executing  0   'n3'>

Taskmaster: Looking for a node to evaluate
Taskmaster: No candidate anymore.
"""

        if value != expect:
            TestCommon.TestCommon.detailed_diff(value, expect)

        assert value == expect, "Expected taskmaster trace contents didn't match. See above"


if __name__ == "__main__":
    unittest.main()

# Local Variables:
# tab-width:4
# indent-tabs-mode:nil
# End:
# vim: set expandtab tabstop=4 shiftwidth=4:
