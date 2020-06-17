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
from myhdl._bulksignal import _BulkSignalBase, mangle
from myhdl.conversion import yshelper as ys

from myhdl._Signal import _Signal

from myhdl.conversion.ysmodule_ng import INPUT, OUTPUT

def map_interface(module, name, mapping, sig, otype = None):
	"""Map signal to module interface."""
	if otype == None:
		otype, _ = module.signal_output_type(sig)

	l = len(mapping)

	if l > 1:
		for j, _ in enumerate(mapping):
			identifier = "%s%d" % (name, j)
			# Make sure to add a 'public' wire:
			w = module.addWire(identifier, 1, True)
			if otype:
				w.setDirection(IN=False, OUT=True)
			else:
				w.setDirection(IN=True, OUT=False)

			module.wires[identifier] = ys.YSignal(w)
	else:
		w = module.addWire(name, 1, True)
		if otype:
			w.setDirection(IN=False, OUT=True)
		else:
			w.setDirection(IN=True, OUT=False)
		module.wires[name] = ys.YSignal(w)

	print("SET IO %s to %s" % (name, otype))
	module.iomap[name] = OUTPUT if otype else INPUT

def map_port(module, unit, mapping, identifier, sig, otype = None):
	"""Maps a signal from the parenting `module` to the ports of a
black box entity (a.ka. cell `unit`) using the given
mapping."""
	if otype == None:
		otype, src = module.signal_output_type(sig)
		if not src:
			print("Notice: %s has no source" % identifier)
	# If we're an input, simply extract signal
	# from bulk signal
	bulk = module.findWireByName(identifier)
	if not bulk:
		raise KeyError("Bulk wire '%s' not found" % n)

	l = len(mapping)
	if l > 1:
		if otype:
			cc = module.addSignal(None, 0)
			for j, me in enumerate(mapping):
				pid, sz = me
				w = ys.YSignal(module.addWire(pid, 1))
				unit.setPort(pid, w)
				cc.append(w)
			module.connect(bulk, cc)
		else:
			for j, me in enumerate(mapping):
				pid, sz = me
				w = bulk.extract(j, 1)
				unit.setPort(pid, w)
	else:
		unit.setPort(identifier, bulk)

def translate_vector(name, sig):
	l = len(sig)
	r = range(l)
	mapping = [ ("%s%d" % (name, i), 1) for i in r]
	return mapping

# Name mangling:

class BulkSignal(_BulkSignalBase):
	def map_ports(self, module, unit):
		"Map ports to unit"
		for n in self.__slots__:
			name = mangle(self._name, n)
			s = getattr(self, n)
			if isinstance(s, _Signal):
				map_port(module, unit, translate_vector(name, s), name, s, self._otype)
			elif isinstance(s, BulkSignal):
				raise TypeError("Nested bulk class signals not allowed")
			else:
				raise TypeError("Unsupported type %s", type(s))

	def interface(self, module):
		"Create the interface in the passed module"

		for n in self.__slots__:
			name = mangle(self._name, n)
			s = getattr(self, n)
			if isinstance(s, _Signal):
				map_interface(module, name, translate_vector(name, s), s, self._otype)
			else:
				raise TypeError("Unsupported type %s", type(s))

	def convert_wires(self, m, c):
		for n, i in self.members():
			name = mangle(self._name, n)
			# We explicitely assign that name and driver:
			i._name = name
			if self._otype:
				i._source = m.implementation
				i.driven = "wire"
			else:
				i.read = True
			ys.convert_wires(m, c, i, name, True)

def signal_output_type(implementation, sig):
	src = sig._source
	is_out = False
	if src:
		# If it's us driving the pin, we're an OUT,
		# unless we're a shadow.
		if src == implementation:
			if not isinstance(sig, _ShadowSignal):
				is_out = sig._driven
		src = src.name
	return is_out, src

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

		if self.mapping:
			print("Custom mapping black box %s" % self.name)
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					if isinstance(sig, _Signal):
						m = self.mapping[n]
						map_port(module, unit, m, n, sig)
					elif isinstance(sig, BulkSignal):
						sig.map_ports(module, unit)
					elif isinstance(sig, (int, bool)):
						w = ys.ConstSignal(sig)
						unit.setPort(n, w)
					else:
						raise TypeError("Unsupported arg type %s" % type(sig))

		else:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					if isinstance(sig, _Signal):
						w = module.findWireByName(n)
						if not w:
							raise KeyError("Wire '%s' not found" % n)
						unit.setPort(n, w)
					elif isinstance(sig, BulkSignal):
						sig.map_ports(module, unit)
					elif isinstance(sig, (int, bool)):
						w = ys.ConstSignal(sig)
						unit.setPort(n, w)
					else:
						raise TypeError("Unsupported arg type %s" % type(sig))
				
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
					otype = interface.output_type(sig, n)
					module.iomap[n] = [otype, sig]
					if isinstance(sig, _Signal):
						map_interface(module, n, self.mapping, sig)
					elif isinstance(sig, BulkSignal):
						sig.interface(module)
					else:
						raise TypeError("Unsupported argument type %s" % (type(sig)))

		else:
			for i, a in enumerate(self.argnames):
				n, p = a
				if p.kind == p.POSITIONAL_OR_KEYWORD:
					sig = args[i]
					otype = interface.output_type(sig, n)
					module.iomap[n] = [otype, sig]
					module.collectArg(n, sig, True, True)

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

def insert_sig(d, prefix, sig):
	def translate(name, sig):
		l = len(sig)
		r = range(l)
		mapping = [ ("%s%d" % (name, i), 1) for i in r]
		return mapping

	if isinstance(sig, BulkSignal):
		for subsig in sig.members():
			insert_sig(d, sig._name + "_" + subsig[0], subsig[1])
	elif isinstance(sig, _Signal):
		name = prefix
		if sig._type == intbv:
			ns = translate(name, sig)
			d[name] = ns
		elif sig._type == bool:
			d[name] = [(name, 1)]
	elif isinstance(sig, bool):
		d[name] = [(name, 1)]
	else:
		raise ValueError("Unsupported type", type(sig))	

def unroll_bulk(args, argnames):
	"""Bulk class unroller. Unrolls all bit vectors of name V into a map
	of V0, V1, .. into boolean signals each"""

	mapping = {}
	for i, n in enumerate(argnames):
		sig = args[i]
		name = n[0]
		insert_sig(mapping, name, sig)

	return mapping
