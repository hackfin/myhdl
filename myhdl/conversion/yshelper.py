# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#
import ast
import inspect

from myhdl import intbv
from myhdl._enum import EnumType, EnumItemType

from myhdl._Signal import _Signal
from myhdl._block import _Block, block
from myhdl import intbv, EnumType, EnumItemType

from myhdl.conversion._misc import (_get_argnames)

from pyosys import libyosys as ys

SM_NUM, SM_BOOL, SM_STRING, SM_WIRE, SM_RECORD, SM_VAR = range(6)

DEFER_MUX, DEFER_RESERVED = range(2)

REDBG = "\033[7;31m"
VIOBG = "\033[7;35m"
BLUEBG = "\033[7;34m"
GREEN = "\033[32m"
OFF = "\033[0m"

# Visitor states:
S_NEUTRAL, S_COLLECT, S_MUX , S_TIE_DEFAULTS = range(4)


class DebugOutput:
	def dbg(self, node, kind, msg = "DBG", details = "MARK"):
		lineno = self.getLineNo(node)
		lineno += self.tree.lineoffset
		# if kind == REDBG:
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

	def addModule(self, name):
		print("Adding module with name:", name)
		m = self.design.addModule(ID(name))
		return Module(m)

	def set_top_module(self, top):
		key = create_key(top.obj)
		ys.run_pass("hierarchy -top $%s" % key, self.design)

	def display_rtl(self, selection = "", pdf = False):
		"Display first stage RTL"
		design = self.design
		print("Display...")
		# ys.run_pass("ls", design)
		if pdf:
			fmt = "-format pdf"
		else:
			fmt = ""
		ys.run_pass("show %s -prefix %s $%s" % (fmt, self.name, selection), design)

	def display_dir(self):
		ys.run_pass("ls", self.design)

	def write_ilang(self, name = "top"):
		ys.run_pass("write_ilang %s_mapped.il" % name, self.design)

	def write_verilog(self, name, rename_default = False):
		"Write verilog"
		ys.run_pass("hierarchy -check")
		if name == None:
			name = "uut"
		design = self.design
		m = design.top_module()
		if rename_default:
			design.rename(m, ys.IdString("\\" + name))
		ys.run_pass("write_verilog %s_mapped.v" % name, design)

class Wire:
	"Tight wire wrapper"
	def __init__(self, wire):
		self.wire = wire

	def get(self):
		return self.wire

	def __getattr__(self, name):
		return getattr(self.wire, name)

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
			self.const = ys.Const(int(value), len(value))
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


class Module:
	"Yosys module wrapper"

	EX_COND, EX_SAME, EX_CARRY, EX_TWICE = range(4)

	_opmap = {
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
		ast.Invert	 : ( ys.Module.addNot,	 EX_SAME ),
		ast.Not		 : ( ys.Module.addNot,	 EX_SAME ),
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

	def __init__(self, m):
		self.module = m
		self.wires = {} # Local module wires
		self.variables = {}
		self.wiring = {}
		self.guard = {}
		self.user = [] # Module users
	
	def __getattr__(self, name):
		return getattr(self.module, name)

	def apply_compare(self, node, a, b, l):
		sm = SynthesisMapper(SM_BOOL)
		sm.q = self.addSignal(None, 1)
		name = NEW_ID(__name__, node, "cmp")
		op = node.ops[0]

		f = self._opmap[type(op)][0]
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


		f, ext = self._opmap[type(op)]
		# print(op)
		# z = input("HIT RETURN")

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
		self._opmap[type(op)](self.module, name, a, q)

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

	def collectWires(self, instance, args):
		initvalues = { }
		d = { }
		blk = instance.obj
		sigs = instance.sigdict

		l = len(blk.args)
		print(l)

		for i, name in enumerate(args):
			print("It ", i)
			if name in sigs:
				sig = sigs[name]
				s = len(sig)
				if isinstance(sig, _Signal):
					w = self.addWire(name, s, True)
					pname = sig._name
					if name != pname:
						self.wiring[pname] = name
					if sig._driven:
						print("Wire OUT %s, parent: %s" % (name, pname))
						w.get().port_output = True
					else:
						print("Wire IN %s, parent %s" % (name, pname))
						w.get().port_input = True
					
					# FIXME: Works only for const values. When using a parametrized value,
					# we need to make sure the cell gets the corresponding parameter
					initvalues[name] = sig._init
					d[name] = Signal(w)
				else:
					raise AssertionError("Unsupported wire")
			elif i < l:
				arg = blk.args[i]
				if isinstance(arg, int):
					print("Const Wire %s" % name)
					d[name] = ConstSignal(arg, arg.bit_length())
				elif isinstance(arg, block):
					print("SKIP block arg %s" % arg)
				else:
					raise Synth_Nosupp("Unsupported wire type %s, signal '%s' in %s" % (type(arg).__name__, name, instance.name))
			else:
				print("SKIP default arg %s" % name)

		for n, s in sigs.items():
			if not n in blk.argdict:
				if isinstance(s._val, EnumItemType):
					d[n] = self.addSignal(n, s._nrbits)
				else:
					print("Internal Wire %s type %s, init: %d" % (n, repr(s._type), s._init))
					l = get_size(s)
					d[n] = self.addSignal(n, l)

				initvalues[n] = s._init

		self.defaults = initvalues
		self.wires = d
		self.module.fixup_ports()

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

class Instance:
	__slots__ = ['level', 'obj', 'subs', 'sigdict', 'memdict', 'name', 'genlist', 'instances', 'cell']

	def __init__(self, level, obj, subs, sigdict, memdict):
		self.level = level
		self.obj = obj
		self.subs = subs
		self.sigdict = sigdict
		self.memdict = memdict
		self.name = None
		self.cell = False

	def __repr__(self):
		return self.name

def create_key(inst):
	"Create a unique key for a specific instance"
	a = inst.func.__name__
	for i in inst.args:
		if isinstance(i, _Signal) or isinstance(i, list) or isinstance(i, tuple):
			a += "_%d" % len(i)
		elif isinstance(i, int):
			a += "_c%d" % i
		elif isinstance(i, block):
			a += '_%s_' % i.func.__name__
		else:
			raise TypeError("Unsupported entity argument type in %s" % inst.name)

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
			inst = Instance(level, modinst, subs, modinst.sigdict, modinst.memdict)
			hierarchy.append(inst)

			if key in self.users:
				self.users[key].append(inst)
				inst.cell = True
			else:
				self.users[key] = [ inst ]

			for inst in modinst.subs:
				self._getHierarchyHelper(level + 1, inst, hierarchy)

	def __init__(self, name, modinst):
		self.top = modinst
		self.hierarchy = hierarchy = []
		self.absnames = absnames = {}
		self.users = {}
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
			l, r = node.left.n, node.right.n
			f = self._opmap_reduce_const[type(node.op)]
			return f(l, r)
		else:
			raise AssertionError("Unsupported op")

	def genid(self, node, ext):
		n = self.cur_module + "::" + type(node).__name__
		src = "%s:%d" % (self.tree.sourcefile, node.lineno + self.tree.lineoffset)
		return OBJ_ID(n, src, ext)

	def setAttr(self, node):
		if node.attr != 'next':
			self.dbg(node, REDBG, "ERROR ",  "attr " + repr(node.attr))
		assert node.attr == 'next'
		self.visit(node.value)
		node.obj = self.getObj(node.value)

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
			self.dbg(t, VIOBG, "getAttr ",	"signal " + repr(node))
			if node.attr == 'next':
				self.SigAss = obj._name
				self.visit(node.value)
			elif node.attr == 'posedge':
				self.dbg(t, VIOBG, "POSEDGE** ",  "clk " + repr(node))
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
		sig = node.value.syn.q
		sm.q = sig.extract(node.slice.value.n, 1)
		node.syn = sm

	def findSignal(self, node):
		identifier = node.obj._name
		if identifier in self.context.wires:
			elem = self.context.wires[identifier]
		else:
			elem = self.context.wires[self.context.wiring[identifier]]

		return elem

	def tie_defaults(self, node):
		"Tie undefined 'other' inputs to defaults in synchronous processes"
		prev = self.state
		self.state = S_TIE_DEFAULTS
		for stmt in node.body:
			if isinstance(stmt, ast.If):
				self.visit(stmt)
		self.state = prev

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


	def handle_mux_statement(self, stmt, casemap):
		"Handle multiplexer case"
		MARK = "\033[7;32m"

		wires = self.context.wires

		for t in stmt:
			if isinstance(t, ast.Assign):
				sigid = t.targets[0].obj._name
				target = wires[sigid]
				l = target.size()
				if sigid in casemap:
					self.dbg(t, REDBG, "DRV_OBSOLETE",	"ineffective previous assignment to '%s'" % sigid)
				b = t.value
				mux_b = mux_input(b, target)
				casemap[sigid] = [ mux_b ]
			elif isinstance(t, ast.If):
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
			self.handle_mux_statement(test[1], casemap)

			self.dbg(test, GREEN, "\n-- CASEMAP PMUX --", "parallel multiplexer map output:")

			for n, item in casemap.items():
				print("   %s ===> %s" % (n, repr(i)))
				target = m.wires[n]

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
			self.handle_mux_statement(elseclause, elsemap)

		other_map = {}
		for e, i in elsemap.items():
			other_map[e] = i[0]
	
		sm = SynthesisMapper(SM_RECORD)
		sm.drivers = {}

		for wn, item in muxmap.items():
			w = m.wires[wn]
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
				s = m.wires[cond.id]
			elif isinstance(cond, ys.SigSpec):
				s = cond
			elif isinstance(cond, Wire):
				s = Signal(cond)
			else:
				print(type(cond))
				raise Synth_Nosupp("Unsupported MapMux selector type ")

			self.handle_mux_statement(stmt, casemap)

			self.dbg(test, GREEN, "\n-- CASEMAP --", "multiplexer map output:")
			for n, i in casemap.items():
				# print("   %s ===> %s" % (n, repr(i)))

				target = m.wires[n]
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
			self.handle_mux_statement(elseclause, elsemap)

			self.dbg(node, REDBG, "\n\n-- ELSE CASE --", "multiplexer map output:")

			for n, i in elsemap.items():
				# print("   %s ===> %s" % (n, repr(i)))
				target = m.wires[n]

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

