"""Functions relating to the CLI interface."""
from __future__ import print_function

from node import MetaNode


def _do_print_color(*vargs, **kwargs):
    """Utility function: Prints using shell colors."""
    colorcode = kwargs.pop("colorcode")
    text = ["\033[00;%im%s\033[00m" % (colorcode, arg) for arg in vargs]

    print(*text, **kwargs)


def print_msg(*vargs, **kwargs):
    """Equivalent to print. Currently does not apply a color to the text"""
    print(*vargs, **kwargs)


def print_info(*vargs, **kwargs):
    """Equivalent to print, but prints using shell colorcodes (green)."""
    _do_print_color(*vargs, colorcode = 32, **kwargs)


def print_err(*vargs, **kwargs):
    """Equivalent to print, but prints using shell colorcodes (red)."""
    _do_print_color(*vargs, colorcode = 31, **kwargs)


def print_warn(*vargs, **kwargs):
    """Equivalent to print, but prints using shell colorcodes (yellow)."""
    _do_print_color(*vargs, colorcode = 33, **kwargs)


def print_disabled(*vargs, **kwargs):
    """Equivalent to print, but prints using shell colorcodes (gray)."""
    _do_print_color(*vargs, colorcode = 30, **kwargs)



def print_node_tree(graph, collapse = True):
    total, done, running, failed = 0, 0, 0, 0
    for node in graph.iterflat():
        total += 1
        if node.state == node.DONE:
            done += 1
        elif node.state == node.RUNNING:
            running += 1
        elif node.state == node.ERROR:
            failed  += 1
            

    print_msg("Pipeline, \t%i running, %i done, %i failed of %i nodes:" \
                  % (running, done, failed, total))
    _print_sub_nodes(graph, collapse, "   ")
        

def _print_sub_nodes(nodes, collapse, prefix = ""):
    nodes = list(nodes)
    nodes.sort(key = str)

    for node in nodes:
        if node.state in (node.RUNNING, node.RUNABLE):
            description = prefix + "R " + str(node)
        else:
            description = prefix + "+ " + str(node)

        # FIXME
        if isinstance(node.task, MetaNode):
            active, done, total = 0, 0, 0
            for subnode in node.subnodes:
                total += 1
                if subnode.state == subnode.RUNNING:
                    active += 1
                elif subnode.state == subnode.DONE:
                    done += 1
        
            description += " %i running, %i done of %i subnodes" % (active, done, total)

        print_func = _get_print_function(node)
        print_func(description)
        current_prefix = prefix + ("  " if (node == nodes[-1]) else "|  ")

        dependencies = _collect_dependencies(node)
        if dependencies:
            if collapse and _collapse_node(dependencies):
                print_disabled(current_prefix + "+ ...")
                print_disabled(current_prefix)
            else:
                _print_sub_nodes(dependencies, collapse, current_prefix + "   ")
        else:
            print_func(current_prefix)


def _collapse_node(dependencies):
    for subnode in dependencies:
        if subnode.state != subnode.DONE:
            return False

    return True


def _get_print_function(node):
    # FIXME
    if isinstance(node.task, MetaNode):
        for subnode in node.subnodes:
            if subnode.state == subnode.RUNNING:
                return print_info

    if node.state is node.RUNNING:
        return print_info
    elif node.state is node.DONE:
        return print_disabled
    elif node.state is node.OUTDATED:
        return print_warn
    else:
        return print_msg


def _collect_dependencies(node):
    """For a regular node, this function returns the subnodes, which are taken
    to be the dependencies of that node. For a MetaNode, the subnodes are 
    considered part of that Node, and hence the dependencies of _those_ nodes
    are returned."""
    # FIXME
    if not isinstance(node.task, MetaNode):
        return node.subnodes

    dependencies = set()
    for subnode in node.subnodes:
        for dependency in subnode.subnodes:
            if dependency not in node.subnodes:
                dependencies.add(dependency)
                
    return dependencies
