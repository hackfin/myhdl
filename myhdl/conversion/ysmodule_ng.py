from pyosys import libyosys as ys
import ast
from myhdl._Signal import _Signal
from myhdl._ShadowSignal import _ShadowSignal, _TristateDriver
from myhdl._bulksignal import _BulkSignalBase
from myhdl import intbv, EnumType, EnumItemType
from myhdl._block import _Block, block
from myhdl._instance import _Instantiator
import myhdl
from myhdl.conversion import yosys_bb

from .ysdebug import *

from .synmapper import *


def bitfield(n):
	l = [ys.State(int(digit)) for digit in bin(n)[2:]]
	l.reverse()
	return l

def YSignal(x):
	return ys.SigSpec(x.get())

def ConstSignal(x, l = None):
	c = Const(x, l)
	return ys.SigSpec(c.get())

def NEW_ID(name, node, ext):
	return ys.new_id(name, node.lineno, ext)

def OBJ_ID(name, src, ext):
	return ys.IdString("$" + name + "\\" + src + "\\" + ext)

def ID(x):
	return ys.IdString("$" + x)

def PID(x):
	return ys.IdString("\\" + x)

def get_size(s):
	"Returns size of a signal, if known"
	if isinstance(s._val, EnumItemType):
		return None
	elif s._type is bool:
		return 1
	elif s._nrbits is not None:
		return s._nrbits
	else:
		raise AssertionError


def match(a, b):
	"Match signal lengths"

	la, lb = a.q.size(), b.q.size()

	l = la
	trunc = False

	c = 0
	if la < lb: # and isinstance(node.left.obj, _Signal):
		if a.is_signed and not b.is_signed:
			print("A < B")
			lb += 1
			trunc = True
		l = lb
		tmp = ys.SigSpec(a.q)
		tmp.extend_u0(l, a.is_signed)
		a.q = tmp
	elif la > lb: # and isinstance(node.right.obj, _Signal):
		if b.is_signed and not a.is_signed:
			print("A > B")
			l += 1
			trunc = True

		tmp = ys.SigSpec(b.q)
		tmp.extend_u0(l, b.is_signed)
		b.q = tmp
	else:
		# Nasty one: If signednesses are not equal,
		# we need one more headroom bit to determine
		if a.is_signed != b.is_signed:
			print("A == B, no equal signedness")
			l += 1
			tmp0, tmp1 = a.q, b.q
			tmp0.extend_u0(l, a.is_signed)
			tmp1.extend_u0(l, b.is_signed)
			a.q, b.q = tmp0, tmp1
			trunc = True
	return l, trunc


def append_sig(i, a):
	if isinstance(i, _Signal) or isinstance(i, list) or isinstance(i, tuple):
		a += "_%d" % len(i)
	elif isinstance(i, intbv):
		a += "_%d" % len(i)
	elif isinstance(i, int):
		a += "_c%d" % i
	elif isinstance(i, str):
		a += '_%s_' % i
	elif isinstance(i, block):
		a += '_%s_' % i.func.__name__
	elif i == None:
		pass
	elif inspect.isclass(i):
		a += class_key(i)

	return a

def class_key(inst):
	a = ""
	for i in inst.__dict__.items():
		a = append_sig(i[1], a)

	return a


class Wire:
	"Tight wire wrapper"
	def __init__(self, wire):
		self.wire = wire

	def get(self):
		return self.wire

	def setDirection(self, IN = False, OUT = False):
		self.wire.port_input = IN
		self.wire.port_output = OUT

	def __getattr__(self, name):
		return getattr(self.wire, name)

class Const:
	"Tight yosys Const wrapper"
	def __init__(self, value, bits = None):
		if isinstance(value, int):
			if bits == None:
				l = value.bit_length()
				if value < 0:
					l += 1 # Fixup to compensate python's awareness
				elif l < 1:
					l = 1
				# We might run into overflow issues from the yosys side,
				# create a bit vector then:
				if l == 32:
					bitvector = bitfield(value)
					# print("long val %x[%d]" % (int(value), bits))
					self.const = ys.Const(bitvector)
				else:
					self.const = ys.Const(value, l)
			else:
				self.const = ys.Const(value, bits)
		elif isinstance(value, intbv):
			self.fromIntbv(value, bits)
		elif isinstance(value, bool):
			self.const = ys.Const(int(value), 1)
		elif isinstance(value, str):
			self.const = ys.Const(value)
		elif isinstance(value, EnumItemType):
			self.const = ys.Const(int(value), value._nrbits)
		else:
			raise Synth_Nosupp("Unsupported type %s" % type(value).__name__)

	def fromIntbv(self, value, bits):
		v = int(value)
		if not bits:
			bits = value._nrbits

		if bits <= 32:
			self.const = ys.Const(v, bits)
		else:
			bitvector = bitfield(v)
			# print("long val %x[%d]" % (int(value), bits))
			self.const = ys.Const(bitvector)

	def get(self):
		return self.const

	def __getattr__(self, name):
		return getattr(self.const, name)


class Cell:
	"Userdefined or built-in technology cell"
	def __init__(self, cell):
		self.cell = cell

	def setPort(self, name, port):
		if isinstance(port, int):
			port = ConstSignal(port, 32)
		elif isinstance(port, bool):
			port = ConstSignal(int(port), 1)
		self.cell.setPort(PID(name), port)

	def setParam(self, name, c):
		if isinstance(c, int):
			self.cell.setParam(PID(name), Const(c, 32).get())
		else:
			self.cell.setParam(PID(name), Const(c).get())

class BBInterface:
	"Black box interface"
	def __init__(self, name, module):
		self.sigdict = None
		self.interface = {}
		self.name = name
		self.module = module
		self.main_out = None # XXX Hack

	def getId(self):
		return PID(self.name)

	def toInitData(self, values_list, dbits):
		init_data = ConstSignal(values_list[0], dbits)
		for i in values_list[1:]:
			init_data.append(ConstSignal(i, dbits))

		return init_data

	def getOutputs(self):
		"This is a hack for now, as we support one output per assignment only"
		return [ self.main_out ]

	def addConst(self, val, len = 32):
		if isinstance(val, int):
			return ConstSignal(val, len)
		else:
			return ConstSignal(val)

	def createSignal(self, wire, name):
		l = wire.size()
		sig = myhdl.Signal(intbv()[l:])
		sig._name = name
		self.interface[name] = ( wire, False )
		return sig

	def addPort(self, sigid, out = False):
		m = self.module
		sig = self.sigdict[sigid]

		if sigid in self.interface:
			# print("preassigned wire for '%s'" % sigid)
			sigspec, _ = self.interface[sigid]
		else:
			s = len(sig)
			# self.name + '_' + sig._name
			w = m.addWire(None, s, True)
			sigspec = ys.SigSpec(w.get())
			if out:
				# Fixme: Within assign statements, we can have only
				# one output for now (no record assignments)
				#
				self.main_out = sigspec # Record last assigned output

			self.interface[sigid] = ( sigspec, out )
			
		return sigspec

	def __repr__(self):
		a = "{ Inferface: \n"
		for n, i in self.interface.items():
			a += "\t%s : %s \n" % (n, i.as_wire().name.str())
		a += "}\n"

		return a

	def wireup(self, defer = False):	
		"When defer == True, do not connect outputs"
		m = self.module
		for n, i in self.interface.items():

			s, direction = i
			sig = m.findWireByName(n, True)
			w = s.as_wire()
			# Reversed!
			if direction == 0:
				m.connect(s, sig)
			else:
				if defer:
					pass
				else:
					m.connect(sig, s)


class Module:
	"Yosys module wrapper"

	EX_COND, EX_FIRST, EX_SAME, EX_CARRY, EX_TWICE, EX_TRUNC = range(6)

	_unopmap = {
		ast.USub	 :   ys.Module.addNeg,
		ast.Invert	 :   ys.Module.addNot,
		ast.Not		 :   ys.Module.addNot,
	}

	_binopmap = {
		ast.Add		 : ( ys.Module.addAdd,	 EX_CARRY ),
		ast.Sub		 : ( ys.Module.addSub,	 EX_SAME ),
		ast.Mult	 : ( ys.Module.addMul,	 EX_TWICE ),
		ast.Div		 : ( ys.Module.addDiv,	 EX_SAME ),
		ast.Mod		 : ( ys.Module.addMod,	 EX_TRUNC ),
		ast.Pow		 : ( ys.Module.addPow,	 EX_SAME ),
		ast.LShift	 : ( ys.Module.addSshl,	 EX_FIRST ),
		ast.RShift	 : ( ys.Module.addSshr,	 EX_FIRST ),
		ast.BitOr	 : ( ys.Module.addOr,	 EX_SAME ),
		ast.BitAnd	 : ( ys.Module.addAnd,	 EX_SAME ),
		ast.BitXor	 : ( ys.Module.addXor,	 EX_SAME ),
		ast.FloorDiv : ( ys.Module.addDiv,	 EX_SAME ),
		ast.UAdd	 : ( ys.Module.addAdd,	 EX_SAME ),
		ast.USub	 : ( ys.Module.addSub,	 EX_SAME ),
		ast.Eq		 : ( ys.Module.addEq,	 EX_COND ),
		ast.Gt		 : ( ys.Module.addGt,	 EX_COND ),
		ast.GtE		 : ( ys.Module.addGe,	 EX_COND ),
		ast.Lt		 : ( ys.Module.addLt,	 EX_COND ),
		ast.LtE		 : ( ys.Module.addLe,	 EX_COND ),
		ast.NotEq	 : ( ys.Module.addNe,	 EX_COND ),
		ast.And		 : ( ys.Module.addAnd,	 EX_SAME ),
		ast.Or		 : ( ys.Module.addOr,	 EX_SAME )
	}

	_boolopmap = {
		ast.And	     : ys.Module.addReduceAnd,
		ast.Or       : ys.Module.addReduceOr,
		ast.Not	     : ys.Module.addNot
	}

	def __init__(self, m, implementation):
		self.module = m
		self.wires = {} # Local module wires
		self.cache_mem = {}
		self.variables = {}
		self.wireid = {}
		self.parent_signals = {}
		self.memories = {}
		self.arrays = {}
		self.inferred_memories = {}  # Maybe temporary: Track inferred memories
		self.guard = {}
		self.user = [] # Module users
		self.implementation = implementation
		self.array_limit = 1024

		def dummy(a, col = None):
			pass

		if not ENABLE_DEBUG:
			self.debugmsg = dummy


		self._namespace = \
			[ self.memories, self.arrays, self.wires, self.parent_signals ]

	def debugmsg(self, msg, col = REDBG):
		print(col + msg + OFF)
	
	def __getattr__(self, name):
		return getattr(self.module, name)

	def apply_compare(self, node, a, b):
		op = node.ops[0]

		# Have to sort out cases:

		l, _ = match(a, b)

		if a.is_signed or b.is_signed:
			is_signed = True
		else:
			is_signed = False

		sm = SynthesisMapper(SM_BOOL)
		sm.q = self.addSignal(None, 1)
		name = NEW_ID(__name__, node, "cmp")

		if a.q.size() != b.q.size():
			raise AssertionError

		f = self._binopmap[type(op)][0]
		f(self.module, name, a.q, b.q, sm.q, is_signed)
		return sm

	def apply_binop(self, node, a, b):

		f, ext = self._binopmap[type(node.op)]

		if a.is_signed or b.is_signed:
			is_signed = True
		else:
			is_signed = False

		sm = SynthesisMapper(SM_WIRE, is_signed)

		if ext == self.EX_COND:
			l = 1
		elif ext == self.EX_FIRST:
			l = a.q.size()
			trunc = False
		elif ext == self.EX_TWICE:
			l, trunc = match(a, b)
			l *= 2
		elif ext == self.EX_SAME:
			l, trunc = match(a, b)
		elif ext == self.EX_TRUNC:
			l = b.q.size()
			trunc = True
		elif ext == self.EX_CARRY:
			l, trunc = match(a, b)
			if not trunc:
				l += 1
			trunc = True


		sm.trunc = trunc

		# print("Add wire with name %s, size %d" % (name, l))
		sm.q = self.addSignal(None, l)
		name = NEW_ID(__name__, node, "binop_%s" % ("s" if is_signed else "u"))

		f(self.module, name, a.q, b.q, sm.q, is_signed)

		return sm

	def apply_unop(self, name, op, a, q):
		self._unopmap[type(op)](self.module, name, a, q)

	def connect(self, dst, src):
		if dst.size() != src.size():
			print(dst.size(), src.size())
			raise ValueError("Signals '%s' and '%s' don't have the same size" % \
				(dst.as_wire().name, src.as_wire().name))
		return self.module.connect(dst, src)

	def guard_name(self, name, which):
		if name in self.guard:
			raise KeyError("%s already used : %s" % (name, repr(self.guard[name])))
		self.guard[name] = which

	def addWire(self, name, n, public=False):
		# print(type(name))
		if isinstance(name, str):
			# print("not a IDstring name")
			if public:
				name = PID(name)
			else:
				name = ID(name)
		elif not name:
			name = ys.new_id(__name__, lineno(), "")

		frame = inspect.currentframe()
		info = inspect.getouterframes(frame)[2] 
		source = "%s:%d" % (info[1], info[2])

		self.guard_name(name, source)

		return Wire(self.module.addWire(name, n))

	def addSignal(self, name, n, public = False):
		w = self.addWire(name, n, public)
		return ys.SigSpec(w.get())

	def addMux(self, *args):
		name = args[0]
		self.guard_name(name, True)
		return self.module.addMux(*args)

	def addCell(self, name, celltype, builtin = False):
		if builtin:
			ct = PID(celltype)
		else:
			ct = ID(celltype)
		if isinstance(name, str):
			identifier = ID(name)
		else:
			identifier = name
		return Cell(self.module.addCell(identifier, ct))

	def addSimpleCell(self, name, which, in_a, in_b, out_y):
		c = self.addCell(name, which)
		c.setPort("A", in_a)
		c.setPort("B", in_b)
		c.setPort("Y", out_y)

	def getCorrespondingWire(self, sig):
		if not sig._id:
			raise ValueError("Can not have None as ID for %s" % sig._name)
		identifier = self.wireid[sig._id]
		w = self.findWireByName(identifier)
		if not w:
			raise KeyError("Wire `%s` not found" % identifier)
		return w


	def findWire(self, sig, reserved = False):
		# TODO: Simplify, once elegant handling found
			
		# We've got a purely local signal
		identifier = sig._name
		if not reserved:
			return self.findWireByName(identifier)
		else:
			print(REDBG + \
				"UNDEFINED/UNUSED wire, localname: %s, origin: %s" % (a._name, a._id) + OFF)
			raise KeyError("Local signal not found")


		return elem

	def findWireByName(self, identifier, throw_exception = False):
		if identifier in self.memories:
			elem = self.memories[identifier]
		elif identifier in self.arrays:
			elem = self.arrays[identifier]
		elif identifier in self.wires:
			elem = self.wires[identifier]
		elif identifier in self.variables:
			elem = self.variables[identifier]
		elif throw_exception:
			raise KeyError("Wire '%s' not found" % identifier)
		else:
			elem = None

		return elem
	
	def signal_output_type(self, sig):
		src = sig._source
		is_out = False
		if src:
			# If it's us driving the pin, we're an OUT,
			# unless we're a shadow.
			if src == self.implementation:
				if isinstance(sig, _ShadowSignal):
					print("Notice: ShadowSignal %s never an output" % sig._name)
				else:
					is_out = sig._driven
			src = src.name

		return is_out, src

	def collectArg(self, name, arg, is_port = False, force_wire = False):
		d = self.wires
		if isinstance(arg, _Signal):
			identifier = arg._id
			if identifier == None:
				# raise ValueError("Signal identifier none for '%s'" % arg._name)
				self.debugmsg("WARNING: Unused signal '%s'" % arg._name)
			elif identifier in self.wireid:
				self.debugmsg("Signal `%s` already in ID lookup table" % identifier)
				return

			self.wireid[identifier] = name # Lookup table for wire ID
			s = len(arg)
			w = self.addWire(name, s, is_port)
			sig = YSignal(w)
			is_out, src = self.signal_output_type(arg)
			# TODO: Clock signal could be flagged for debugging purposes
			# Currently, it tends to be regarded as 'floating'
			if is_out:
				self.debugmsg("\tWire OUT (%s) `%s`, id: `%s`, driver: %s" % \
					(arg._driven, name, identifier, src), col = BLUEBG)
				w.setDirection(IN=False, OUT=True)
				# If we need to create a register, replace this wire
#				if arg._driven == "reg":	
#					buf = sig
#					w = self.addWire(name + "_reg", s)
#					sig = YSignal(w)
#					self.connect(buf, sig)

			elif arg._read:
				self.debugmsg("\tWire IN `%s`, id: `%s`, origin: %s" % (name, identifier, src), col = BLUEBG)
				w.setDirection(IN=True, OUT=False)
			else:
				self.debugmsg("\tWire FLOATING %s, id: %s" % (name, identifier), col = BLUEBG)
				# FIXME
				# For now, we allocate this port as a dummy, anyway
				# Also note: clk ports are not properly marked as 'read'
				w.setDirection(IN=True, OUT=False)

			# FIXME: Works only for const values. When using a parametrized value,
			# we need to make sure the cell gets the corresponding parameter
			self.defaults[name] = arg._init
			d[name] = sig
		elif isinstance(arg, int) or isinstance(arg, bool):
			if force_wire:
				if isinstance(arg, bool):
					s = 1
				else:
					t = arg.bit_length()
					s = t if t > 0 else 1
				w = self.addWire(name, s, True)
				w.get().port_input = True
				d[name] = YSignal(w)
			else:
				d[name] = ConstSignal(arg)
		elif isinstance(arg, intbv):
			# print("Const signal Wire IN %s" % (name))
			s = len(arg)
			w = self.addWire(name, s, True)
			w.get().port_input = True
			d[name] = ConstSignal(arg)
		elif isinstance(arg, EnumType):
			# print("\tENUM %s" % arg)
			pass
		elif isinstance(arg, block):
			# print("\tSKIP block arg %s" % arg)
			pass
		elif arg == None:
			pass
		elif isinstance(arg, tuple):
			pass
		elif isinstance(arg, _BulkSignalBase):
			arg.collect(self)
		else:
			# print("Bus/Port class %s" % name)
			try:
				for i in arg.__dict__.items():
					# print("%s.%s" % (name, i[0]))
					self.collectArg(name + "_" + i[0], i[1], True)
			except AttributeError:
				raise ValueError("Unhandled object type %s for %s" % (type(arg), name))
			
	def collectAliases(self, sig, name):
		"Collect alias signals from Shadow signal"
		shadow_sig = self.addSignal('alias_' + name, 0)
		self.debugmsg("COLLECT SHADOWS FOR '%s'" % name, col = GREEN)
		self.wireid[sig._id] = name
		for a in reversed(sig._args):
			if isinstance(a, _Signal):
				identifier = a._id
				elem = self.getCorrespondingWire(a)

			elif isinstance(a, (intbv, bool)):
				elem = ConstSignal(a)
			else:
				raise ValueError("Unsupported alias argument in ConcatSignal")

			shadow_sig.append(elem)
		self.wires[name] = shadow_sig

	def dump_wires(self):
		for n, i in self.wireid.items():
			print("WIRE ID '%s' : %s" % (n, i))
			
		for n, i in self.wires.items():
			print("WIRE '%s'" % n)

	def collectWires(self, instance, args):
		def insert_wire(wtype, d, n, s):
			if not s._id:
				self.debugmsg("WARNING: Unused signal '%s'" % n)
				return None
			if isinstance(s._val, EnumItemType):
				w = self.addSignal(n, s._nrbits)
				d[n] = w
				self.wireid[s._id] = n
				return w
			else:
				self.debugmsg("%s Wire '%s' id:`%s` init: %d" % (wtype, n, s._id, s._init), col = BLUEBG)
				l = get_size(s)
				w = self.addSignal(n + "_w", l)
				d[n] = w
				self.wireid[s._id] = n
				return w

		self.defaults = initvalues = { }
		self.wires = d = { }
		blk = instance.obj
		sigs = instance.sigdict


		l = len(blk.args)
		# print("# of block arguments:", l)

		remaining = instance.symdict

		for i, a in enumerate(args):
			name, param = a
			is_port = name in blk.argdict
			if name in sigs:
				sig = sigs[name]
				self.collectArg(name, sig, is_port)
			elif i < l:
				remaining.pop(name)
				arg = blk.args[i]
				self.collectArg(name, arg, is_port)
			else:
				print("SKIP default arg %s" % name)

	
		# Collect remaining signals
		shadow_syms = {}
		for n, s in sigs.items():
			if not n in blk.argdict:
				if isinstance(s, _ShadowSignal):
					shadow_syms[n] = s
				elif not s._id in self.wireid:
					w = insert_wire("INTERNAL", d, n, s)
					initvalues[n] = s._init
		
		# z = input("HIT RETURN")

		
		# Collect local Class signals:
		for n, el in remaining.items():
			# Note: Instantiators can also create members, depending
			# on order of analysis (random dict item order)
			if inspect.isclass(type(el)) and not isinstance(el, _Instantiator):
				if isinstance(el, _BulkSignalBase):
					el.collect(self, False)
				elif hasattr(el, '__dict__'):
					for mn, member in el.__dict__.items():
						if isinstance(member, _Signal):
							identifier = "%s_%s" % (n, mn)
							if identifier not in sigs:
								w = insert_wire("CSIG", d, identifier, member)
								# print("Class sig: %s.%s" % (n, mn))

		
		# Now resolve arrays (a.k.a. memories)
		# TODO: Do that only with true arrays
		# FIXME: Depending on resolving order, a signal array might already
		# have been removed from the memory dict upon analysis
		for n, m in instance.memdict.items():
			if m.depth > self.array_limit:
				print("Array limit reached for signal arrays, SKIP")
			else:
				# print("ARRAY COLLECT `%s`" % n)
				for i, s in enumerate(m.mem):
					identifier = "%s[%d]" % (n, i)
					# Make sure to not re-define alias wires:
					if s._id not in self.wireid:
						if not s._id:
							s._id = "mem_" + identifier
							# print("\tNEW WIRE id %s" % s._id)
						else:
							pass
							# print("\tADD WIRE id %s" % s._id)
						self.wireid[s._id] = identifier
						w = insert_wire("MEM INTERNAL", d, identifier, s)
						initvalues[identifier] = s._init
					else:
						pass
						# print("\tREUSE WIRE id %s" % s._id)

		# Now handle shadow signals:

		for n, s in sigs.items():
			# print("========== %s ===========" % n)
			if len(s._slicesigs) > 0:
				w = self.findWireByName(n)
				if not w:
					raise KeyError("Signal %s not found" % n)

			for i, sl in enumerate(s._slicesigs):
				if sl._right:
					sls = w.extract(sl._right, sl._left - sl._right)
					identifier = "%s[%d:%d]" % (s._id, sl._left, sl._right)
				else:
					identifier = "%s[%d]" % (s._id, sl._left)
					sls = w.extract(sl._left, 1)
				if not sl._id:
					sl._id = identifier

				self.wireid[sl._id] = identifier

				# print("SLICE(%s) id: `%s`" % (identifier, sl._id))

				d[identifier] = sls

		for n, s in shadow_syms.items():
			self.collectAliases(s, n)
	
		self.module.fixup_ports()

	def collectMemories(self, instance):
		for m in instance.memdict.items():
			print("SIGNAL ARRAY '%s'" % m[0])
			self.memories[m[0]] = ( m[1] )

	def addMemory(self, name):
		mem = ys.Memory()
		identifier = PID(name)
		mem.name = identifier
		self.cache_mem[identifier] = mem

		return mem

	def infer_rom(self, romobj, sig_data, wire_addr):
		"Infer ROM using the blackbox synthesis method"
		name = "rom_" + romobj.name
		intf = BBInterface(name, self)

		sm = SynthesisMapper(SM_WIRE)

		# We need to create (register) a signal descriptor 'addr' for the
		# blackbox interface
		sig_addr = intf.createSignal(wire_addr, "rom_addr")
		rom = yosys_bb.Rom(sig_addr, sig_data, romobj.rom)
		rom.infer(self, intf)
		# Note we don't wire up
		
		outs = intf.getOutputs()
		sm.q = outs[0]
		return sm

	def finish(self, design):
		self.module.memories = self.cache_mem
		self.module.avail_parameters = self.avail_parameters
		mname = self.name.str()
		# self.module.check()

