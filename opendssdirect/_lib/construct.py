from __future__ import absolute_import, print_function
from builtins import open
import os
import sys
import json
from collections import OrderedDict
from functools import partial
import ctypes
import logging

from ..compat import ModuleType

from .core import load_library
from .core import VArg, VarArray, is_x64, is_delphi


logger = logging.getLogger('opendssdirect.core')


# Global modules and classes that can be populated by functions
modules = OrderedDict()
functions = OrderedDict()


# Use dir_path to locate interface.json
dir_path = os.path.dirname(os.path.realpath(__file__))


# Read interface.json and create interfaces
with open(os.path.join(dir_path, 'interface.json'), encoding='utf-8') as f:
    interface = json.loads(f.read())


if is_delphi():
    HEADER_SIZE = 4  # Windows
else:
    HEADER_SIZE = 8  # OSX and LINUX

if is_x64():
    POINTER = ctypes.c_int64
else:
    POINTER = ctypes.c_int32


def construct():

    library = load_library()

    create_modules()

    create_functions(library)

    for name, f in functions.items():
        module_name = '.'.join(name.split('.')[:-1])
        function_name = name.split('.')[-1]
        setattr(modules[module_name], function_name, f)

    for name, m in modules.items():
        sys.modules[name] = m

    return modules, library


def create_modules():

    for m in interface['modules']:
        name = 'opendssdirect.' + (m['name'])
        modules[name] = ModuleType(name)


def create_functions(library):

    for m in interface['modules']:

        module_name = 'opendssdirect.' + (m['name'])
        for function in m['functions']:

            f = getattr(library, function['library_function_name'])

            f = generate_function(f, function)

            f.__name__ = function['name']
            f.__module__ = module_name
            f.__doc__ = function['doc']

            functions[f.__module__ + '.' + f.__name__] = f


def generate_function(f, function):

    if len(function['args']) == 1 and function['args'][0][-1] is None:
        args = function['args'][0]
        assert args[-1] is None, "Expected second argument to be None"
        mode = args[0]
        f = partial(VarArrayFunction, f=f, mode=mode, name=function['library_function_name'])
    else:
        modes = tuple(mode for mode, arg in function['args'])
        args = tuple(arg for mode, arg in function['args'])
        f = partial(CtypesFunction, f=f, modes=modes, args=args, name=function['library_function_name'])
    return f


def CtypesFunction(arg=None, f=None, modes=None, args=None, name=None):

    if arg is None:
        # First mode should be used
        arg = args[0]
        mode = modes[0]
    else:
        # Second mode should be used
        arg = arg  # Ignore the args
        mode = modes[1]

    logger.debug("Calling function {} with arguments {}".format(name, (mode, arg)))

    return f(mode, arg)


def VarArrayFunction(f, mode, name):

    varg = VArg(0, None, 0, 0)

    p = ctypes.POINTER(VArg)(varg)

    logger.debug("Calling function {} with arguments {}".format(name, (mode, p)))
    f(mode, p)

    var_arr = ctypes.cast(varg.p, ctypes.POINTER(VarArray)).contents

    l = list()

    if varg.dtype == 0x2008:

        data = ctypes.cast(var_arr.data, ctypes.POINTER(POINTER * var_arr.length))

        for s in data.contents:

            length = ctypes.cast(s - HEADER_SIZE, ctypes.POINTER(ctypes.c_uint8)).contents.value

            s = ctypes.cast(s, ctypes.POINTER(ctypes.c_int16 * length))

            l.append(''.join([chr(x).decode('ascii') for x in s.contents[:]]))

    else:

        import warnings
        warnings.warn("Unsupported dtype. Contact developer")

    return l