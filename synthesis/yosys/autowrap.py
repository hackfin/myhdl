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
from myhdl.conversion import yshelper as ys

from myhdl._Signal import _Signal

class AutoSynthesisObject(SynthesisObject):
	def __init__(self, identifier, typename, args, kwargs, argnames, \
		mapping = None):
		self.args = args
		self.kwargs = kwargs
		self.argnames = argnames
		self.name = identifier
		self.typename = typename
		self.mapping = mapping

	def infer(self, module, interface):
		"""The inference method defines how the connections outside
the blackbox are made. For identical signal mapping (self.mapping == None),
it sets the ports of the unit according to the interface signal types."""

		unit = module.addCell(self.name, self.typename, True)
		args = self.args

		print("Custom mapping for %s" % module.name)

		if self.mapping:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					if isinstance(sig, _Signal):
						otype, src = module.signal_output_type(sig)
						if not src:
							print("Notice: %s has no source" % n)
						# If we're an input, simply extract signal
						# from bulk signal
						bulk = module.findWireByName(n)
						m = self.mapping[n]
						l = len(m)
						if otype:
							if l > 1:
								cc = module.addSignal(None, 0)
								for j, s in enumerate(reversed(m)):
									identifier = "%s%d" % (n, j)
									w = ys.Signal(module.addWire(identifier, 1))
									unit.setPort(identifier, w)
									cc.append(w)
								module.connect(bulk, cc)
							else:
								w = ys.Signal(module.addWire(n, 1))
								unit.setPort(n, w)
								module.connect(bulk, w)
						else:
							if l > 1:
								for j, s in enumerate(reversed(m)):
									identifier = "%s%d" % (n, j)
									w = bulk.extract(j, 1)
									unit.setPort(identifier, w)
							else:
								unit.setPort(identifier, bulk)

					elif isinstance(sig, bool):
						w = ys.ConstSignal(sig)
						unit.setPort(n, w)
					else:
						raise TypeError("Unhandled parameter type")

		else:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					w = module.findWireByName(n)
					unit.setPort(n, w)
				
		for pid, param in self.kwargs.items():
			if param != None:
				unit.setParam(pid, param)

		module.fixup_ports() # Important

	def blackbox(self, module, interface):
		"Creates the black box interface for the stub"
		args = self.args
		module.defaults = {}
		module.makeblackbox()

		if self.mapping:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]

					m = self.mapping[n]
					l = len(m)

					if isinstance(sig, _Signal):
						otype, src = module.signal_output_type(sig)
					else:
						otype = False

					if l > 1:
						for j, s in enumerate(m):
							identifier = "%s%d" % (n, j)
							# Make sure to add a 'public' wire:
							w = module.addWire(identifier, 1, True)
							if otype:
								w.setDirection(IN=False, OUT=True)
							else:
								w.setDirection(IN=True, OUT=False)
							module.wires[identifier] = ys.Signal(w)
					else:
						w = module.addWire(n, 1, True)
						if otype:
							w.setDirection(IN=False, OUT=True)
						else:
							w.setDirection(IN=True, OUT=False)
						module.wires[n] = ys.Signal(w)
		else:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					module.collectArg(n, sig, True)

		l = self.kwargs.keys()
		module.avail_parameters = [ (ys.PID(i)) for i in l ]

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
		self.unroll = None

	def __call__(self, *args, **kwargs):
		name = self.func.__name__ + "_" + str(self.calls)
		self.calls += 1

		name = _uniqueify_name(name)

		b = _BlackBox(self.func, self, name, self.srcfile,
					  self.srcline, *args, **kwargs)

		b.is_builtin = True

		if self.unroll:
			mapping = self.unroll(args, self.argnames)
		else:
			mapping = None
	
		gen = AutoSynthesisObject(name, self.func.__name__, \
			args, kwargs, self.argnames, mapping)
		b.subs.append(gen)

		return b

class WrapperFactory:
	def __init__(self, translate):
		self.translate = translate

	def __call__(self, *args, **kwargs):
		func = args[0]
		wrapper = autowrap(func)
		wrapper.unroll = self.translate

		return wrapper


def autowrap_unroll(func):
	wrapper = WrapperFactory(func)
	return wrapper


class BulkSignal(_Signal):
	"""Class for automatical unwrapping of an intb into single boolean
signals"""
	def __init__(self, *args):
		self.signals = args
