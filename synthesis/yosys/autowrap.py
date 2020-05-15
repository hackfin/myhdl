"""Auto wrapper decorator framework

(c) 2020 section5.ch

Extracts the blackbox module stub definitions from a blackbox
module definition. This is like the @blackbox, with the @synthesis
rules missing.

The blackbox definition needs to match the following scheme to correctly
define input/outputs:

```
@autowrap
def BB(SIG1_IN, SIG2_OUT, ..., **parameters):
	
	SIG1_IN.read = True  # Mark this explicitely as input, if not
	                     # read below in the emulation

	@always_comb
	def emulation():
		"Set all output ports to something"
		SIG2_OUT.next = True

	
	return assign()
```
"""

import inspect

from myhdl import *
from myhdl._blackbox import blackbox, _BlackBox, SynthesisObject
from myhdl.conversion import yshelper

class AutoSynthesisObject(SynthesisObject):
	def __init__(self, identifier, typename, args, kwargs, argnames):
		self.args = args
		self.kwargs = kwargs
		self.argnames = argnames
		self.name = identifier
		self.typename = typename

	def infer(self, module, interface):
		unit = module.addCell(self.name, self.typename, True)
		args = self.args

		for i, a in enumerate(self.argnames):
			n, p = a
			if p.kind == p.POSITIONAL_OR_KEYWORD:
				sig = args[i]
				w = module.findWireByName(n)
				unit.setPort(n, w)
				
		for pid, param in self.kwargs.items():
			unit.setParam(pid, param)

		module.fixup_ports() # Important

	def blackbox(self, module, interface):
		"Creates the black box interface for the stub"
		args = self.args
		module.defaults = {}
		module.makeblackbox()
		for i, a in enumerate(self.argnames):
			n, p = a
			if p.kind == p.POSITIONAL_OR_KEYWORD:
				sig = args[i]
				module.collectArg(n, sig, True)

		l = self.kwargs.keys()
		module.avail_parameters = [ (yshelper.PID(i)) for i in l ]

		module.fixup_ports() # Important

from myhdl._block import block, _Block, _uniqueify_name

class autowrap(blackbox):
	def __init__(self, func):
		self.argnames = inspect.signature(func).parameters.items()
		# We might want to grab the default parameter settings at
		# a later point. For now, the default bindings should resolve
		# properly.
#		for i, a in enumerate(self.argnames):
#			n, p = a
#			if p.kind == p.VAR_KEYWORD:
#				print("KEYWORD", n)

		blackbox.__init__(self, func)

	def __call__(self, *args, **kwargs):
		name = self.func.__name__ + "_" + str(self.calls)
		self.calls += 1

		name = _uniqueify_name(name)

		b = _BlackBox(self.func, self, name, self.srcfile,
					  self.srcline, *args, **kwargs)

		b.is_builtin = True
	
		gen = AutoSynthesisObject(name, self.func.__name__, \
			args, kwargs, self.argnames)
		b.subs.append(gen)

		return b


