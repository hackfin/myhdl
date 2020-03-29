import ast
from myhdl._block import _Block
from myhdl._getHierarchy import _getHierarchy

from types import GeneratorType
from myhdl._instance import _Instantiator

from myhdl._extractHierarchy import (_HierExtr, _isMem, _getMemInfo,
									 _UserVhdlCode, _userCodeMap)

from myhdl._Signal import _Signal, _WaiterList, _PosedgeWaiterList, _NegedgeWaiterList

from myhdl._compat import StringIO

from myhdl.conversion._misc import (_error, _kind, _context,
									_ConversionMixin, _Label, _genUniqueSuffix, _isConstant)

from myhdl.conversion._analyze import (_analyzeSigs, _analyzeGens, _analyzeTopFunc,
									   _Ram, _Rom, _enumTypeSet, _slice_constDict)

from myhdl import intbv, EnumType, concat

try:
	from myhdl.conversion.yshelper import *
except:
	from myhdl.conversion.yshelper_dummy import *
	

import inspect

# To write out testbench for post-map output:
from myhdl.conversion._toVerilog import _writeTestBench

_n  = lambda: "CALL \t" + inspect.stack()[1][3] + "()"

from myhdl.conversion.annotate import _AnnotateTypesVisitor

def _annotateTypes(genlist):
	for tree in genlist:
		v = _AnnotateTypesVisitor(tree)
		v.visit(tree)

def _flatten(*args):
	arglist = []
	for arg in args:
		if isinstance(arg, _Block):
			if arg.vhdl_code is not None:
				arglist.append(arg.vhdl_code)
				continue
			else:
				arg = arg.subs
		if id(arg) in _userCodeMap['vhdl']:
			arglist.append(_userCodeMap['vhdl'][id(arg)])
		elif isinstance(arg, (list, tuple, set)):
			for item in arg:
				arglist.extend(_flatten(item))
		else:
			arglist.append(arg)
	return arglist

def _checkArgs(arglist):
	for arg in arglist:
		if not isinstance(arg, (GeneratorType, _Instantiator, _UserVhdlCode)):
			raise ToVHDLError(_error.ArgType, arg)


ANNOTATE = "\033[7;30m"

class _ConvertVisitor(ast.NodeVisitor, _ConversionMixin, VisitorHelper):
	def __init__(self, context, tree):
		self.context = context
		self.tree = tree
		self.variables = { }
		self.depth = 0
		self.state = S_NEUTRAL
		self.cur_module = "undefined"

	def generic_visit(self, node):
		self.dbg(node, ANNOTATE, "VISIT", type(node).__name__)
		self.depth += 1
		ast.NodeVisitor.generic_visit(self, node)
		self.depth -= 1

	def visit_BinOp(self, node):
		m = self.context
		a, b = node.left, node.right
		self.visit(a)
		self.visit(b)

		la, lb = a.syn.q.size(), b.syn.q.size()

		l = la

		if a.syn.isConst() and b.syn.isConst():
			sm = SynthesisMapper(SM_WIRE)
			self.dbg(node, BLUEBG, "BINOP CONST EXPR", "%s" % (node.op))
			res = self.const_eval(node)
			sm.q = ConstSignal(res, res.bit_length())
			del a.syn, b.syn

		else:

			if la < lb and isinstance(node.left.obj, _Signal):
				a.syn.q.extend_u0(lb, a.syn.is_signed)
				l = lb
			elif la > lb and isinstance(node.right.obj, _Signal):
				b.syn.q.extend_u0(lb, b.syn.is_signed)

			# print("Add wire with name %s, size %d" % (name, l))
			sm = SynthesisMapper(SM_WIRE)
			sm.q = m.addSignal(None, l)
			name = NEW_ID(__name__, node, "binop")
			m.apply_binop(name, node.op, a.syn.q, b.syn.q, sm.q)

		node.syn = sm

#	def visit_BoolOp(self, node):
#		pass
#
	def visit_UnaryOp(self, node):
		m = self.context
		a = node.operand
		self.dbg(node, BLUEBG, "UNARY_OP", "%s" % (node.op))
		self.visit(a)
		l = a.syn.q.size()
		sm = SynthesisMapper(SM_WIRE)
		sm.q = m.addSignal(None, l)
		name = NEW_ID(__name__, node, "unop")
		m.apply_unop(name, node.op, a.syn.q, sm.q)
		node.syn = sm
		
	def visit_Attribute(self, node):
		if isinstance(node.ctx, ast.Store):
			self.setAttr(node)
		else:
			self.getAttr(node)

#	def visit_Assert(self, node):
#		print(_n())

	def visit_Store(self, node):
		if self.state == S_COLLECT:
			print("STORE", node.id)

	def visit_Assign(self, node):
		lhs = node.targets[0]
		rhs = node.value
		self.visit(lhs)
		# print("lhs", lhs.value)
		self.visit(rhs)

		t = SM_WIRE


		if not hasattr(rhs, "obj"):
			name = rhs.id
			q = self.variables[name]
			raise Synth_Nosupp("Can't handle this YET")
		elif isinstance(rhs, bool):
			src = ConstSignal(int(rhs), 1)
			t = SM_BOOL
		elif isinstance(rhs, int):
			src = ConstSignal(rhs, rhs.bit_length())
		else:
			src = rhs.syn.q

		if not hasattr(lhs, "obj"):
			name = lhs.id
			self.variables[name] = rhs.syn
			self.dbg(node, BLUEBG, "ASSIGN", "assign to variable %s" % (name))
			dst = None
		elif isinstance(lhs.obj, _Signal):
			dst = self.context.wires[lhs.obj._name]
			self.dbg(node, BLUEBG, "ASSIGN", "assign to type %s" % (type(lhs.obj)))

			# Size handling and sign extension:
			if dst.size() > src.size():
				self.dbg(node, REDBG, "EXTENSION", "signed: %s" % (repr(rhs.syn.is_signed)))
				src.extend_u0(dst.size(), rhs.syn.is_signed)
			elif dst.size() < src.size():
				self.raiseError(node, "OVERFLOW const value: %s[%d:], src[%d:]" %(lhs.obj._name, dst.size(), src.size()))

		else:
			raise Synth_Nosupp("Can't handle this YET")

		sm = SynthesisMapper(t)
		sm.q = src

		if self.state == S_MUX:
			node.driver = lhs.obj._name
		elif dst:
			m = self.context
			m.connect(dst, src)

		node.syn = sm

	
#	def visit_AugAssign(self, node):
#		print(_n())
#
#	def visit_Break(self, node):
#		print(_n())
#
	def visit_Call(self, node):
		fn = node.func
		f = self.getObj(fn)

		if f == intbv.signed:
			arg = fn.value
			self.visit(arg)
			arg.syn.is_signed = True
			node.syn = arg.syn # Pass on
		elif f is concat:
			self.dbg(node, GREEN, "CONCAT", "")
			q = self.context.addSignal(None, 0)
			for arg in reversed(node.args):
				self.visit(arg)
				q.append(arg.syn.q)
			sm = SynthesisMapper(SM_WIRE)
			sm.q = q
			node.syn = sm
		else:
			self.raiseError(node, "Can't synthesize function %s" % f.__name__)
			

	def visit_Compare(self, node):
		name = None
		# self.dbg(node, REDBG, "NOTICE", "call compare attr")
		# print("Add wire with name %s" % (name))
		self.generic_visit(node)
		a = node.left
		b = node.comparators[0]
		l = a.syn.q.size()
		if l > 1 or isinstance(b.value, ast.Name):
			sm = SynthesisMapper(SM_BOOL)
			q = self.context.addSignal(name, 1)
			op = node.ops[0]
			name = NEW_ID(__name__, node, "binop2")
			# print("apply_binop() name %s" % (name))
			self.context.apply_binop(name, op, a.syn.q, b.syn.q, q)
			sm.q = q
		else:
			node.defer = DEFER_MUX
			sm = SynthesisMapper(SM_BOOL)
			if hasattr(b, 'value'):
				if b.value in [True, 1]:
					sm.q = a
				elif b.value in [False, 0]:
					sm.q = self.context.addSignal(None, 1)
					name = NEW_ID(__name__, node, "not")
					sin = SigBit(a.syn.q)
					self.context.addNotGate(name, sin, SigBit(sm.q))
				else:
					self.raiseError(node, "Unsupported right hand value %s" % (type(b.value)))
			else:
				self.raiseError(node, "Unsupported right hand type %s" % (type(b)))
				
		node.syn = sm

	def visit_Num(self, node):
		sm = SynthesisMapper(SM_NUM)
		sm.q = Signal(Const(node.value))
		node.syn = sm
#
#	def visit_Str(self, node):
#		print(_n())
#
#	def visit_Continue(self, node, *args):
#		print(_n())
#
#	def visit_Expr(self, node):
#		print(_n())

	def visit_If(self, node):
		if self.state == S_TIE_DEFAULTS:
			for stmt in node.body:
				if isinstance(stmt, ast.If):
					self.visit(stmt)

			self.dbg(node, REDBG, "TIE_DEFAULT", "VISIT")

			for n, i in node.syn.drivers.items():
				other = i[1]
				if other:
					self.dbg(node, REDBG, "TIE_DEFAULT", "Tie to default signal %s" % n)
					defsig = self.context.wires[n]
					self.context.connect(other, defsig)
				else:
					self.dbg(node, REDBG, "TIE_DEFAULT", "Signal has default: %s" % n)
		else:
			prev = self.state
			self.state = S_MUX

			self.generic_visit(node)

			if hasattr(node, "isFullCase"):
				if node.isFullCase:
					self.mapToMux(node, True)
				else:
					# print("SYNC_MAP_MUX")
					self.mapToMux(node, True)
			else:
				# print("MAP_MUX_F")
				# self.mapToMux(node, True)
				self.dbg(node, REDBG, "WARN", "no fullcase attr in sync process")

			self.state = prev


	def visit_IfExp(self, node):
		self.generic_visit(node)

#	def visit_For(self, node):
#		print(_n())

	def manageEdges(self, ifnode, senslist):
		""" Helper method to convert MyHDL style template into VHDL style"""
		first = senslist[0]
		if isinstance(first, _WaiterList):
			bt = _WaiterList
		elif isinstance(first, _Signal):
			bt = _Signal
		elif isinstance(first, delay):
			bt = delay
		assert bt
		for e in senslist:
			if not isinstance(e, bt):
				self.raiseError(ifnode, "base type error in sensitivity list")
		if len(senslist) >= 2 and bt == _WaiterList:
			# ifnode = node.code.nodes[0]
			# print ifnode
			assert isinstance(ifnode, ast.If)
			asyncEdges = []
			for test, suite in ifnode.tests:
				e = self.getEdge(test)
				if e is None:
					self.raiseError(ifnode, "No proper edge value test")
				asyncEdges.append(e)
			if not ifnode.else_:
				self.raiseError(ifnode, "No separate else clause found")
			edges = []
			for s in senslist:
				for e in asyncEdges:
					if s is e:
						break
				else:
					edges.append(s)
			ifnode.edge = edges
			senslist = [s.sig for s in senslist]
		return senslist

#	def visit_FunctionDef(self, node):
#		self.cur_module = node.name
#		w = node.body[-1]
#		y = w.body[0]
#		if isinstance(y, ast.Expr):
#			y = y.value
#		assert isinstance(y, ast.Yield)
#		senslist = y.senslist
#		senslist = self.manageEdges(w.body[1], senslist)
#		singleEdge = (len(senslist) == 1) and isinstance(senslist[0], _WaiterList)
#		if singleEdge:
#			print("SINGLE CLK:", senslist[0].sig)
#		else:
#			for e in senslist[:-1]:
#				print(e)
#
#		for stmt in w.body[1:]:
#			self.visit(stmt)

#	def visit_ListComp(self, node):
#		print(_n())

	def visit_Module(self, node):
		for stmt in node.body:
			self.visit(stmt)

	def visit_NameConstant(self, node):
		print("ID", node.id)

	def visit_Name(self, node):
		m = self.context
		if node.id in self.tree.vardict:
			d = m.wires
			if node.id in self.variables:
				node.syn = self.variables[node.id]
			else:
				sm = SynthesisMapper(SM_VAR)
				self.variables[node.id] = None
				node.syn = sm
				self.dbg(node, REDBG, "Init Variable", node.id)
		elif node.id in m.wires:
			d = m.wires
			sm = SynthesisMapper(SM_WIRE)
			sm.q = d[node.id]
			node.syn = sm

		else:
			raise KeyError("'%s' not in wires" % node.id)

#
#	def visit_Pass(self, node):
#		print(_n())

#	def visit_Print(self, node):
#		print(_n())

#	def visit_Raise(self, node):
#		print(_n())

#	def visit_Return(self, node):
#		print(_n())

	def visit_Subscript(self, node):
		if isinstance(node.slice, ast.Slice):
			self.accessSlice(node)
		else:
			self.accessIndex(node)
	

#	def visit_While(self, node):
#		print(_n())

#	def visit_Yield(self, node):
#		print(_n())

	def visit_stmt(self, body):
		for stmt in body:
			self.dbg(stmt, GREEN, "STMT", stmt)
			self.visit(stmt)


class _ConvertAlwaysVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

class _ConvertInitialVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

class _ConvertSimpleAlwaysCombVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

	def visit_Attribute(self, node):
		if isinstance(node.ctx, ast.Store):
			self.SigAss = True
			if isinstance(node.value, ast.Name):
				sig = self.tree.symdict[node.value.id]
				self.SigAss = sig._name
			self.visit(node.value)
		else:
			self.getAttr(node)

	def visit_FunctionDef(self, node, *args):
		self.cur_module = node.name
		self.visit_stmt(node.body)

class _ConvertAlwaysDecoVisitor(_ConvertVisitor):
	"""Visitor for @always(sens_signal) type modules"""
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

	def visit_FunctionDef(self, node, *args):
		def handle_dff(m, stmt, clk, clkpol = True):
			for name, sig in stmt.syn.drivers.items():
				gsig = m.wires[name]
				l = gsig.size()
				sig_ff = m.addSignal(PID(name + "_ff"), l)
				clk = m.wires[clk._name]
				m.addDff(self.genid(node, name), clk, sig[0], sig_ff, clkpol)
				m.connect(gsig, sig_ff)
	
		assert self.tree.senslist
		m = self.context
		self.cur_module = node.name
		senslist = self.tree.senslist
		senslist = self.manageEdges(node.body[-1], senslist)
		singleEdge = (len(senslist) == 1) and isinstance(senslist[0], _WaiterList)
		if singleEdge:
			clknode = senslist[0]
			clk = clknode.sig
			if isinstance(clknode, _PosedgeWaiterList):
				clkpol = True
			elif isinstance(clknode, _NegedgeWaiterList):
				clkpol = False
			else:
				self.raiseError(clknode, "Invalid clk type")

			self.dbg(node, VIOBG, "PROCESS", "%s() Single edge:" % self.tree.name + repr(clk))
			# print(clk)
			self.cur_clk = clk._name
		else:
			raise Synth_Nosupp("Can't handle this YET")

		self.handle_toplevel_process(node, handle_dff, clk, clkpol)
		self.tie_defaults(node)


class _ConvertAlwaysSeqVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)


	def visit_FunctionDef(self, node, *args):
		def handle_dff(m, stmt, reset, clk, clkpol = True):
			clk = m.wires[clk._name]
			for name, sig in stmt.syn.drivers.items():
				gsig = m.wires[name]
				l = gsig.size()
				sig_ff = m.addSignal(PID(name + "_ff"), l)
				y = m.addSignal(PID(name + "_rst"), l)
				reset_val = Signal(Const(m.defaults[name], l)) # Value when in reset
				# Create synchronous reset circuit
				rst = m.wires[reset._name]
				if reset.active:
					m.addMux(self.genid(node, name + "_rst"), sig[0], reset_val, rst, y)
				else:
					m.addMux(self.genid(node, name + "_!rst"), reset_val, sig[0], rst, y)

				m.addDff(self.genid(node, name), clk, y, sig_ff, clkpol)

				m.connect(gsig, sig_ff)

		def handle_adff(m, stmt, reset, clk, clkpol = True):
			clk = m.wires[clk._name]
			for name, sig in stmt.syn.drivers.items():
				gsig = m.wires[name]
				l = gsig.size()
				sig_ff = m.addSignal(PID(name + "_ff"), l)
				reset_val = Const(m.defaults[name], l) # Value when in reset
				arst = m.wires[reset._name]
				m.addAdff(self.genid(node, name), clk, arst, sig[0], sig_ff, reset_val.get(), \
					clkpol, reset.active)

				m.connect(gsig, sig_ff)

		assert self.tree.senslist
		self.cur_module = node.name
		senslist = self.tree.senslist
		edge = senslist[0]
		reset = self.tree.reset
		isasync = reset is not None and reset.isasync
		m = self.context

		clknode = senslist[0]
		if isinstance(clknode, _PosedgeWaiterList):
			clkpol = True
		elif isinstance(clknode, _NegedgeWaiterList):
			clkpol = False
		else:
			self.raiseError(clknode, "Invalid clk type")

		clk = clknode.sig
		self.cur_clk = clk._name

		if isasync:
			self.handle_toplevel_reset_process(node, handle_adff, reset, clk, clkpol)
		else:
			self.handle_toplevel_reset_process(node, handle_dff, reset, clk, clkpol)

		self.tie_defaults(node)

class _ConvertAlwaysCombVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

	def visit_FunctionDef(self, node):
		self.cur_module = node.name
		# a local function works nicely too
		print("Sensitivity list for %s:" % node.name)
		for e in self.tree.senslist:
			print('\t', e)

		m = self.context

		for stmt in node.body:
			self.dbg(stmt, GREEN, "STMT", stmt)
			self.visit(stmt)
			if isinstance(stmt, ast.If):
				for name, sig in stmt.syn.drivers.items():
					print("wire %s:" % name)
					gsig = m.wires[name]
					m.connect(gsig, sig[0])
					self.dbg(stmt, REDBG, "DRIVERS", name)

	def visit_If(self, node):
		if self.state == S_TIE_DEFAULTS:
			self.dbg(node, REDBG, "TIE_DEFAULT", "SKIP, not applicable")
		else:
			prev = self.state
			self.state = S_MUX

			self.generic_visit(node)

			if hasattr(node, "isFullCase"):
				if node.isFullCase:
					self.mapToPmux(node)
				else:
					self.mapToMux(node)
			else:
				self.dbg(node, REDBG, "WARN", "no fullcase attr in async process")

			self.state = prev


def convert_rtl(hierarchy, func, tbname, design, write_tb, trace):
	arglist = _flatten(hierarchy.top)
	_checkArgs(arglist)
	genlist = _analyzeGens(arglist, hierarchy.absnames)
	siglist, memlist = _analyzeSigs(hierarchy.hierarchy, hdl='Verilog')


	_annotateTypes(genlist)

	func._inferInterface()

	m = design.addModule(func.name)

	m.collectWires(siglist, func.argdict)

	for tree in genlist:
		if tree.kind == _kind.ALWAYS:
			Visitor = _ConvertAlwaysVisitor
		elif tree.kind == _kind.INITIAL:
			Visitor = _ConvertInitialVisitor
		elif tree.kind == _kind.SIMPLE_ALWAYS_COMB:
			Visitor = _ConvertSimpleAlwaysCombVisitor
		elif tree.kind == _kind.ALWAYS_DECO:
			Visitor = _ConvertAlwaysDecoVisitor
		elif tree.kind == _kind.ALWAYS_SEQ:
			Visitor = _ConvertAlwaysSeqVisitor
		else:  # ALWAYS_COMB
			Visitor = _ConvertAlwaysCombVisitor

		v = Visitor(m, tree)
		v.visit(tree)

	if write_tb:
		tbfile = open("tb_%s_mapped.v" % tbname, 'w')
		func.name = tbname # Hack to overwrite DUT name
		_writeTestBench(tbfile, func, trace, "1ps/1ps")
		tbfile.close()

	return design

class YosysModuleConvertor(object):
	def __init__(self):
		self.name = None
		self.design = None
		self.trace = False

	def __call__(self, func, *args, **kwargs):

		if self.name is None:
			name = func.func.__name__
		else:
			name = str(self.name)

		try:
			h = _getHierarchy(name, func)
		finally:
			_converting = 0

		_genUniqueSuffix.reset()
		_enumTypeSet.clear()
		_slice_constDict.clear()
		# _enumPortTypeSet = set()

		convert_rtl(h, func, name, self.design, True, self.trace)


toYosysModule = YosysModuleConvertor()
