# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#

import ast
import inspect
import myhdl
import os
import io

from myhdl import ConversionError

from myhdl._util import _makeAST
from myhdl.conversion.analyze_ng import _AnalyzeTopFuncVisitor, \
	_slice_constDict
from myhdl._Signal import _Signal
from myhdl._block import _Block
from myhdl._blackbox import _BlackBox

from myhdl._ShadowSignal import _ShadowSignal, _SliceSignal, _TristateDriver
from myhdl._bulksignal import _BulkSignalBase

from myhdl.conversion._misc import (_get_argnames, _error)

from pyosys import libyosys as ys

from .ysmodule_ng import *
from .ysdebug import *

from .synmapper import *


DEFER_MUX, DEFER_RESERVED = range(2)

# Visitor states:
S_NEUTRAL, S_COLLECT, S_MUX , S_TIE_DEFAULTS = range(4)

class DebugOutput:
	debug = ENABLE_DEBUG
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


def ConstDriver(val, bit_len = None):
	if val < 0:
		signed = True
	else:
		signed = False

	sm = SynthesisMapper(SM_NUM, signed)
	sm.q = ConstSignal(val, bit_len)

	return sm
		

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
		self.modules = {}

	def get(self):
		return self.design

	def addModule(self, name, implementation, public = False):
		print(GREEN + "Adding module with name:"  + OFF, name)
		if public:
			n = PID(name)
		else:
			n = ID(name)
		m = self.design.addModule(n)
		m = Module(m, implementation)
		self.modules[name] = m
		return m

	def set_top_module(self, top):
		key = create_key(top.obj)
		ys.run_pass("hierarchy -top \\%s" % key, self.design)

	def top_module(self):
		return Module(self.design.top_module(), None)

	def run(self, cmd, silent = True):
		"Careful. This function can exit without warning"
		if not silent:
			print("Note: Capturing currently broken")
#		capture = io.StringIO()
#		ys.log_to_stream(capture)
		if isinstance(cmd, list):
			for c in cmd:
				ys.run_pass(c, self.design)
		else:
			ys.run_pass(cmd, self.design)
#		ys.log_pop()
#
#		if not silent:
#			print(capture.getvalue())
#		else:
#			return capture.getvalue()
		

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
		ys.run_pass("ls; check")
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
		if isinstance(obj, _BulkSignalBase):
			obj.expand(v.argdict, v.argnames)
		elif hasattr(obj, '__dict__'):
			print("Legacy class %s" % name)
			# must be an interface object (probably ...?)
			expandinterface(v, name, obj)

	blk.argnames = v.argnames
	blk.argdict = v.argdict

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

# from itertools import chain

def _makeName(n, prefixes, namedict):
	# trim empty prefixes
	prefixes = [p for p in prefixes if p]
	if len(prefixes) > 0:
		name = '_'.join(prefixes[0:]) + '_' + n
	else:
		name = n
	if '[' in name or ']' in name:
		name = "\\" + name + ' '

	if name in namedict:
		raise ValueError("Identifier `%s` already present" % name)
	else:
		namedict[name] = n

	return name


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

  Assume case 2.b:
 - Signal declared in parent: 'port_a', but not driven/read in parent
 - port_a driven by child module B, read by child module A
 - Signal port_a passed as (implicit output) parameter `b_out` to B
 - Signal port_a passed as (implicit input) parameter `a_in` to A

 When seen first (driven) in B, it's registered as local name `b_out`.
 When seen first in A, it takes the name `a_in`.

To preserve hierarchy, a .wiremap is maintained. See analyze_signals().

Nested hierarchies have to be fixed by a final pass, because the
module I/O properties might not be fully determined at the time the interface
is inferred.

"""

	__slots__ = ['level', 'obj', 'subs', 'sigdict', 'symdict', 'memdict', 'wiremap', 'name', 'genlist', 'instances', 'cell', 'module', 'msg']

	def __init__(self, level, obj, subs, debug = False):
		self.level = level
		self.obj = obj
		self.subs = subs
		self.sigdict = obj.sigdict
		self.symdict = obj.symdict
		self.memdict = obj.memdict
		self.wiremap = {}
		self.name = None
		self.cell = False
		self.module = None

		def dummy_msg(*args, **kwargs):
			pass

		if debug:
			self.msg = print
		else:
			self.msg = dummy_msg

	def __lt__(self, other):
		return self.level > other.level

	def __repr__(self):
		return "< Instance %s >" % self.name

	def dump(self):
		print("===== DUMP Mem/SIGNALS, INSTANCE  %s =====" % self.name)
		for m in self.memdict.items():
			print(GREEN + "Memory/Signal list: %s" % m[0] + OFF)
		for n, i in self.sigdict.items():
			if isinstance(i, _Signal):
				print("SIGNAL %s (%d)" % (n, len(i)))
			elif hasattr(i, '__dict__'):
				print("CLASS %s (type %s)" % (n, type(i).__name__))
			else:
				print("OTHER %s (type %s)" % (n, type(i).__name__))

	def analyze_signals(self):
		"""Analyze signals of an instance. We may be walking the hierarchy in any direction,
thus wired signals are getting their ._name on the fly. Note: Bulk signals are not analyzed,
as they appear not in the sigdict. Note that I/O characteristics are not yet determined."""
		msg = self.msg

		msg("===== Analyze signals for %s =====" % self)
		# sigs = []
		# sigarrays = []

		# namedict = dict(chain(sigdict.items(), memdict.items()))
		namedict = {}

		for n, s in self.sigdict.items():

			if s._name is not None:
				self.wiremap[n] = (s, True)
				if not s._id:
					s._id = _makeName(n, [self.name], namedict)
					msg(GREEN + "SHADOW/CLASS WIRE %s <--- <%s> := %s" % (n, s._name, s._id) + OFF)
				else:
					msg(GREEN + "REUSE WIRE %s <--- <%s> := %s" % (n, s._name, s._id) + OFF)
				continue
			else:
				self.wiremap[n] = (s, False)
				sname = _makeName(n, [], namedict)
				s._name = sname
				if not s._id:
					s._id = _makeName(n, [self.name], namedict)
				msg(BLUEBG + "NEW WIRE %s := %s" % (n, s._id) + OFF)

			if isinstance(s, _SliceSignal):
				continue

			if not s._nrbits:
				print(type(s))
				raise ConversionError(_error.UndefinedBitWidth, s._name)
			# slice signals
			for sl in s._slicesigs:
				sl._setName("Verilog")
			# sigs.append(s)
		
		# handle array/memory:
		for n, m in self.memdict.items():
			if m.name is None:
				m.name = _makeName(n, [], namedict)

			# sigarrays.append(m)

	def infer_interface(self):
		blk = self.obj
		infer_interface(blk)

	def get_io(self):
		inputs = set()
		outputs = set()
		for t in self.genlist:
			inputs.update(t.inputs)
			outputs.update(t.outputs)

		return inputs, outputs

	def create_key(self):
		"Create a unique key for a specific instance"
		blk = self.obj
		a = blk.func.__name__
		for i in blk.args:
			a = append_sig(i, a)

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
			inst = Instance(level, modinst, subs, debug = ENABLE_DEBUG)
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
		elif isinstance(node, ast.Name):
			return node.value
		elif isinstance(node, ast.Num):
			return node.n
		elif hasattr(node, "value"):
			return node.value
		else:
			self.raiseError(node, "Unsupported operator '%s" % type(node).__name__)

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

	def findWireById(self, name):
		return self.context.findWireByName(name, True)

	def handle_memport(self, port, name, which):
		m = self.context
		c = m.addCell(name, ID(which))
		port_addr = m.getCorrespondingWire(port.addrsig)
		data_w = port.q.size() # Number of data bits
		c.setPort(PID("DATA"), port.q)
		c.setPort(PID("ADDR"), port_addr)

		en = m.addSignal(None, data_w)
		c.setPort(PID("EN"), en)
			
		if self.clk != None:
			clk = m.getCorrespondingWire(self.clk)
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
						self.dbg(stmt, REDBG, "TIE DEFAULT", "%s" % n)
						self.assign_default(n, default, default_assignments, True)
					if other:
						self.dbg(stmt, REDBG, "TIE OTHER", "%s" % n)
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
							self.dbg(stmt, BLUEBG, "HAVE DEFAULT", "sig %s" % n)
							ret = self.assign_default(n, default, default_assignments, True)
							if clk == None and ret == 2:
								self.dbg(stmt, REDBG, "LATCH_WARNING", \
									"Incomplete 'default' assignments, latch created for %s" % n)
						if other:
							self.dbg(stmt, BLUEBG, "HAVE OTHER", "sig %s" % n)
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
				lineno = self.getLineNo(stmt)
				drv[name] = [ ("l:%d$default_%d" % (lineno, i), None) for i in range(n) ]
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
					self.dbg(stmt, REDBG, "IMPLICIT_WARNING", \
						"(other) missing assignments, assuming defaults for %s" % name)
					ret0 = self.assign_default(name, other, defaults)
					if not ret0:
						self.dbg(stmt, REDBG, "APPEND OPEN OTHER", "%s" % name)

				if default:
					self.dbg(stmt, REDBG, "IMPLICIT_WARNING", \
						"(default) missing assignments, assuming defaults %s" % name)
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
			self.dbg(node, GREEN, "MUX WALK DRV >>>", dr_id)
			w = m.findWireByName(dr_id)
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
						lineno = self.getLineNo(node)
						name = self.genid(node, "l:%d$%s_default" % (lineno, dr_id))
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
		lhs = stmt.targets[0]
		rhs = stmt.value
		result = stmt.syn.q
		m = self.context
		sig = lhs.obj 

		outsig = m.getCorrespondingWire(sig)

		name = lhs.value.id
		self.dbg(stmt, GREEN, "PORT ASSIGN", \
			"PORT local: '%s', sig: %s" % (name, outsig.as_wire().name))
		m.connect(outsig, result)

############################################################################
# Factory auxiliaries:
#

class yosys:
	def __init__(self):
		self.id = "YOSYS_SYNTHESIS"


		
def convert_wires(m, c, a, n, force = False):
	if isinstance(a, _Signal):
		sig = m.findWire(a)
		if not sig:
			print("==== Wire dump for %s ====" % m.name)
			for w in m.wires:
				print(w)
			raise KeyError("Wire %s not found in signal list" % a._name)
		if a.driven or a.read or force:
			c.setPort(n, sig)
		else:
			print("FLOATING wire", a._name)

	elif isinstance(a, intbv):
		l = len(a)
		# print("CONST (vector len %d) wire" % l)
		port = m.addWire(None, l)
		s = Signal(port)
		sig = ConstSignal(a, l)
		c.setPort(n, s)
		if (s.size() < sig.size()) or sig.size() == 0:
			raise AssertionError("Bad signal size")
		m.connect(s, sig)
	elif isinstance(a, int) or isinstance(a, bool):
		print("WARNING: Parameter '%s' handled as constant signal" % n)
	elif a == None:
		pass
	elif inspect.isclass(type(a)):
		if isinstance(a, _BulkSignalBase):
			a.convert_wires(m, c)
		else:
			# Legacy support:
			print("Resolve legacy class (bus wire) %s" % (n))
			if hasattr(a, '__dict__'):
				for id, s in a.__dict__.items():
					convert_wires(m, c, s, n + "_" + id)
			elif hasattr(a, '__slots__'):
				for id in a.__slots__:
					s = getattr(a, id)
					convert_wires(m, c, s, n + "_" + id)
			elif isinstance(a, list):
				pass
			else:
				raise TypeError("Unsupported class type for %s: %s" % (n, type(a).__name__))
	else:
		raise TypeError("Unsupported wire type for %s: %s" % (n, type(a).__name__))


