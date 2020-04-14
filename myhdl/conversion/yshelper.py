# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#
import ast
import inspect
import myhdl

from myhdl import intbv
from myhdl._enum import EnumType, EnumItemType
from myhdl import ConversionError

from myhdl._util import _makeAST
from myhdl.conversion.analyze_ng import _AnalyzeTopFuncVisitor, _makeName
from myhdl._Signal import _Signal
from myhdl._block import _Block, block
from myhdl._blackbox import _BlackBox
from myhdl import intbv, EnumType, EnumItemType
from myhdl._ShadowSignal import _ShadowSignal, _SliceSignal, _TristateDriver

from myhdl.conversion._misc import (_get_argnames, _error)

from pyosys import libyosys as ys
from myhdl.conversion import blackbox

SM_NUM, SM_BOOL, SM_STRING, SM_WIRE, SM_RECORD, SM_VAR, SM_MEMPORT = range(7)

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


class SynthesisMapper:
	def __init__(self, el_type):
		self.el_type = el_type
		self.q = None
		self.is_signed = False
		self.carry = False # Carry flag

	def isConst(self):
		return self.el_type == SM_NUM

def NEW_ID(name, node, ext):
	return ys.new_id(name, node.lineno, ext)

def OBJ_ID(name, src, ext):
	return ys.IdString("$" + name + "\\" + src + "\\" + ext)

def Signal(x):
	if isinstance(x, Wire) or isinstance(x, Const):
		return ys.SigSpec(x.get())
	else:
		return ys.SigSpec(x)

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

	def addModule(self, name, implementation):
		print(GREEN + "Adding module with name:" + OFF, name)
		m = self.design.addModule(ID(name))
		return Module(m, implementation)

	def set_top_module(self, top):
		key = create_key(top.obj)
		ys.run_pass("hierarchy -top $%s" % key, self.design)

	def top_module(self):
		return Module(self.design.top_module(), None)

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

	def write_verilog(self, name, rename_default = False):
		"Write verilog"
		ys.run_pass("hierarchy -check")
		if name == None:
			name = "uut"
		design = self.design
		m = design.top_module()
		if rename_default:
			design.rename(m, ys.IdString("\\" + name))
		# Can cause failures in cosim: TODO investigate
		# ys.run_pass("write_verilog -norename %s_mapped.v" % name, design)
		ys.run_pass("write_verilog %s_mapped.v" % name, design)

	def test_synth(self):
		ys.run_pass("hierarchy -check")
		ys.run_pass("techmap -map techmap/lutrams_map.v")
		ys.run_pass("proc")


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
		if type(value) == type(1):
			if bits == None:
				l = value.bit_length()
				if l < 1:
					l = 1
				self.const = ys.Const(value, l)
			else:
				self.const = ys.Const(value, bits)
		elif isinstance(value, intbv):
			v = int(value)
			l = v.bit_length() 
			if l <= 32:
				self.const = ys.Const(int(value), len(value))
			else:
				bitvector = bitfield(v)
				print("long val %x[%d]" % (int(value), l))
				self.const = ys.Const(bitvector)
		elif isinstance(value, bool):
			self.const = ys.Const(int(value), 1)
		else:
			raise Synth_Nosupp("Unsupported type %s" % type(value).__name__)

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
	print("|| expand class", name)
	for attr, attrobj in vars(obj).items():
		if isinstance(attrobj, _Signal):
			print("\t--	 %s_%s : %s" % (name, attr, dump_sig(attrobj)))
			#					  signame = attrobj._name
			#					  if not signame:
			#						  signame = name + '_' + attr
			#						  attrobj._name = signame
			signame = name + '_' + attr
#			  signame = name + attr
				
			oldname = attrobj._name
			print("\trename local '.%s' : %s <= %s ORIGINAL '%s'" % (attr, oldname, signame, attrobj._origname))
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
	print(76 * '=')
	print("INFER INTERFACE for %s" % blk.func.__name__)
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
		self.cell.setPort(PID(name), port)

	def setParam(self, name, c):
		self.cell.setParam(PID(name), Const(c).get())

class Module:
	"Yosys module wrapper"

	EX_COND, EX_SAME, EX_CARRY, EX_TWICE = range(4)

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
		ast.Mod		 : ( ys.Module.addMod,	 EX_SAME ),
		ast.Pow		 : ( ys.Module.addPow,	 EX_SAME ),
		ast.LShift	 : ( ys.Module.addShl,	 EX_SAME ),
		ast.RShift	 : ( ys.Module.addShr,	 EX_SAME ),
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

	def __init__(self, m, implementation):
		self.module = m
		self.wires = {} # Local module wires
		self.variables = {}
		self.wiring = {}
		self.parent_signals = {}
		self.memories = {}
		self.inferred_memories = {}  # Maybe temporary: Track inferred memories
		self.guard = {}
		self.user = [] # Module users
		self.implementation = implementation
	
	def __getattr__(self, name):
		return getattr(self.module, name)

	def apply_compare(self, node, a, b, l):
		sm = SynthesisMapper(SM_BOOL)
		sm.q = self.addSignal(None, 1)
		name = NEW_ID(__name__, node, "cmp")
		op = node.ops[0]

		f = self._binopmap[type(op)][0]
		f(self.module, name, a.q, b.q, sm.q)
		return sm

	def apply_binop(self, node, a, b):

		la, lb = a.q.size(), b.q.size()
		op = node.op

		l = la

		if la < lb and isinstance(node.left.obj, _Signal):
			a.q.extend_u0(lb, a.is_signed)
			l = lb
		elif la > lb and isinstance(node.right.obj, _Signal):
			b.q.extend_u0(lb, b.is_signed)


		f, ext = self._binopmap[type(op)]
		# print(op)

		sm = SynthesisMapper(SM_WIRE)

		if ext == self.EX_COND:
			l = 1
		elif ext == self.EX_TWICE:
			l *= 2
		elif ext == self.EX_CARRY:
			l += 1
			sm.carry = True

		# print("Add wire with name %s, size %d" % (name, l))
		sm.q = self.addSignal(None, l)
		name = NEW_ID(__name__, node, "binop")

		f(self.module, name, a.q, b.q, sm.q)

		return sm

	def apply_unop(self, name, op, a, q):
		self._unopmap[type(op)](self.module, name, a, q)

	def connect(self, dst, src):
		if dst.size() != src.size():
			raise ValueError("Signals '%s' and '%s' don't have the same size" % (dst.as_wire().name, src.as_wire().name))
		return self.module.connect(dst, src)

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

		if name in self.guard:
			raise KeyError("%s already used : %s" % (name, repr(self.guard[name])))
		self.guard[name] = public
		# print("adding wire '%s'" % (name))
		return Wire(self.module.addWire(name, n))

	def addSignal(self, name, n, public = False):
		w = self.addWire(name, n, public)
		return ys.SigSpec(w.get())

	def addCell(self, name, celltype, builtin = False):
		if builtin:
			ct = PID(celltype)
		else:
			ct = ID(celltype)
		return Cell(self.module.addCell(ID(name), ct))

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
				print(">>>>> LOOKUP PARENT (FALLBACK):  %s" % identifier)
				elem = self.parent_signals[identifier]
			else:
				elem = None
		else:
			elem = None

		return elem

	def findWireByName(self, identifier):
		if identifier in self.memories:
			elem = self.memories[identifier]
		elif identifier in self.wires:
			elem = self.wires[identifier]
		elif identifier in self.wiring:
			elem = self.wires[self.wiring[identifier][0]]
		elif identifier in self.parent_signals:
			print(">>>>> LOOKUP PARENT (FALLBACK):  %s" % identifier)
			elem = self.parent_signals[identifier]
		else:
			elem = None

		return elem

	def collectArg(self, name, arg):
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
				print("\tWire OUT (%s) %s, parent: %s, driver: %s" % (arg._driven, name, pname, src))
				w.get().port_output = True
				# If we need to create a register, replace this wire
				if arg._driven == "reg":	
					buf = sig
					w = self.addWire(name + "_reg", s)
					sig = Signal(w)
					self.connect(buf, sig)

			elif arg._read:
				print("\tWire IN %s, parent %s, origin: %s" % (name, pname, src))
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
		elif isinstance(arg, int):
			print("\tConst Wire %s" % name)
			d[name] = ConstSignal(arg, arg.bit_length())
		elif isinstance(arg, bool):
			d[name] = ConstSignal(arg, 1)
		elif isinstance(arg, block):
			print("\tSKIP block arg %s" % arg)
		elif isinstance(arg, intbv):
			# print("Const signal Wire IN %s" % (name))
			s = len(arg)
			w = self.addWire(name, s, True)
			w.get().port_input = True
			d[name] = Signal(w)
		elif arg == None:
			pass
		else:
			print("Bus/Port class %s" % name)
			for i in arg.__dict__.items():
				print(".%s" % (i[0]))
				self.collectArg(name + "_" + i[0], i[1])
			


	def collectWires(self, instance, args):

		def insert_wire(wtype, d, n, s):
			if isinstance(s._val, EnumItemType):
				d[n] = self.addSignal(n, s._nrbits)
			else:
				print("%s Wire %s type %s, init: %d" % (wtype, n, repr(s._type), s._init))
				l = get_size(s)
				d[n] = self.addSignal(n, l)

		# Grab wiring from instance analysys
		self.wiring = instance.wiring
		self.defaults = initvalues = { }
		self.wires = d = { }
		blk = instance.obj
		sigs = instance.sigdict

		l = len(blk.args)
		print("# of block arguments:", l)

		for i, name in enumerate(args):
			print("ARG", name)
			if name in sigs:
				sig = sigs[name]
				self.collectArg(name, sig)
			elif i < l:
				arg = blk.args[i]
				self.collectArg(name, arg)
			else:
				print("SKIP default arg %s" % name)

		ps = self.parent_signals

		print("----- PARENT/LOCAL CONTEXT -----")

		# Collect parent signals:
		for n, s in instance.symdict.items():
			if not n in ps:
				insert_wire("PARENT", ps, n, s)
				initvalues[n] = s._init
	
		# Collect remaining symbols, typically locally defined ones:
		for n, s in sigs.items():
			if not n in blk.argdict and not n in ps:
				insert_wire("INTERNAL", d, n, s)
				initvalues[n] = s._init

		
		self.module.fixup_ports()

	def collectMemories(self, instance):
		for m in instance.memdict.items():
			print("MEMORY", m[0], m[1])
			self.memories[m[0]] = ( m[1] )

	def infer_rom(self, rom, addr_signame, data_signame):
		intf = BBInterface("bb_rom", self)
		sm = SynthesisMapper(SM_WIRE)

		# addr = self.addSignal(None, 8)
		# data = self.addSignal(None, 8)
		addr = myhdl.Signal(intbv()[8:])
		data = myhdl.Signal(intbv()[8:])
		rom = blackbox.Rom(addr, data, rom)
		rom.infer(self, intf)
		read_data = self.addSignal(None, 8)
		sm.q = read_data
		return sm

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
		print(type(x))
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
		print(GREEN + "Analyze signals for %s" % self + OFF)
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
				print("WIRE %s <--- %s (%s)" % (n, s._name, s._origname))
				continue
			if isinstance(s, _SliceSignal):
				continue
			sname = _makeName(n, [], namedict)
			if s._origname:
				print("New Name %s <= %s (%s)" % (n, sname, s._origname))
				symdict[s._origname] = s
			else:
				print("New local signal name %s <= %s (%s)" % (n, sname, s._origname))
			s._name = sname
			if not s._nrbits:
				raise ConversionError(_error.UndefinedBitWidth, s._name)
			# slice signals
			for sl in s._slicesigs:
				sl._setName(hdl)
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
			print("insert key %s" % key)

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
		elif isinstance(node, ast.Name):
			return node.value
		else:
			raise AssertionError("Unsupported op")

	def genid(self, node, ext):
		n = self.cur_module + "::" + type(node).__name__
		srcfile = self.tree.sourcefile[self.tree.sourcefile.rfind('/'):]
		src = "%s:%d" % (srcfile, node.lineno + self.tree.lineoffset)
		return OBJ_ID(n, src, ext)

	def setAttr(self, node):
		if node.attr != 'next':
			self.dbg(node, REDBG, "ERROR ",  "attr " + repr(node.attr))
		assert node.attr == 'next'
		self.visit(node.value)
		node.obj = self.getObj(node.value)
		if hasattr(node.value, "syn"):
			self.dbg(node, BLUEBG, "PASS ON ASSIGN ",  "obj: " + repr(node.value))
			node.syn = node.value.syn # pass on

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
			print("INTBV SIGNAL")
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
				n = lower.n

		elif lower == None:
			i = upper.n
			n = sig.size() - upper.n
		else:
			i = upper.n
			n = lower.n - upper.n

		sm.q = sig.extract(i, n)
		node.syn = sm

	def accessIndex(self, node):
		sm = SynthesisMapper(SM_WIRE)
		self.visit(node.value)
		try:
			sig = node.value.syn.q
		except AttributeError:
			self.raiseError(node, "%s Has no index" % type(node.value.obj))

		i = node.slice.value.n
		sm.q = sig.extract(i, 1)
		node.syn = sm

	def findWire(self, node):
		return self.context.findWire(node.obj)

	def tie_defaults(self, node):
		"Tie undefined 'other' inputs to defaults in synchronous processes"
		prev = self.state
		self.state = S_TIE_DEFAULTS
		for stmt in node.body:
			if isinstance(stmt, ast.If):
				self.visit(stmt)
		self.state = prev

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

		else:
			print("ASYNC MEM PORT")
		c.parameters[PID("MEMID")] = port.memid
		c.parameters[PID("ABITS")] = len(port.addrsig)
		c.parameters[PID("WIDTH")] = data_w

		return c, en
		
	def handle_toplevel_reset_process(self, node, func, reset, clk, clkpol):
		"Handle top level synchronous processes with reset"
		m = self.context
		for stmt in node.body:
			self.dbg(stmt, GREEN, "SEQ_STMT", stmt)
			self.visit(stmt)
			if isinstance(stmt, ast.If):
				func(m, stmt, reset, clk, clkpol)

	def handle_toplevel_process(self, node, func, clk, clkpol):
		"Handle top level processes"
		m = self.context
		for stmt in node.body:
			self.dbg(stmt, GREEN, "STMT", stmt)
			self.visit(stmt)
			if isinstance(stmt, ast.If):
				func(m, stmt, clk, clkpol)
			elif isinstance(stmt, ast.Assign):
				lhs = stmt.targets[0]
				n = lhs.obj._name
				# Ugly: ad-hoc insert drivers:
				stmt.syn.drivers = { n : [stmt.syn.q, None] }
				func(m, stmt, clk, clkpol)
			# Special treatment for memory port without condition:
			# Wire EN pins to True
			elif stmt.syn.el_type == SM_MEMPORT:
				cc = m.addSignal(None, 0)
				c = ConstSignal(True)
				en_sig = stmt.syn.sources['enable']
				for i in range(en_sig.size()):
					cc.append(c)
				m.connect(en_sig, cc)
			else:
				self.dbg(stmt, REDBG, "HANDLE OTHER", stmt)

	def handle_mux_statement(self, cond, stmt, casemap):
		"Handle multiplexer case"
		MARK = "\033[7;32m"

		m = self.context

		# List of sources that needs to be tracked to top hierarchy
		sources = []

		for t in stmt:
			if isinstance(t, ast.Assign):
				if hasattr(t.syn, "sources") and 'enable' in t.syn.sources:
					self.dbg(t, REDBG, "SOURCE", "Open source from %s" % t.syn.memid)
					next_en = m.addSignal(None, 1)
					q = m.addSignal(None, 1)
					name = NEW_ID(__name__, t, "and_enable")
					and_cell = m.addAnd(name, next_en, cond, q)
					cc = m.addSignal(None, 0)
					en_sig = t.syn.sources['enable']
					for i in range(en_sig.size()):
						cc.append(q)
					m.connect(en_sig, cc)
					sources.append(t.syn.sources)
				else:
					sigid = t.targets[0].obj._name
					target = m.findWireByName(sigid)
					l = target.size()
					if sigid in casemap:
						self.dbg(t, REDBG, "DRV_OBSOLETE",	"ineffective previous assignment to '%s'" % sigid)
					b = t.value
					mux_b = mux_input(b, target)
					casemap[sigid] = [ mux_b ]
					
			elif isinstance(t, ast.If):
				if t.ignore:
					self.dbg(t, REDBG, "SKIP_IF",	"ineffective if statement")
				else:
					self.dbg(t, VIOBG, "VISIT_MUX_NODE",  "")
					for sigid, drv in t.syn.drivers.items():
						if sigid in casemap:
							self.dbg(t, MARK, "DRV",  "%s has default. Driver entry: %s" % (sigid, drv))
							print("previous:", casemap[sigid])
							self.context.connect(drv[1], casemap[sigid][0])
							casemap[sigid].insert(0, drv[0])
						else:
							casemap[sigid] = [drv[0]]

			else:
				self.dbg(t, MARK, "UNSUPPORTED",  "generating mux")
				raise AssertionError("Unhandled statement")

		return sources

	def mapToPmux(self, node, sync = False):
		print("MAP_PMUX %d" % len(node.tests))
		m = self.context
		cc = m.addSignal(None, 0)

		muxmap = {}

		l = len(node.tests)

		for i, test in enumerate(node.tests):
			t = test[0]
			self.dbg(t, GREEN, "CASE[%d]" % i,	"")
			cc.append(t.syn.q)
			casemap = {}
			self.handle_mux_statement(t.syn.q, test[1], casemap)

			self.dbg(test, GREEN, "\n-- CASEMAP PMUX --", "parallel multiplexer map output:")

			for n, item in casemap.items():
				print("   %s ===> %s" % (n, repr(i)))
				target = m.findWireByName(n)

				if not n in muxmap:
					muxmap[n] = [ None for i in range(l) ]
				muxmap[n][i] = item[0]

				if len(item) == 2:
					self.dbg(test, REDBG, "-- OVERRIDE DEFAULT --", "\n\n")

			self.dbg(test, GREEN, "-- CASEMAP END --", "\n\n")
	
		elseclause = node.else_
		if elseclause:
			print(GREEN + "OTHERS" + OFF)
			elsemap = {}
			self.handle_mux_statement(True, elseclause, elsemap)

		other_map = {}
		for e, i in elsemap.items():
			other_map[e] = i[0]
	
		sm = SynthesisMapper(SM_RECORD)
		sm.drivers = {}

		for wn, item in muxmap.items():
			w = m.findWireByName(wn)
			varray = m.addSignal(None, 0)
			for j in item:
				if j:
					self.dbg(t, REDBG, "MUX_INPUT",  "create mux input " + wn + " type %s" % type(w))
					print("Width:", w.size())
					varray.append(j)
						
					
			y = m.addSignal(self.genid(node, wn + "_out"), w.size())

			name = NEW_ID(__name__, node, "pmux")


			self.dbg(t, REDBG, "MUX_INPUT",  "create mux input " + wn + " type %s" % type(w))

			if wn in other_map:
				a = other_map[wn]
			else:
				a = m.addSignal(self.genid(node, wn + "_other"), w.size())

			m.addPmux(name, a, varray, cc, y)
			sm.drivers[wn] = [ y, None ]
	
#		self.dbg(node, GREEN, "\n\n-- PMUXMAP --", "multiplexer map output:")
#		for n, i in muxmap.items():
#			print("   %s ===> %s" % (n, repr(i)))
#
#		self.dbg(node, GREEN, "-- PMUXMAP END --", "\n\n")
			
		node.syn = sm

	def mapToMux(self, node, sync = False):
		m = self.context
		muxmap = {}
		sm = SynthesisMapper(SM_RECORD)

		for test, stmt in node.tests:
			self.dbg(test, GREEN, "-- IF --",  "handle test %s" % test)

			casemap = {}

			cond = test.syn.q
			if isinstance(cond, ast.Name):
				s = m.findWireByName(cond.id)
			elif isinstance(cond, ys.SigSpec):
				s = cond
			elif isinstance(cond, Wire):
				s = Signal(cond)
			else:
				print(type(cond))
				raise Synth_Nosupp("Unsupported MapMux selector type ")

			self.handle_mux_statement(cond, stmt, casemap)

			self.dbg(test, GREEN, "\n-- CASEMAP --", "multiplexer map output:")
			for n, i in casemap.items():
				# print("	%s ===> %s" % (n, repr(i)))

				target = m.findWireByName(n)
				l = target.size()


				mux_b = i[0]
				name = self.genid(test, n)
				# self.dbg(test, BLUEBG, "ADD_SIGNAL",	"%s" % name)
				other = m.addSignal(name, l)

				if n in muxmap:
					y = muxmap[n][1] # Grab previous 'other'
				else:
					y = m.addSignal(self.genid(test, n + "_out"), l)
					self.dbg(test, BLUEBG, "INSERT NEW OUTPUT",  n)
					muxmap[n] = [ y, other ]

				name = self.genid(test, "mux_" + n)
				m.addMux(name, other, mux_b, s, y)
				muxmap[n][1] = other

				if len(i) == 2:
					self.dbg(test, REDBG, "-- OVERRIDE DEFAULT --", "\n\n")
					# m.connect(other, i[1])

			self.dbg(test, GREEN, "-- CASEMAP END --", "\n\n")

		elseclause = node.else_
		if elseclause:
			elsemap = {}
			self.handle_mux_statement(True, elseclause, elsemap)

			self.dbg(node, REDBG, "\n\n-- ELSE CASE --", "multiplexer map output:")

			for n, i in elsemap.items():
				# print("	%s ===> %s" % (n, repr(i)))
				target = m.findWireByName(n)

				if len(i) == 2:
					b, other = i
				else:
					b = i[0]

				# Check if we did not assign to this target in the 'case' section:
				if n not in casemap:
					self.dbg(node, REDBG, "MISSING CASE", " No default for %s" % n)
					
				if n in muxmap:
					y, other = muxmap[n]
					m.connect(other, b)
					muxmap[n][1] = None # Mark as connected
				else:
					muxmap[n] = [ b, other ]
					self.dbg(node, REDBG, "NO DEFAULT", " No default for %s" % n)

		self.dbg(node, GREEN, "\n\n-- MUXMAP --", "multiplexer map output:")
#		for n, i in muxmap.items():
#			print("   %s ===> %s" % (n, repr(i)))

		self.dbg(node, GREEN, "-- MUXMAP END --", "\n\n")

		sm.drivers = muxmap

		node.syn = sm

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
				self.dbg(stmt, GREEN, "PORT ASSIGN", "PORT local: '%s', port: '%s', sig: %s" % (name, portname, signame))
				dst, src = (outsig, result)
			else:
				# Try find a locally declared signal:
				outsig = m.findWireByName(name)
				if outsig:
					dst, src = (outsig, result)
				else:
					self.dbg(stmt, REDBG, "UNCONNECTED", "PORT local: '%s', orig: '%s'" % (name, oname))
					raise AssertionError
		else:
			outsig = m.findWireByName(name)
			signame = outsig.as_wire().name
			self.dbg(stmt, REDBG, "SIGNAL local: '%s', %s" % (name, signame))
			# Simply connect RHS to LHS:
			dst, src = (outsig, result)

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

	def addWire(self, sig, out = False):
		m = self.module
		if isinstance(sig, _Signal):
			s = len(sig)
			w = m.addWire(None, s, True)
			if not out:
				w.get().port_output = True
				w.get().port_input = False
			else:
				w.get().port_output = False
				w.get().port_input = True

			sigspec = ys.SigSpec(w.get())
			self.interface[sig._name] = sigspec
		else:
			raise AssertionError("Not a Signal")
			
		return sigspec
		
