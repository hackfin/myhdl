# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#
import ast
import inspect
import myhdl
import os

from myhdl import ConversionError

from myhdl._util import _makeAST
from myhdl.conversion.analyze_ng import _AnalyzeTopFuncVisitor, _makeName, \
	_slice_constDict
from myhdl._Signal import _Signal
from myhdl._block import _Block, block
from myhdl._blackbox import _BlackBox
from myhdl import intbv, EnumType, EnumItemType
from myhdl._ShadowSignal import _ShadowSignal, _SliceSignal, _TristateDriver

from myhdl.conversion._misc import (_get_argnames, _error)

from pyosys import libyosys as ys
from myhdl.conversion import yosys_bb

SM_NUM, SM_BOOL, SM_STRING, SM_WIRE, SM_RECORD, SM_VAR, SM_MEMPORT, SM_ARRAY = range(8)

DEFER_MUX, DEFER_RESERVED = range(2)

REDBG = "\033[7;31m"
VIOBG = "\033[7;35m"
BLUEBG = "\033[7;34m"
GREEN = "\033[32m"
OFF = "\033[0m"

# Visitor states:
S_NEUTRAL, S_COLLECT, S_MUX , S_TIE_DEFAULTS = range(4)


class DebugOutput:
	debug = False
	def dbg(self, node, kind, msg = "DBG", details = "MARK"):
		lineno = self.getLineNo(node)
		lineno += self.tree.lineoffset
		if kind == REDBG or self.debug:
			print("%s: %s:%d %s" % (kind + msg + OFF, self.tree.sourcefile, lineno, details))

class Synth_Nosupp(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

def ID(x):
	return ys.IdString("$" + x)

def PID(x):
	return ys.IdString("\\" + x)

def lineno():
	return inspect.currentframe().f_back.f_lineno


def match(a, b):
	"Match signal lengths"

	la, lb = a.q.size(), b.q.size()

	l = la

	if la < lb: # and isinstance(node.left.obj, _Signal):
		a.q.extend_u0(lb, a.is_signed)
		l = lb
	elif la > lb: # and isinstance(node.right.obj, _Signal):
		b.q.extend_u0(la, b.is_signed)
	
	return l

class SynthesisMapper:
	def __init__(self, el_type, is_signed = False):
		self.el_type = el_type
		self.q = None
		self.trunc = False # True when truncation allowed
		self.is_signed = is_signed

	def isConst(self):
		return self.el_type == SM_NUM

	def __repr__(self):
		types = [ "NUM", "BOOL", "STRING", "WIRE", "RECORD", "VAR", "MEMPORT" ]
		if self.q:
			identifier = "$"
		else:
			identifier = "X"
		return "[%s: %s]" % (types[self.el_type], identifier)

def ConstDriver(val, bit_len = None):
	if val < 0:
		signed = True
	else:
		signed = False

	sm = SynthesisMapper(SM_NUM, signed)
	sm.q = ConstSignal(val, bit_len)

	return sm
		
def NEW_ID(name, node, ext):
	return ys.new_id(name, node.lineno, ext)

def OBJ_ID(name, src, ext):
	return ys.IdString("$" + name + "\\" + src + "\\" + ext)

def Signal(x):
	return ys.SigSpec(x.get())

def ConstSignal(x, l = None):
	c = Const(x, l)
	return ys.SigSpec(c.get())

def SigBit(x):
	if isinstance(x, Wire):
		return ys.SigBit(x.get())
	else:
		return ys.SigBit(x)


class Design:
	"Simple design wrapper"
	def __init__(self, name="top"):
		self.design = ys.Design()
		self.name = name

	def get(self):
		return self.design

	def addModule(self, name, implementation, builtin = False):
		print(GREEN + "Adding module with name:" + OFF, name)
		if builtin:
			n = PID(name)
		else:
			n = ID(name)
		m = self.design.addModule(n)
		return Module(m, implementation)

	def set_top_module(self, top):
		key = create_key(top.obj)
		ys.run_pass("hierarchy -top $%s" % key, self.design)

	def top_module(self):
		return Module(self.design.top_module(), None)

	def run(self, cmd):
		"Careful. This function can exit without warning"
		ys.run_pass(cmd, self.design)

	def display_rtl(self, selection = "", fmt = None, full = False):
		"Display first stage RTL"
		design = self.design
		print("Display...")
		# ys.run_pass("ls", design)
		#
		sel = selection
		if fmt:
			fmt = "-format " + fmt
			if full:
				sel = "*"
		else:
			fmt = ""
		ys.run_pass("show %s -prefix %s %s" % (fmt, self.name, sel), design)

	def display_dir(self):
		ys.run_pass("ls", self.design)

	def write_ilang(self, name = "top"):
		ys.run_pass("write_ilang %s_mapped.il" % name, self.design)

	def import_verilog(self, filename):
		ys.run_pass("read_verilog %s" % filename, self.design)

	def finalize(self, name = None):
		"Finalize design so that it is visible"
		design = self.design
		m = design.top_module()

		if name == None:
			name = self.name

		design.rename(m, PID(name))

	def write_verilog(self, name, rename_default = False, rename_signals = True):
		"Write verilog"
		ys.run_pass("hierarchy -check")
		if name == None:
			name = "uut"
		design = self.design
		m = design.top_module()
		if rename_default:
			design.rename(m, ys.IdString("\\" + name))
		if rename_signals:
			ys.run_pass("write_verilog %s_mapped.v" % name, design)
		else:
			# Can cause failures in cosim: TODO investigate
			ys.run_pass("write_verilog -norename %s_mapped.v" % name, design)


	def test_synth(self):
		design = self.design
		ys.run_pass("memory_collect", design)
		# We don't test on that level yet
		# ys.run_pass("techmap -map techmap/lutrams_map.v", design)
		# ys.run_pass("techmap -map ecp5/brams_map.v", design)
		# ys.run_pass("techmap -map ecp5/cells_map.v", design)
		ys.run_pass("write_ilang %s_mapped.il" % self.name, design)
		ys.run_pass("hierarchy -check", design)



class Wire:
	"Tight wire wrapper"
	def __init__(self, wire):
		self.wire = wire

	def get(self):
		return self.wire

	def __getattr__(self, name):
		return getattr(self.wire, name)

def bitfield(n):
	l = [ys.State(int(digit)) for digit in bin(n)[2:]]
	l.reverse()
	return l

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

def dump_sig(x):

	if x._driven:
		a = "ACT "
	elif x._read:
		a = "PAS  "
	else:
		a = "--- "

	if x._name == None:
		a += "''"
	else:
		a += x._name


	return a
	

def expandinterface(v, name, obj):
	# print("|| expand class", name)
	for attr, attrobj in vars(obj).items():
		if isinstance(attrobj, _Signal):
			# print("\t--	 %s_%s : %s" % (name, attr, dump_sig(attrobj)))
			#					  signame = attrobj._name
			#					  if not signame:
			#						  signame = name + '_' + attr
			#						  attrobj._name = signame
			signame = name + '_' + attr
#			  signame = name + attr
				
			oldname = attrobj._name
			# print("\trename local '.%s' : %s <= %s ORIGINAL '%s'" % (attr, oldname, signame, attrobj._origname))
			attrobj._name = signame
			
			# check if already in
#					  if v.fullargdict.has_key(signame):
#						  raise ConversionError(_error.NameCollision, signame)
			v.argdict[signame] = attrobj
			v.argnames.append(signame)
		elif isinstance(attrobj, EnumType):
			pass
		elif hasattr(attrobj, '__dict__'):
			# can assume is yet another interface ...
			expandinterface(v, name + '_' + attr, attrobj)


def infer_interface(blk):
	"Our own interface inferring, preserving wiring hierarchy"
	# print(76 * '=')
	# print("INFER INTERFACE for %s" % blk.func.__name__)
	tree = _makeAST(blk.func)
	v = _AnalyzeTopFuncVisitor(blk.func, tree, *blk.args, **blk.kwargs)
	v.visit(tree)

	objs = []
	for name, obj in v.fullargdict.items():
		if not isinstance(obj, _Signal):
			objs.append((name, obj))

	# now expand the interface objects
	for name, obj in objs:
		if hasattr(obj, '__dict__'):
			# must be an interface object (probably ...?)
			expandinterface(v, name, obj)

	blk.argnames = v.argnames
	blk.argdict = v.argdict


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

class Module:
	"Yosys module wrapper"

	EX_COND, EX_SAME, EX_CARRY, EX_TWICE, EX_TRUNC = range(5)

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
		ast.LShift	 : ( ys.Module.addSshl,	 EX_SAME ),
		ast.RShift	 : ( ys.Module.addSshr,	 EX_SAME ),
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
		self.wiring = {}
		self.parent_signals = {}
		self.memories = {}
		self.arrays = {}
		self.inferred_memories = {}  # Maybe temporary: Track inferred memories
		self.guard = {}
		self.user = [] # Module users
		self.implementation = implementation

		self._namespace = \
			[ self.memories, self.arrays, self.wires, self.parent_signals ]
	
	def __getattr__(self, name):
		return getattr(self.module, name)

	def apply_compare(self, node, a, b):
		op = node.ops[0]

		# Have to sort out cases:

		l = match(a, b)

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

		l = match(a, b)

		f, ext = self._binopmap[type(node.op)]

		if a.is_signed or b.is_signed:
			is_signed = True
		else:
			is_signed = False

		sm = SynthesisMapper(SM_WIRE, is_signed)

		if ext == self.EX_COND:
			l = 1
		elif ext == self.EX_TWICE:
			l *= 2
		elif ext == self.EX_TRUNC:
			sm.trunc = True
		elif ext == self.EX_CARRY:
			l += 1
			sm.trunc = True

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

		self.guard_name(name, public)

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

	def findWire(self, sig, local = False):
		# TODO: Simplify, once elegant handling found
			
		# We've got a purely local signal
		identifier = sig._name
		if identifier in self.memories:
			elem = self.memories[identifier]
		elif identifier in self.wires:
			elem = self.wires[identifier]
		elif not local:
			identifier = sig._origname

			if identifier in self.memories:
				elem = self.memories[identifier]
			elif identifier in self.wires:
				elem = self.wires[identifier]
			elif identifier in self.wiring:
				elem = self.wires[self.wiring[identifier][0]]
			elif identifier in self.parent_signals:
				# print(">>>>> LOOKUP PARENT (FALLBACK):  %s" % identifier)
				elem = self.parent_signals[identifier]
			else:
				elem = None
		else:
			elem = None

		return elem

	def findWireByName(self, identifier):
		if identifier in self.memories:
			elem = self.memories[identifier]
		elif identifier in self.arrays:
			elem = self.arrays[identifier]
		elif identifier in self.wires:
			elem = self.wires[identifier]
		elif identifier in self.wiring:
			elem = self.wires[self.wiring[identifier][0]]
		elif identifier in self.parent_signals:
			# print(">>>>> LOOKUP PARENT (FALLBACK):  %s" % identifier)
			elem = self.parent_signals[identifier]
		else:
			elem = None

		return elem

	def collectArg(self, name, arg, force_wire = False):
		d = self.wires
		if isinstance(arg, _Signal):
			s = len(arg)
			w = self.addWire(name, s, True)
			pname = arg._origname
			src = arg._source
			is_out = False
			sig = Signal(w)
			if src:
				# If it's us driving the pin, we're an OUT:
				if src == self.implementation:
					is_out = arg._driven
				src = src.name
			# TODO: Clock signal could be flagged for debugging purposes
			# Currently, it tends to be regarded as 'floating'
			if is_out:
				#print("\tWire OUT (%s) %s, parent: %s, driver: %s" % (arg._driven, name, pname, src))
				w.get().port_output = True
				# If we need to create a register, replace this wire
				if arg._driven == "reg":	
					buf = sig
					w = self.addWire(name + "_reg", s)
					sig = Signal(w)
					self.connect(buf, sig)

			elif arg._read:
				#print("\tWire IN %s, parent %s, origin: %s" % (name, pname, src))
				w.get().port_input = True
			else:
				print("\tWire FLOATING %s, parent %s" % (name, pname))
				# FIXME
				# For now, we allocate this port as a dummy, anyway
				# Also note: clk ports are not properly marked as 'read'
				w.get().port_input = True

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
				d[name] = Signal(w)
			else:
				d[name] = ConstSignal(arg)
		elif isinstance(arg, block):
			# print("\tSKIP block arg %s" % arg)
			pass
		elif isinstance(arg, intbv):
			# print("Const signal Wire IN %s" % (name))
			s = len(arg)
			w = self.addWire(name, s, True)
			w.get().port_input = True
			d[name] = Signal(w)
		elif isinstance(arg, EnumType):
			# print("\tENUM %s" % arg)
			pass
		elif arg == None:
			pass
		elif isinstance(arg, tuple):
			pass
		else:
			# print("Bus/Port class %s" % name)
			try:
				for i in arg.__dict__.items():
					# print(".%s" % (i[0]))
					self.collectArg(name + "_" + i[0], i[1])
			except AttributeError:
				raise ValueError("Unhandled object type %s for %s" % (type(arg), name))
			
	def collectAliases(self, sig, name):
		"Collect alias signals from Shadow signal"
		shadow_sig = self.addSignal(None, 0)
		for a in reversed(sig._args):
			if isinstance(a, _Signal):
				elem = self.findWireByName(a._name)
				if not elem:
					raise KeyError("%s not found" % a._name)
			elif isinstance(a, (intbv, bool)):
				elem = ConstSignal(a)
			else:
				raise ValueError("Unsupported alias argument in ConcatSignal")

			shadow_sig.append(elem)
		self.wires[name] = shadow_sig


	def collectWires(self, instance, args):
		def insert_wire(wtype, d, n, s):
			if isinstance(s._val, EnumItemType):
				w = self.addSignal(n, s._nrbits)
				d[n] = w
				return w
			else:
				# print("%s Wire %s type %s, init: %d" % (wtype, n, repr(s._type), s._init))
				l = get_size(s)
				w = self.addSignal(n, l)
				d[n] = w
				return w

		# Grab wiring from instance analysys
		self.wiring = instance.wiring
		self.defaults = initvalues = { }
		self.wires = d = { }
		blk = instance.obj
		sigs = instance.sigdict

		l = len(blk.args)
		# print("# of block arguments:", l)

		for i, a in enumerate(args):
			name, param = a
			# print("ARG", name)
			if name in sigs:
				sig = sigs[name]
				self.collectArg(name, sig)
			elif i < l:
				arg = blk.args[i]
				self.collectArg(name, arg)
			else:
				print("SKIP default arg %s" % name)

		ps = self.parent_signals

		# print("----- PARENT/LOCAL CONTEXT -----")

		# Collect parent signals:
		for n, s in instance.symdict.items():
			if not n in ps:
				insert_wire("PARENT", ps, n, s)
				initvalues[n] = s._init

	
		# Collect remaining symbols, typically locally defined ones:
		shadow_syms = []
		for n, s in sigs.items():
			if not n in blk.argdict and not n in ps:
				if isinstance(s, _ShadowSignal):
					shadow_syms.append((n, s))
				else:
					w = insert_wire("INTERNAL", d, n, s)
					initvalues[n] = s._init

		for n, s in sigs.items():
			for sl in s._slicesigs:
				w = self.findWireByName(s._name)
				if sl._right:
					sls = w.extract(sl._right, sl._left - sl._right)
				else:
					sls = w.extract(sl._left, 1)
				d[sl._name] = sls

		for i in shadow_syms:
			n, s = i
			self.collectAliases(s, n)
		
		self.module.fixup_ports()

	def collectMemories(self, instance):
		for m in instance.memdict.items():
			# print("MEMORY", m[0], m[1])
			self.memories[m[0]] = ( m[1] )

	def addMemory(self, name):
		mem = ys.Memory()
		identifier = PID(name)
		mem.name = identifier
		print("ADDING MEMORY %s" % name)
		self.cache_mem[identifier] = mem

		return mem

	def infer_rom(self, romobj, sig_data, wire_addr):
		"Infer ROM using the blackbox synthesis method"
		name = "rom_" + romobj.name
		intf = BBInterface(name, self)

		sm = SynthesisMapper(SM_WIRE)

		# We need to create (register) a signal descriptor 'addr' for the
		# blackbox interface
		sig_addr = intf.createSignal(wire_addr)
		rom = yosys_bb.Rom(sig_addr, sig_data, romobj.rom)
		rom.infer(self, intf)

		# Don't wire up
		# intf.wireup(True)
		outs = intf.getOutputs()
		sm.q = outs[0]
		return sm

	def finish(self, design):
		self.module.memories = self.cache_mem
		self.module.avail_parameters = self.avail_parameters
		mname = self.name.str()
		# self.module.check()

def dump(n):
	if isinstance(n, ast.Num):
		return "%d" % n.n
	else:
		return repr(n)

def mux_input(x, templ):
	if isinstance(x, EnumItemType):
		x = ConstSignal(int(x), templ.size())
	elif isinstance(x, int):
		x = ConstSignal(int(x), 32)
	elif isinstance(x, bool):
		x = ConstSignal(int(x), 1)
	elif isinstance(x, ast.Num):
		x = ConstSignal(int(x.n), templ.size())
	elif isinstance(x, Const):
		x = x.syn.q
		x.extu(templ.size())
	elif isinstance(x, Wire):
		if x.size() == templ.size():
			pass
		else:
			raise AssertionError("Not of same size")
	else:
		# print(type(x))
		x = x.syn.q

	return x

#################################################################

from itertools import chain

class Instance:
	"""
 Instance / signal analysis class
 ===================================

 Note: depending on the order of sub-modules, naming procedure is pretty random.
 There are several cases:
 1) Signal driven by current (parenting) level
 2) Signal driven by instance (sub module), child level

 Again, forking from these cases:

 a) Signal driven to port output
 b) Signal driven to sub module port input

 If a signal was already named by another routine, this routine will not
 override the previous name by any specific rule, means, the naming
 may be according to the order of sub module analysys (avoid this by
 using OrderedDict in future)


 Now there's a catch: Signals become registered, when they are used.
 So from the above cases, a signal might be left unregistered in the
 parent level when it is not used in the latter.

 Therefore, the signal gets named/registered upon creation of
 a child instance. See also `._source` member below.

 Assume case 2.b:
 - Signal declared in parent: 'port_a', but not driven/read in parent
 - port_a driven by child module B, read by child module A
 - Signal port_a passed as (implicit output) parameter `b_out` to B
 - Signal port_a passed as (implicit input) parameter `a_in` to A

 When seen first (driven) in B, it's registered as local name `b_out`.
 When seen first in A, it takes the name `a_in`.

 Solution:

 During expansion of the interface in the block initialization, we assign an
 original signal name in the top level name space of the module.

 During analysis, a wire map is created as follows:
 - When a new local name `._name` is created, the signal's `._origname`
   is used as key for insertion into the module symbol dictionary.
   From this entry, a per-module wire is created.
 - The ._name of a signal during 'elaboration' is obviously different
   than the local wire name created (according to argument names).
   Therefore we need to maintain a lookup `.wiring` map.

  Input/Output port handling
  ===========================

  Port Signals are driven in two variants by a module:
  - 'reg': A register is instanced 
  - 'wire': A simple output is driven only

  To resolve in/out per module, we need to keep track of the driver
  origin. This introduces a new `._source` member for a _Signal type.

"""

	__slots__ = ['level', 'obj', 'subs', 'sigdict', 'symdict', 'memdict', 'wiring', 'name', 'genlist', 'instances', 'cell']

	def __init__(self, level, obj, subs):
		self.level = level
		self.obj = obj
		self.subs = subs
		self.sigdict = obj.sigdict
		self.symdict = obj.symdict
		self.memdict = obj.memdict
		self.wiring = {}
		self.name = None
		self.cell = False

	def __repr__(self):
		return "< Instance %s >" % self.name

	def dump(self):
		print("===== DUMP SIGNALS, INSTANCE  %s =====" % self.name)
		for n, i in self.sigdict.items():
			if isinstance(i, _Signal):
				print("SIGNAL %s [%d]" % (n, len(i)))
			elif hasattr(i, '__dict__'):
				print("CLASS %s (type %s)" % (n, type(i).__name__))
			else:
				print("OTHER %s (type %s)" % (n, type(i).__name__))

#	def signals_name_init(self):
#		"Hack to pre-init names of locally declared signals"
#		def expand(parent, names, level):
#			if level > 5:
#				return
#			for n, i in names.items():
#				if isinstance(i, _Signal):
#					if i._name == None:
#						name = parent + n
#						print("Init Signal name %s" % name)
#						i._name = name
#					else:
#						print("Signal already has name %s" % i._name)
#				elif hasattr(i, '__dict__'):
#					expand(n + '_', i.__dict__, level + 1)
#			
#		expand("", self.symdict, 0)
		

	def analyze_signals(self, symdict):
		# print(GREEN + "Analyze signals for %s" % self + OFF)
		sigdict = self.sigdict
		memdict = self.memdict
		siglist = []
		memlist = []

		# self.dump()
		# self.signals_name_init()

		namedict = dict(chain(sigdict.items(), memdict.items()))

		for n, s in sigdict.items():
			if s._name is not None:
				# For local signal dictionary, create port wiring map:
				self.wiring[s._name] = (n, s)
				# print("WIRE %s <--- %s (%s)" % (n, s._name, s._origname))
				continue
			if isinstance(s, _SliceSignal):
				continue
			sname = _makeName(n, [], namedict)
			if s._origname:
				# print("New Name %s <= %s (%s)" % (n, sname, s._origname))
				symdict[s._origname] = s
			else:
				# print("New local signal name %s <= %s (%s)" % (n, sname, s._origname))
				pass
			s._name = sname
			if not s._nrbits:
				raise ConversionError(_error.UndefinedBitWidth, s._name)
			# slice signals
			for sl in s._slicesigs:
				sl._setName("Verilog")
			siglist.append(s)
		# list of signals
		for n, m in memdict.items():
			if m.name is not None:
				continue
			m.name = _makeName(n, [], namedict)
			memlist.append(m)

		return siglist, memlist


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
	c = type(inst)
	print(c)

	a = ""
	for i in inst.__dict__.items():
		a = append_sig(i[1], a)

	return a

def create_key(inst):
	"Create a unique key for a specific instance"
	a = inst.func.__name__
	for i in inst.args:
		a = append_sig(i, a)

	return a


class Hierarchy:
	"""Hierarchy class for modular transfer languages which don't require flattening
the entire design. However, they need to maintain a parameter dictionary for
differing instances of the same architecture"""


	def _getHierarchyHelper(self, level, modinst, hierarchy):
		if isinstance(modinst, _Block):
			impl = modinst.func.__name__
			# Create some 'hash' according to interface specs
			key = create_key(modinst)

			subs = [(s.name, s) for s in modinst.subs]
			inst = Instance(level, modinst, subs)
			hierarchy.append(inst)

			if key in self.users:
				self.users[key].append(inst)
				inst.cell = True
			else:
				self.users[key] = [ inst ]

			for i in modinst.subs:
				self._getHierarchyHelper(level + 1, i, hierarchy)


	def __init__(self, name, modinst):
		self.top = modinst
		self.hierarchy = hierarchy = []
		self.absnames = absnames = {}
		self.users = {}
		self.instdict = {}
		self._getHierarchyHelper(1, modinst, hierarchy)
		# compatibility with _extractHierarchy
		# walk the hierarchy to define relative and absolute names
		names = {}
		top_inst = hierarchy[0]
		obj, subs = top_inst.obj, top_inst.subs

		names[id(obj)] = name
		absnames[id(obj)] = name
		for inst in hierarchy:
			obj, subs = inst.obj, inst.subs
			inst.name = names[id(obj)]
			tn = absnames[id(obj)]
			for sn, so in subs:
				names[id(so)] = sn
				absnames[id(so)] = "%s_%s" % (tn, sn)



class VisitorHelper(DebugOutput):
	"""Visitor helper class for yosys interfacing
Used for separation of common functionality of visitor classes"""

	# Note: Python3 specific
	_opmap_reduce_const = {
		ast.Add		 : int.__add__,
		ast.Sub		 : int.__sub__,
		ast.Mult	 : int.__mul__,
		ast.Div		 : int.__floordiv__,
		ast.Mod		 : int.__mod__,
		ast.Pow		 : int.__mod__,
		ast.LShift	 : int.__lshift__,
		ast.RShift	 : int.__rshift__,
		ast.BitOr	 : int.__or__,
		ast.BitAnd	 : int.__and__,
		ast.BitXor	 : int.__xor__,
		ast.FloorDiv : int.__floordiv__,
		ast.Invert	 : int.__mod__,
		ast.UAdd	 : int.__add__,
		ast.USub	 : int.__sub__,
		ast.And		 : int.__and__,
		ast.Or		 : int.__or__,
	}

	def const_eval(self, node):
		if isinstance(node, ast.BinOp):
			l = self.const_eval(node.left)
			r = self.const_eval(node.right)
			f = self._opmap_reduce_const[type(node.op)]
			return f(l, r)
		elif isinstance(node, ast.Num):
			return node.n
		elif hasattr(node, "value"):
			return node.value
		else:
			self.raiseError(node, "Unsupported operator")

	def node_tag(self, node):
		srcfile = os.path.basename(self.tree.sourcefile)
		src = self.srcformat % (srcfile, node.lineno + self.tree.lineoffset)
		return src

	def genid(self, node, ext):
		n = self.cur_module + "::" + type(node).__name__
		if isinstance(node, str):
			return ys.IdString("$" + node + "\\" + ext)
		else:
			srcfile = os.path.basename(self.tree.sourcefile)
			src = self.srcformat % (srcfile, node.lineno + self.tree.lineoffset)
		return OBJ_ID(n, src, ext)

	def setAttr(self, node):
		"Called upon .next = ..."
		if node.attr != 'next':
			self.dbg(node, REDBG, "ERROR ",  "attr " + repr(node.attr))
		assert node.attr == 'next'
		self.dbg(node, BLUEBG, "VISIT", node.value)
		self.visit(node.value)
		node.obj = self.getObj(node.value)
		if hasattr(node.value, "syn"):
			self.dbg(node, BLUEBG, "PASS ON ASSIGN ",  "sig: %s/%s" % (node.value.id, node.obj._name), )
			node.syn = node.value.syn # pass on

		node.id = node.value.id

	def getAttr(self, node):
		if isinstance(node.value, ast.Subscript):
			self.setAttr(node)
			return

		assert isinstance(node.value, ast.Name), node.value
		n = node.value.id
		if n in self.tree.symdict:
			obj = self.tree.symdict[n]
		elif n in self.tree.vardict:
			obj = self.tree.vardict[n]
		else:
			raise AssertionError("object not found")
		if isinstance(obj, _Signal):
			self.dbg(obj, VIOBG, "getAttr ",	"signal " + repr(node))
			if node.attr == 'next':
				self.SigAss = obj._name
				self.visit(node.value)
			elif node.attr == 'posedge':
				self.dbg(obj, VIOBG, "POSEDGE** ",  "clk " + repr(node))
				self.polarity = 1
			elif node.attr == 'negedge':
				self.polarity = -1
			elif node.attr == 'val':
				# pre, suf = self.inferCast(node.vhd, node.vhdOri)
				self.visit(node.value)
		elif isinstance(obj, (_Signal, intbv)):
			# print("INTBV SIGNAL")
			if node.attr in ('min', 'max'):
				pre, suf = self.inferCast(node.vhd, node.vhdOri)
		elif isinstance(obj, EnumType):
			assert hasattr(obj, node.attr)
			sm = SynthesisMapper(SM_WIRE)
			e = getattr(obj, node.attr)
			sm.q = ConstSignal(int(e), obj._nrbits)
			node.syn = sm
		else:
			self.dbg(obj, REDBG, "getAttr ",	"unknown " + repr(obj))

	def accessSlice(self, node):
		sm = SynthesisMapper(SM_WIRE)
		self.visit(node.value)
		sig = node.value.syn.q
		lower, upper = node.slice.lower, node.slice.upper
		if upper == None:
			i = 0
			if lower == None:
				n = sig.size()
			else:
				n = self.const_eval(lower)

		elif lower == None:
			i = self.const_eval(upper)
			n = sig.size() - i
		else:
			i = self.const_eval(upper)
			n = self.const_eval(lower) - i

		if sig.size() < (i + n):
			self.raiseError(node, "Invalid signal size: %d < %d" % (sig.size(), i + n))
		# Pyosys can segfault if we don't do the above check
		# NASTY.
		sm.q = sig.extract(i, n)
		node.syn = sm

	def get_index(self, idx):
		if hasattr(idx, 'value'):
			i = idx.value
		elif isinstance(idx, ast.Name):
			# If we're a global variable, assume we're a named slice:
			try:
				if idx.id in _slice_constDict:
					i = _slice_constDict[idx.id]
				else:
					i = self.loopvars[idx.id]
			except KeyError:
				self.raiseError(idx, "Symbol not found: %s" % idx.id)

		elif isinstance(idx, ast.Num):
			i = idx.n
		else:
			i = self.const_eval(idx)

		return i

	def accessIndex(self, node):
		sm = SynthesisMapper(SM_WIRE)
		self.visit(node.slice)
		self.visit(node.value)
		idx = node.slice.value
		obj = node.value.obj

		if isinstance(idx, ast.Call):
			self.visit(idx)
			if idx.syn.el_type in [ SM_WIRE, SM_VAR ]:
				m = self.context
				name = self.genid(node, "slice_out")
				y = m.addSignal(name, 1)
				name = self.genid(node, "slice")
				m.addSimpleCell(name, "dynslice", node.value.syn.q, idx.syn.q, y)
				sm.q = y
				# self.raiseError(idx, "Slice inference not yet supported")
			else:
				self.raiseError(idx, "Unsupported index type: %s" % (idx.syn.el_type))
		elif isinstance(idx, _Signal):
			self.raiseError(idx, "Do not ")
		else:
			i = self.get_index(idx)

			try:
				sig = node.value.syn.q
				# Inherit signedness:
				sm.is_signed = node.value.syn.is_signed
			except AttributeError:
				self.raiseError(node, "Unsynthesized argument %s" % type(obj))
			if isinstance(i, slice):
				n = i.start - i.stop
				if n < 0:
					raise ValueError("Bad slice value")
				sm.q = sig.extract(i.stop, n)
			else:
				sm.q = sig.extract(i, 1)

		node.syn = sm

	def findWire(self, node):
		return self.context.findWire(node.obj)

	def handle_memport(self, port, name, which):
		m = self.context
		c = m.addCell(name, ID(which))
		port_addr = m.wires[port.addrsig._name]
		data_w = port.q.size() # Number of data bits
		c.setPort(PID("DATA"), port.q)
		c.setPort(PID("ADDR"), port_addr)

		en = m.addSignal(None, data_w)
		c.setPort(PID("EN"), en)
			
		if self.clk != None:
			clk = m.wires[self.clk._name]
			c.setPort(PID("CLK"), clk)
			c.parameters[PID("CLK_ENABLE")] = 1
			if self.clkpol:
				c.parameters[PID("CLK_POLARITY")] = 1
			else:
				c.parameters[PID("CLK_POLARITY")] = 0

		c.parameters[PID("MEMID")] = port.memid
		c.parameters[PID("ABITS")] = len(port.addrsig)
		c.parameters[PID("WIDTH")] = data_w

		return c, en

	def assign_default(self, name, dst, defdict, toplevel = False):
		m = self.context
		if name in defdict:
			previous = defdict[name][0]
			ret = True
		# When on toplevel, we can assume default = previous value
		elif toplevel:
			w = m.findWireByName(name)
			if w:
				previous = w
				ret = 2
			elif name in self.variables:
				previous = self.variables[name]
				ret = True
			else:
				return False
		else:
			return False

		m.connect(dst, previous)
		return ret
	
	def handle_toplevel_reset_process(self, node, func, reset, clk, clkpol):
		"Handle top level synchronous processes with reset"
		m = self.context
		default_assignments = {}
		for stmt in node.body:
			self.dbg(stmt, GREEN, "SEQ_STMT", stmt)
			self.visit(stmt)
			if isinstance(stmt, ast.If):
				if stmt.ignore:
					continue
				sm = stmt.syn
				for n, drv in sm.drivers.items():
					y, other, default = drv
					if default:
						print("TIE DEFAULT", n)
						self.assign_default(n, default, default_assignments, True)
					if other:
						self.assign_default(n, other, default_assignments, True)

					if n in default_assignments:
						default_assignments[n][2] = False # Clear flag

				func(m, stmt, reset, clk, clkpol)
				# Now if we have an open 'other' input, tie it to default:
			elif isinstance(stmt, ast.Assign):
				# This gets nasty. An assigment can be a default signal for subsequent
				# assignments, or a one time thing.
				lhs = stmt.targets[0]
				n = stmt.id
				if not n in default_assignments:
					default_assignments[n] = [stmt.syn.q, stmt, True]
				else:
					self.dbg(stmt, REDBG, "WARNING", "Overriding statement")
					raise AssertionError
			else:
				self.dbg(stmt, REDBG, "HANDLE OTHER", stmt)

		# Now assign all non-muxed (left over) signals (those with flag still set):
		for n, i in default_assignments.items():		
			if i[2]:
				self.dbg(i, BLUEBG, "FINAL ASSIGN", n)
				i[1].syn.drivers = { n : [i[0], None, None] }
				func(m, i[1], reset, clk, clkpol)

	def handle_toplevel_process(self, node, func, clk, clkpol = False):
		"Handle top level processes"
		m = self.context
		default_assignments = {}
		for stmt in node.body:
			self.visit(stmt)
			if clk:
				self.dbg(stmt, GREEN, "STMT_SYNC", clk._name)
			else:
				self.dbg(stmt, GREEN, "STMT_COMB", "async")
			if isinstance(stmt, ast.If):
				if not stmt.ignore:
					sm = stmt.syn
					for n, drv in sm.drivers.items():
						y, other, default = drv
						if default:
							ret = self.assign_default(n, default, default_assignments, True)
							if clk == None and ret == 2:
								self.dbg(stmt, REDBG, "LATCH_WARNING", \
									"Incomplete 'default' assignments, latch created for %s" % n)
						if other:
							ret = self.assign_default(n, other, default_assignments, True)
							if clk == None and ret == 2:
								self.dbg(stmt, REDBG, "LATCH_WARNING", \
									"Incomplete 'other' assignments, latch created for %s" % n)


						if n in default_assignments:
							default_assignments[n][2] = False

					func(m, stmt, clk, clkpol)
			elif isinstance(stmt, ast.Assign):
				# This gets nasty. An assigment can be a default signal for subsequent
				# assignments, or a one time thing.
				lhs = stmt.targets[0]
				name = stmt.id
				if isinstance(lhs, ast.Name):
					pass
				elif isinstance(lhs.obj, _Signal):
					pass
				elif isinstance(lhs, ast.Subscript):
					rhs = stmt.value
					# Legacy allows lhs.value to be an attribute.
					if __legacy__:
						if isinstance(lhs.value, ast.Attribute):
							self.dbg(stmt, REDBG, "LEGACY_ASSIGN", rhs.syn.q)
							m.connect(lhs.syn.q, rhs.syn.q)
					else:
						self.variables[lhs.value.id] = rhs.obj

				if not name in default_assignments:
					default_assignments[name] = [stmt.syn.q, stmt, True]
				else:
					self.dbg(stmt, REDBG, "WARNING", "Overriding statement")

			# Special treatment for memory port without condition:
			# Wire EN pins to True
			elif isinstance(stmt, ast.For):
				pass
			else:
				if stmt.syn.el_type == SM_MEMPORT:
					cc = m.addSignal(None, 0)
					c = ConstSignal(True)
					en_sig = stmt.syn.sources['enable']
					for i in range(en_sig.size()):
						cc.append(c)
					m.connect(en_sig, cc)
				else:
					self.dbg(stmt, REDBG, "UNHANDLED", "")
		
		# Left overs (non-muxed):
		for n, i in default_assignments.items():		
			if i[2]:
				self.dbg(i, BLUEBG, "FINAL ASSIGN", n)
				i[1].syn.drivers = { n : [i[0], None, None] }
				func(m, i[1], clk, clkpol)

	def handle_mux_table(self, stmt, defaults, implicit, drv, n, pos):

		if isinstance(stmt, ast.Assign):
			name = stmt.id
			self.dbg(stmt, BLUEBG, "SET DEFAULT", name)
			if not name in drv:
				drv[name] = [ ("default_%d" % i, None) for i in range(n) ]
			mux_id = self.node_tag(stmt)
			# Assign nodes have a simple synthesis output
			drv[name][pos] = (mux_id, stmt.syn.q)
			if name in defaults:
				self.dbg(stmt, REDBG, "DEFAULT OVERRIDE", name)
				# FIXME:
				# if name not in self.context.arrays:
				self.raiseError(stmt, "Default override not allowed")
			else:
				defaults[name] = [stmt.syn.q, stmt] # Local default

		elif isinstance(stmt, ast.If):
			if stmt.ignore:
				return

			for t in stmt.drivers.items():
				name, i = t
				mux_id = self.node_tag(stmt)
				y, other, default = stmt.syn.drivers[name] # Get output, other and default sources

				ret0, ret1 = True, True

				if other:
#					self.dbg(stmt, REDBG, "IMPLICIT_WARNING", \
#						"(other) missing assignments, assuming defaults for %s" % name)
					ret0 = self.assign_default(name, other, defaults)
					if not ret0:
						self.dbg(stmt, REDBG, "APPEND OPEN OTHER", "%s" % name)

				if default:
#					self.dbg(stmt, REDBG, "IMPLICIT_WARNING", \
#						"(default) missing assignments, assuming defaults %s" % name)
					ret1 = self.assign_default(name, default, defaults)
					if not ret1:
						self.dbg(stmt, REDBG, "APPEND OPEN DEFAULT", "%s" % name)

				if ret0 or ret1:
					if name in implicit:
						implicit[name].append([other, default])
					else:
						implicit[name] = [[other, default]]

				if name in drv:
					drv[name][pos] = (mux_id, y)
				else:
					drv[name] = [ ("%s_%s_default" % (mux_id, name), None) for _ in range(n)]
					drv[name][pos] = (mux_id, y)

		elif isinstance(stmt, ast.Pass):
			self.dbg(stmt, VIOBG, "NOTICE",  "empty case (pass)")
		else:
			self.dbg(stmt, REDBG, "UNSUPPORTED", \
				"generating mux for %s" % type(stmt))
			raise AssertionError("Unhandled statement")

	def create_mux_table(self, node, implicit):
		m = self.context
		n = len(node.tests)
		n += 1

		# We store all potential signal drivers in this node
		# context:
		node.drivers = drivers = {}
		decision_signals = []
		sm = SynthesisMapper(SM_RECORD)
		sm.drivers = {}
		c = 1
		for test, suite in node.tests:
			# print(test, suite)
			sig_s = self.from_condition(test)
			decision_signals.append(sig_s)
			defaults = {}
			for stmt in suite:
				self.handle_mux_table(stmt, defaults, implicit, drivers, n, c)
			c += 1

		defaults = {}
		# If we have an else clause, store at col 0 in table
		for stmt in node.else_:
			self.handle_mux_table(stmt, defaults, implicit, drivers, n, 0)

		node.syn = sm

		return decision_signals


	def mapToPmux(self, node):
		node.implicit = implicit = {}
		decision_signals = self.create_mux_table(node, implicit)

		m = self.context
		for dr_id, drivers in node.drivers.items():
			self.dbg(node, GREEN, "PMUX WALK DRV >>>", dr_id)
			w = m.findWireByName(dr_id)
			proto = w if w else self.variables[dr_id].q
			size = proto.size()

			varray = m.addSignal(None, 0)
			default = None

			cc = m.addSignal(None, 0)
			for i, drvdesc in enumerate(drivers[1:]):
				mux_id, drv = drvdesc
				if not drv:
					if not default:
						name = self.genid(node, "%s_default" % dr_id)
						default = m.addSignal(name, size)
					drv = default

				cc.append(decision_signals[i])
				varray.append(drv)

			other = drivers[0][1] # First is 'other'

			if other:
				o = other
				other = None # Mark in driver map we're fully resolved
			else:
				# Create an open 'other' signal
				name = self.genid(node, "%s_other" % dr_id)
				other = o = m.addSignal(name, size)
	
			y = m.addSignal(self.genid(node, dr_id + "_out"), size)

			name = self.genid(node, "PMUX_%s" % dr_id)

			m.addPmux(name, o, varray, cc, y)
			node.syn.drivers[dr_id] = [ y, other, default ]
			self.tie_implicit(node, dr_id)

	def mapToMux(self, node):
		node.implicit = implicit = {}
		decision_signals = self.create_mux_table(node, implicit)

		m = self.context
		for dr_id, drivers in node.drivers.items():
			w = m.findWireByName(dr_id)
			# Get prototype from origin value:
			proto = w if w else self.variables[dr_id].q
			size = proto.size()
			
			chain_out = m.addSignal(None, size)
			y = chain_out # Start
			# Now we chain the muxers:

			# The default signal comes into play when we are missing
			# an explicit assignment for a muxed signal within a specific condition.
			# It is created on demand below.
			default = None

			for i, drvdesc in enumerate(drivers[1:-1]):
				mux_id, drv = drvdesc
				if not drv:
				# We have no assignment, use default:
					if not default:
						name = self.genid(node, "%s_default" % dr_id)
						default = m.addSignal(name, size)
					drv = default

				name = self.genid(mux_id, "MUX_%s" % dr_id)
				other = m.addSignal(None, size)
				s = decision_signals[i]
				m.addMux(name, other, drv, s, y)
				y = other # next output is previous other

			else_sig = drivers[0][1] # First is other

			if else_sig:
				next_other = else_sig
				else_sig = None # Mark in driver map we're fully resolved
			else:
				# Create an open 'next_other' signal
				name = self.genid(node, "%s_other" % dr_id)
				next_other = m.addSignal(name, size)
				else_sig = next_other

			# Last one
			mux_id, drv = drivers[-1]
			if not drv:
				if not default:
					name = self.genid(mux_id, "%s_default_last" % dr_id)
					default = m.addSignal(name, size)
				drv = default

			s = decision_signals[-1]
			name = self.genid(mux_id, "MUX_%s" % dr_id)
			m.addMux(name, next_other, drv, s, y)

			# Insert output and `else_sig` into multiplexer
			# tracking map:
			node.syn.drivers[dr_id] = [ chain_out, else_sig, default ]

			self.tie_implicit(node, dr_id)


	def tie_implicit(self, node, dr_id):
		"""Ties implicitely-assigned signals to a default and eventually pass it on to upper level"""
		chain_out, other, default = node.syn.drivers[dr_id]
		m = self.context

		# First, we can tie other to default. Then we can take it out of 'open drivers' list.
		if other and default:
			m.connect(other, default)
			node.syn.drivers[dr_id][1] = None

		# Now we collect all open drivers from .implicit lists. These are the 'open' and 'default'
		# drivers collected from lower hierarchies.
		if dr_id in node.implicit:
			for o, d in node.implicit[dr_id]:
				if d:
					if not default:
						name = self.genid(node, "%s_tie_default" % dr_id)
						default = m.addSignal(name, d.size())
						node.syn.drivers[dr_id][2] = default
					m.connect(d, default)
				elif o:
					if not other:
						if not default:
							name = self.genid(node, "%s_tie_other" % dr_id)
							other = m.addSignal(name, o.size())
							m.connect(o, other)
							node.syn.drivers[dr_id][1] = other
					else:
						m.connect(o, other)
		
	def handle_toplevel_assignment(self, stmt):
		"Auxiliary for signal wiring"

		lhs = stmt.targets[0]
		rhs = stmt.value
		result = stmt.syn.q
		m = self.context
		sig = lhs.obj 
		name = sig._name
		oname = sig._origname
		if oname:
			# Do we have an active wiring for the original name?
			if oname in m.wiring:
				# print("WIRING", m.wiring[oname])
				portname = m.wiring[oname][0]
				outsig = m.findWireByName(name)
				signame = outsig.as_wire().name
				self.dbg(stmt, GREEN, "PORT ASSIGN", \
					"PORT local: '%s', port: '%s', sig: %s" % (name, portname, signame))
				dst, src = (outsig, result)
			else:
				# Try find a locally declared signal:
				outsig = m.findWireByName(name)
				if outsig:
					dst, src = (outsig, result)
				else:
					self.dbg(stmt, REDBG, "UNCONNECTED", \
						"PORT local: '%s', orig: '%s'" % (name, oname))
					raise AssertionError
		else:
			outsig = m.findWireByName(name)
			signame = outsig.as_wire().name
			self.dbg(stmt, BLUEBG, "SIGNAL local: '%s', %s" % (name, signame))
			# Simply connect RHS to LHS:
			dst, src = (outsig, result)

		# dst.replace(0, src)
		m.connect(dst, src)


############################################################################
# Factory auxiliaries:
#

class yosys:
	def __init__(self):
		self.id = "YOSYS_SYNTHESIS"

class BBInterface:
	"Black box interface"
	def __init__(self, name, module):
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

	def createSignal(self, wire):
		name = "rom_addr"
		l = wire.size()
		sig = myhdl.Signal(intbv()[l:])
		sig._name = name
		self.interface[name] = ( wire, False )
		return sig

	def addWire(self, sig, out = False):
		m = self.module
		if isinstance(sig, _Signal):
			sigid = sig._name
			if sigid == None:
				raise AssertionError("Signal must be named")

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
		else:
			raise AssertionError("Not a Signal")
			
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
			# print("wire: arg %s" % n)

			s, direction = i
			sig = m.findWireByName(n)
			w = s.as_wire()
			# Reversed!
			if direction == 0:
				m.connect(s, sig)
			else:
				if defer:
					pass
				else:
					m.connect(sig, s)
		
