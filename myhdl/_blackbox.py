# Blackbox wrapper implementation
#
# PROTOYPE STADIUM, rather stable
#
# (c) 2020 section5.ch
#
# Implements @inference() decorator for inference hints to synthesis
# factories.
# Currently, only yosys is supported.
#
# The reason for blackbox module is elaborated as follows:
#
# 1) There are complicated descriptions that are hard to synthesize or
#    detected by a mapper routine in order to infer a specific primitive,
#    such as an abstracted single or dual port memory primitive
#
# 2) There are vendor specific IP blocks, possibly without functional
#    simulation description that are to be instanced in a top level design.
#
# A blackbox allows to:
#
# - Describe an exact method to infer to a primitive
# - Provide a emulation model for a hardware design
#
#  Note: When not providing a model, remember to use the _driven attribute for
#  signals that are output (from the black box module)
#


from ._block import block, _Block, _uniqueify_name, _getCallInfo

import inspect
import functools
from myhdl._util import _flatten
from myhdl._instance import _Instantiator
from myhdl import BlockError, BlockInstanceError, CosimulationPipe

BLUEBG = "\033[7;34m"
OFF = "\033[0m"

def _my_debug(details):
	msg = "SYNTHESIS"
	print("%s: %s" % (BLUEBG + msg + OFF, details))

def _dummy_debug(x):
	pass

_debug = _my_debug

class SynthesisObject:
	ignoreSimulation = True

	def __init__(self, func, methodclass = None):
		self.id  = "synthesis"
		self.func = func
		self.name = func.__name__
		self.method = methodclass

	def infer(self, module, interface):
		if hasattr(module, 'name'):
			_debug("Inferring %s for module '%s'" % (self.name, module.name.str()))
			self.func(module, interface)
		else:
			raise TypeError("Incompatible module object passed")

	def implement(self, name, **kwargs):
		"Implements an object according to the given @synthesis(rule)"
		m = self.method(**kwargs)
		module = m.instance(name)
		_debug("Implementing unit '%s'" % (self.name))
		ret = self.func(module, name)
		if ret == None:
			raise ValueError("Did you return the generator from the @blackbox entity?")
		return ret

	def blackbox(self, module, interface):
		_debug("Default: External black box '%s' for module %s" % (self.name, module.name.str()))
		
class SynthesisFactory:
	def __init__(self, func):
		self.func = func
		_debug("Wrapping for inference: %s()" % func.__name__)

	def __call__(self, func, *args, **kwargs):
		return SynthesisObject(func, self.func)

def inference(func):
	fact = SynthesisFactory(func)
	return fact

synthesis = inference

class _BlackBox(_Block):
	def __init__(self, func, deco, name, srcfile, srcline, *args, **kwargs):
		self.func = func
		self.args = args
		self.kwargs = kwargs
		callinfo = _getCallInfo()
		self.callinfo = callinfo
		self.modctxt = callinfo.modctxt
		self.name = self.__name__ = name
		self.symdict = None
		self.sigdict = {}
		self.memdict = {}
		self.name = self.__name__ = name
		# True when we are a module from the library
		self.is_builtin = False

		# flatten, but keep BlockInstance objects
		self.subs = _flatten(func(*args, **kwargs))
		self._verifySubs()
		self._updateNamespaces()
		self.verilog_code = self.vhdl_code = None
		self.sim = None

		self._config_sim = {'trace': False}

	def _verifySubs(self):
		for inst in self.subs:
			# _debug(type(inst))
			if not isinstance(inst, (_Block, _Instantiator, CosimulationPipe, SynthesisObject)):
				raise BlockError("ERR %s: %s not known" %  (self.name, type(inst)))
			if isinstance(inst, (_Block, _Instantiator)):
				if not inst.modctxt:
					raise BlockError("ERR %s %s" % (self.name, inst.callername))

	def infer(self, module, interface = None):
		"Calls inference members of blackbox object"
		if interface:
			interface.sigdict = self.sigdict
		for inst in self.subs:
			if isinstance(inst, SynthesisObject):
				inst.infer(module, interface)

	def implement(self, name, top_name, **kwargs):
		"""Implements all sub objects of method `name` and renames
the top level object to `top_name`"""
		for inst in self.subs:
			if inst.name == name:
				return inst.implement(top_name, **kwargs)
		raise KeyError("Unable to find inference function '%s'\n" % name + \
		               "Did you return it from the @blackbox entity?")

	def blackbox(self, module, interface):
		"Calls all blackbox creator functions of Blackbox"
		for inst in self.subs:
			if isinstance(inst, SynthesisObject):
				inst.blackbox(module, interface)

	def dump(self):
		_debug(self.kwargs)
		
############################################################################
# EXPERIMENTAL, should move
class blackbox(block):
	def __init__(self, func):
		block.__init__(self, func)

	def __call__(self, *args, **kwargs):

		name = self.func.__name__ + "_" + str(self.calls)
		self.calls += 1

		# See concerns above about uniqueifying
		name = _uniqueify_name(name)

		return _BlackBox(self.func, self, name, self.srcfile,
					  self.srcline, *args, **kwargs)


