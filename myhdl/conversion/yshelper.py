# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#
import ast
import inspect

from myhdl import intbv
from myhdl._enum import EnumType, EnumItemType

from myhdl._Signal import _Signal
from myhdl import intbv, EnumType, EnumItemType

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
		self.a = None
		self.b = None

def NEW_ID(name, node, ext):
	return ys.new_id(name, node.lineno, ext)

def OBJ_ID(name, src, ext):
	return ys.IdString("$" + name + "\\" + src + "\\" + ext)

def Signal(x):
	return ys.SigSpec(x.get())

def ConstSignal(x, l):
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

	def display_rtl(self, pdf = False):
		"Display first stage RTL"
		design = self.design
		print("Display...")
		ys.run_pass("ls", design)
		if pdf:
			fmt = "-format pdf"
		else:
			fmt = ""
		ys.run_pass("show %s -prefix %s" % (fmt, self.name), design)

	def write_verilog(self, name, rename_default = False):
		"Write verilog"
		design = self.design
		m = design.top_module()
		if rename_default:
			design.rename(m, ys.IdString("\\uut"))
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
				self.const = ys.Const(value, 32)
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

	_opmap = {
		ast.Add      : ys.Module.addAdd,
		ast.Sub      : ys.Module.addSub,
		ast.Mult     : ys.Module.addMul,
		ast.Div      : ys.Module.addDiv,
		ast.Mod      : ys.Module.addMod,
		ast.Pow      : ys.Module.addPow,
		ast.LShift   : ys.Module.addShl,
		ast.RShift   : ys.Module.addShr,
		ast.BitOr    : ys.Module.addOr,
		ast.BitAnd   : ys.Module.addAnd,
		ast.BitXor   : ys.Module.addXor,
		ast.FloorDiv : ys.Module.addDiv,
		# ast.Invert   : ys.Module.addNotGate,
		ast.Not      : ys.Module.addNot,
		ast.UAdd     : ys.Module.addAdd,
		ast.USub     : ys.Module.addSub,
		ast.Eq       : ys.Module.addEq,
		ast.Gt       : ys.Module.addGt,
		ast.GtE      : ys.Module.addGe,
		ast.Lt       : ys.Module.addLt,
		ast.LtE      : ys.Module.addLe,
		ast.NotEq    : ys.Module.addNe,
		ast.And      : ys.Module.addAnd,
		ast.Or       : ys.Module.addOr
	}

	def __init__(self, m):
		self.module = m
		self.wires = {}
		self.variables = {}
		self.guard = {}
	
	def __getattr__(self, name):
		print("calling %s" % name)
		return getattr(self.module, name)

	def apply_binop(self, name, op, a, b, q):
		print("ADDING OBJECT", name)
		self._opmap[type(op)](self.module, name, a, b, q)

	def addWire(self, name, n, public=False):
		# print(type(name))
		if isinstance(name, str):
			# print("not a IDstring name")
			if public:
				name = PID(name)
			else:
				name = ID(name)
		elif not name:
			print("Create random name")
			name = ys.new_id(__name__, lineno(), "")

		if name in self.guard:
			raise KeyError("%s already used : %s" % (name, repr(self.guard[name])))
		self.guard[name] = public
		# print("adding wire '%s'" % (name))
		return Wire(self.module.addWire(name, n))

	def addSignal(self, name, n, public = False):
		w = self.addWire(name, n, public)
		return ys.SigSpec(w.get())

	def collectWires(self, sigs, sigdict):
		initvalues = { }
		d = { }
		print(sigs)
		i = 0
		for name, sig in sigdict.items():
			l = len(sig)
			w = self.addWire(name, l, True)
			if sig._driven:
				print("Wire OUT %s" % name)
				w.get().port_output = True
			else:
				print("Wire IN %s" % name)
				w.get().port_input = True

			i += 1

			initvalues[name] = sig._init
			d[name] = Signal(w)

		for s in sigs:
			n = s._name
			if not n in sigdict:
				if isinstance(s._val, EnumItemType):
					d[n] = self.addSignal(n, s._nrbits)
				else:
					print("Internal Wire %s type %s" % (n, repr(s._type)))
					l = get_size(s)
					d[n] = self.addSignal(n, l)

				initvalues[n] = s._init

		self.defaults = initvalues
		self.wires = d
		self.module.fixup_ports()

def run_synth_ecp5(design):
	YOSYS_TECHLIBS  = "/media/sandbox/usr/share/yosys"

	ys.run_pass("proc", design)	
	ys.run_pass("flatten", design)	
	ys.run_pass("tribuf -logic", design)	
	ys.run_pass("deminout", design)	
	ys.run_pass("opt_expr", design)	
	ys.run_pass("opt_clean", design)	
	ys.run_pass("check", design)	
	ys.run_pass("opt", design)	
	ys.run_pass("wreduce", design)	
	ys.run_pass("peepopt", design)	
	ys.run_pass("opt_clean", design)	
	ys.run_pass("share", design)	
	ys.run_pass("techmap -map %s/cmp2lut.v -D LUT_WIDTH=4" % YOSYS_TECHLIBS)
	ys.run_pass("dffsr2dff; dff2dffs; opt_clean")
	ys.run_pass("dff2dffe -direct-match $_DFF_* -direct-match $__DFFS_*")
	ys.run_pass("techmap -D NO_LUT -map %s/ecp5/cells_map.v" % YOSYS_TECHLIBS)
	ys.run_pass("opt_expr -undriven -mux_undef; simplemap; ecp5_ffinit")
	ys.run_pass("abc")
	ys.run_pass("techmap -map %s/ecp5/latches_map.v" % YOSYS_TECHLIBS)
	ys.run_pass("abc -lut 4:7 -dress")
	ys.run_pass("clean")
	ys.run_pass("stat", design)	
	ys.run_pass("show -prefix syn", design)




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

def to_driver(x):

	if isinstance(x, bool):
		x = ConstSignal(int(x), 1)
		t = SM_BOOL
	elif isinstance(x, int):
		x = ConstSignal(int(x), 32)
		t = SM_WIRE
	else:
		# print("=====> RHS: %s[%d:]" % (type(x).__name__, l), type(x.syn.q).__name__)
		return x.syn

	sm = SynthesisMapper(t)
	sm.q = x

	return sm

class VisitorHelper:
	"""Visitor helper class for yosys interfacing
Used for separation of common functionality of visitor classes"""

	def genid(self, node, ext):
		n = self.cur_module + "::" + type(node).__name__
		src = "%s:%d" % (self.tree.sourcefile, node.lineno + self.tree.lineoffset)
		return OBJ_ID(n, src, ext)

	def dbg(self, node, kind, msg = "DBG", details = "MARK"):
		lineno = self.getLineNo(node)
		lineno += self.tree.lineoffset
		print("%s: %s:%d %s" % (kind + msg + OFF, self.tree.sourcefile, lineno, details))

	def setAttr(self, node):
		assert node.attr == 'next'
		if isinstance(node.value, ast.Name):
			sig = self.tree.symdict[node.value.id]
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
			self.dbg(t, VIOBG, "getAttr ",  "signal " + repr(node))
			if node.attr == 'next':
				sig = self.tree.symdict[node.value.id]
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
		pass

	def accessIndex(self, node):
		sm = SynthesisMapper(SM_WIRE)
		self.visit(node.value)
		sig = node.value.syn.q
		sm.q = sig.extract(node.slice.value.n, 1)
		node.syn = sm

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
					self.dbg(t, REDBG, "DRV_OBSOLETE",  "ineffective previous assignment to '%s'" % sigid)
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
			self.dbg(t, GREEN, "CASE[%d]" % i,  "")
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

		self.dbg(node, GREEN, "\n\n-- PMUXMAP --", "multiplexer map output:")
		for n, i in muxmap.items():
			print("   %s ===> %s" % (n, repr(i)))

		self.dbg(node, GREEN, "-- PMUXMAP END --", "\n\n")
			
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
				s = Signal(m.wires[cond.id])
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
				print("   %s ===> %s" % (n, repr(i)))

				target = m.wires[n]
				l = target.size()


				mux_b = i[0]
				name = self.genid(test, n)
				# self.dbg(test, BLUEBG, "ADD_SIGNAL",  "%s" % name)
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
				print("   %s ===> %s" % (n, repr(i)))
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
		for n, i in muxmap.items():
			print("   %s ===> %s" % (n, repr(i)))

		self.dbg(node, GREEN, "-- MUXMAP END --", "\n\n")

		sm.drivers = muxmap

		node.syn = sm

