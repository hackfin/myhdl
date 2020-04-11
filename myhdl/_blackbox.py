# Blackbox wrapper implementation
#
# PROTOYPE STADIUM, rather unstable
#
# (c) 2020 section5.ch
#
# Implements @synthesis() decorator for inference hints to synthesis
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
from myhdl import BlockError, BlockInstanceError, Cosimulation

BLUEBG = "\033[7;34m"
OFF = "\033[0m"

def _debug(details):
	msg = "SYNTHESIS"
	print("%s: %s" % (BLUEBG + msg + OFF, details))

class SynthesisObject:
	ignoreSimulation = True

	def __init__(self, func):
		self.id  = "synthesis"
		self.func = func
		self.name = func.__name__

	def infer(self, module, inst):
		_debug("Inferring %s for module '%s'" % (self.name, module.name.str()))
		self.func(module, inst)

class SynthesisFactory:
	def __init__(self, func):
		self.func = func
		_debug("Wrapping for synthesis: %s()" % func.__name__)

	def __call__(self, func, *args, **kwargs):
		print(args)
		_debug("Call factory, mode: %s" % func.__name__)
		return SynthesisObject(func)

def synthesis(func):
	_debug("wrap factory")

	fact = SynthesisFactory(func)
	_debug(fact)
	return fact

class _BlackBox(_Block):
	def __init__(self, func, deco, name, srcfile, srcline, *args, **kwargs):
		self.func = func
		self.args = args
		self.kwargs = kwargs
		callinfo = _getCallInfo()
		self.callinfo = callinfo
		self.modctxt = callinfo.modctxt
		self.name = self.__name__ = name
		self.subs = _flatten(func(*args, **kwargs))
		self.symdict = None
		self.sigdict = {}
		self.memdict = {}
		self.name = self.__name__ = name

		# flatten, but keep BlockInstance objects
		self.subs = _flatten(func(*args, **kwargs))
		self._verifySubs()
		self._updateNamespaces()
		self.verilog_code = self.vhdl_code = None
		self.sim = None

	def _verifySubs(self):
		for inst in self.subs:
			_debug(type(inst))
			if not isinstance(inst, (_Block, _Instantiator, Cosimulation, SynthesisObject)):
				raise BlockError("ERR %s: %s not known" %  (self.name, type(inst)))
			if isinstance(inst, (_Block, _Instantiator)):
				if not inst.modctxt:
					raise BlockError("ERR %s %s" % (self.name, inst.callername))

	def infer(self, module, interface):
		for inst in self.subs:
			if isinstance(inst, SynthesisObject):
				inst.infer(module, interface)

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


