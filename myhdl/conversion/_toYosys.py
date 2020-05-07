import ast
from myhdl._block import _Block
import sys
# from myhdl._getHierarchy import _getHierarchy

from types import GeneratorType
from myhdl._instance import _Instantiator

from myhdl._always_comb import _AlwaysComb
from myhdl._always_seq import _AlwaysSeq
from myhdl._always import _Always

from myhdl._Signal import _Signal, _WaiterList, _PosedgeWaiterList, _NegedgeWaiterList

from myhdl._compat import StringIO

from myhdl.conversion._misc import (_error, _kind, _context,
									_ConversionMixin, _Label, _genUniqueSuffix, _isConstant)

from myhdl.conversion.analyze_ng import (_analyzeGens,_makeName,
									   _Ram, _Rom, _enumTypeSet, _slice_constDict)


from myhdl import intbv, concat, delay

from myhdl._blackbox import _BlackBox

# Allow support of not nice legacy:
__legacy__ = True

try:
	from myhdl.conversion.yshelper import *
except:
	from myhdl.conversion.yshelper_dummy import *
	

import inspect

# To write out testbench for post-map output:
from myhdl.conversion._toVerilog import _writeTestBench

_n	= lambda: "CALL \t" + inspect.stack()[1][3] + "()"

from myhdl.conversion.annotate import _AnnotateTypesVisitor

def _annotateTypes(genlist):
	for tree in genlist:
		v = _AnnotateTypesVisitor(tree)
		v.visit(tree)

ANNOTATE = "\033[7;30m"

class _ConvertVisitor(ast.NodeVisitor, _ConversionMixin, VisitorHelper):
	def __init__(self, context, tree):
		self.context = context
		self.tree = tree
		self.variables = { }
		self.loopvars = { }
		self.depth = 0
		self.state = S_NEUTRAL
		self.cur_enable = None
		self.cur_module = "undefined"

	def generic_visit(self, node):
		self.depth += 1
		ast.NodeVisitor.generic_visit(self, node)
		self.depth -= 1

	def visit_BinOp(self, node):
		"""This supports synthesizeable types as well as local variables
		on the fly. This is a bit of a hack and could be done nicer by
		a procedural analysis."""
		m = self.context
		a, b = node.left, node.right
		self.visit(a)
		self.visit(b)

		# Did we synthesize?
		if hasattr(a, 'syn') and hasattr(b, 'syn'):
			if a.syn.isConst() and b.syn.isConst():
				sm = SynthesisMapper(SM_WIRE)
				self.dbg(node, BLUEBG, "BINOP CONST EXPR", "%s" % (node.op))
				res = self.const_eval(node)
				sm.q = ConstSignal(res, res.bit_length())
				del a.syn, b.syn
			else:
				sm = m.apply_binop(node, a.syn, b.syn)
			node.syn = sm
		else:
			# Assume we're constant
			try:
				res = self.const_eval(node)
			except AttributeError:
				self.raiseError(node, "Unhandled type %s" % type(node))

			node.value = res # Hack: set .value for get_index()

	def visit_BoolOp(self, node):
		m = self.context
		func = m._boolopmap[type(node.op)]
		cc = m.addSignal(None, 0)
		for i in node.values:
			self.visit(i)
			cc.append(i.syn.q)

		sm = SynthesisMapper(SM_WIRE)
		sm.q = m.addSignal(None, 1)
		name = NEW_ID(__name__, node, "bool")

		func(m.module, name, cc, sm.q)
		node.syn = sm

	def visit_UnaryOp(self, node):
		m = self.context
		a = node.operand

		# If we have a constant, resolve here
		if isinstance(node.operand, ast.Num):
			val = ast.literal_eval(node)
			sm = ConstDriver(int(val))
			self.dbg(node, REDBG, "UNOP type", "%s" % (node.operand))
		else:
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

	def visit_Assert(self, node):
		lineno = self.getLineNo(node)
		lineno += self.tree.lineoffset
		c = self.context.addCell("assert:%s:%d" % (self.tree.sourcefile, lineno), "user_assert", True)
		self.visit(node.test)
		c.setPort("COND", node.test.syn.q)

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
		sm = None

		# Right hand side (src)
		if not hasattr(rhs, "obj"):
			name = rhs.id
			q = self.variables[name]
			raise Synth_Nosupp("Can't handle this YET")
		elif isinstance(rhs, bool):
			src = ConstSignal(int(rhs), 1)
			t = SM_BOOL
		elif isinstance(rhs, int):
			src = ConstSignal(rhs, rhs.bit_length())
		elif isinstance(rhs, ast.Subscript):
			if isinstance(node.value.value.obj, _Rom) and isinstance(node.value.slice, ast.Index):
				self.dbg(node, BLUEBG, "DETECT", "found ROM %s" % (node.value.value.obj))
				rom = node.value.value.obj
				sm = self.context.infer_rom(rom, lhs.obj, rhs.syn.q)
			else:
				src = rhs.syn.q
		else:
			src = rhs.syn.q

		node.id = None # Pass on ID for driver mux table

		# Left hand side (dst)
		if not hasattr(lhs, "obj"):
			name = lhs.id
			node.id = name
			vs = self.variables[name]
			if vs == None:
				# First time assignment
				self.dbg(node, BLUEBG, "VAR_INIT", "Init variable %s" % (name))
				# Create a variable mapper. This is different from a signal
				# as in values become effective immediately, despite the outer function's kind.
				sm = SynthesisMapper(SM_VAR)
				sm.q = rhs.syn.q
				sm.is_signed = rhs.syn.is_signed
				self.variables[name] = sm
			else:
				# TODO: Type check
				self.dbg(node, BLUEBG, "REASSIGN", "reassign to variable %s" % (name))
				# Set reference to right hand side:
				sm = rhs.syn
		elif isinstance(lhs.obj, _Signal):
			drvname = lhs.obj._name # Default driver name
			node.id = drvname
			if hasattr(lhs, "syn"):
				# We already have an assigned port
				self.dbg(node, BLUEBG, "ASSIGN", "assign '%s' to preassigned Port %s size %d" % (drvname, lhs.id, lhs.syn.q.size()))
				dst = lhs.syn.q
				# Special case: detect memory cell read/write:
				if lhs.syn.el_type == SM_MEMPORT:
					self.dbg(node, GREEN, "MEMPORT", "write port detected %s" % (type(lhs)))
					port = lhs.syn
					sm = port
					sm.q = rhs.syn.q # Copy output from RHS as input to memport
					name = NEW_ID(__name__, node, "memwr")
					sm.cell, enable = self.handle_memport(port, name, "memwr")
					sm.sources = { 'enable' : enable } # Store in 'open sources' dict
				elif hasattr(rhs, 'syn'):
					if rhs.syn.el_type == SM_MEMPORT:
						self.dbg(node, GREEN, "MEMPORT", "read port detected %s" % (type(rhs)))
						name = NEW_ID(__name__, node, "memrd")
						port = rhs.syn
						sm = port
						sm.cell, enable = self.handle_memport(port, name, "memrd")
						sm.sources = { 'enable' : enable }
					else:
						dst = lhs.syn.q
				else:
					self.dbg(node, BLUEBG, "ALREADY_HANDLED", "RHS type %s" % (type(rhs)))
				dst = lhs.syn.q
					
			else:
				# self.dbg(node, BLUEBG, "ASSIGN", "assign '%s' to Signal type %s" % (drvname, type(lhs.obj)))
				dst = self.findWire(lhs)
		elif isinstance(lhs.obj, intbv):
			# POTENTIALLY_SEQUENTIAL
			if hasattr(lhs, 'syn'):
				if isinstance(lhs, ast.Subscript):
					name = lhs.value.id
					self.variables[name] = rhs.syn
					sm = lhs.syn
				else:
					self.raiseError(node, "Unhandled type %s" % type(lhs))
			else:
				self.raiseError(node, "No new assignment with sliced var")
		elif isinstance(lhs.obj, bool):
			if isinstance(lhs, ast.Subscript):
				name = lhs.value.id
				i = self.get_index(lhs.slice.value)
				sig_dst = self.variables[name].q
				self.dbg(node, BLUEBG, "REPLACE", " %s[%d] by %s" % (name, i, "new"))
				sig_dst.replace(i, rhs.syn.q)
				dst = sig_dst
		else:
			self.dbg(node, REDBG, "UNHANDLED", "type %s" % (type(lhs.obj)))
			raise Synth_Nosupp("Can't handle this YET")

		# Handle synthesis mapping / resizes:

		if not sm:
			if dst.size() > src.size():
				self.dbg(node, BLUEBG, "EXTENSION", "signed: %s" % (repr(rhs.syn.is_signed)))
				tmp = ys.SigSpec(src) # Create a copy, don't extend original:
				tmp.extend_u0(dst.size(), rhs.syn.is_signed)
				src = tmp
			elif dst.size() < src.size():
				if rhs.syn.trunc:
					self.dbg(node, REDBG, "TRUNC", "Implicit carry truncate: %s[%d:], src[%d:]" %(lhs.obj._name, dst.size(), src.size()))
					src = src.extract(0, dst.size())
				else:
					# self.dbg(node, REDBG, "OVERFLOW", "%s[%d:], src[%d:]" %(lhs.obj._name, dst.size(), src.size()))
					self.raiseError(node, "OVERFLOW value: %s[%d:] <= x[%d:]" %(lhs.obj._name, dst.size(), src.size()))

			sm = SynthesisMapper(t)
			sm.q = src
			sm.is_signed = rhs.syn.is_signed

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
			src = arg.syn.q
			# src.extend_u0(src.size(), True)
			self.dbg(node, BLUEBG, "\tTYPE", "%s" % (type(arg)))
			arg.syn.is_signed = True
			node.syn = arg.syn # Pass on
		elif f is intbv:
			if isinstance(node.args[0], ast.Num):
				self.dbg(node, GREEN, "ASSIGN NUM", f.__name__)
				sm = SynthesisMapper(SM_WIRE)
				args = (node.args[0].value,)
				kwargs = {}
				for kw in node.keywords:
					kwargs[kw.arg] = ast.literal_eval(kw.value)
				intbv_inst = f(*args, **kwargs)
				sm.q = ConstSignal(intbv_inst)
				node.syn = sm
			else:
				val = node.args[0]
				self.visit(val)
				node.syn = val.syn
		elif f is len:
			node.value = len(node.args[0].obj)
		elif f is int:
			val = node.args[0]
			self.visit(val)
			node.syn = val.syn
		elif f is concat:
			self.dbg(node, GREEN, "CONCAT", "")
			q = self.context.addSignal(None, 0)
			for arg in reversed(node.args):
				self.visit(arg)
				q.append(arg.syn.q)
			sm = SynthesisMapper(SM_WIRE)
			sm.q = q
			node.syn = sm
		elif f in [delay, print, range]:
			self.dbg(node, REDBG, "IGNORED FUNCTION", f)
		elif f is myhdl.StopSimulation:
			self.dbg(node, REDBG, "RAISE FUNCTION", f)
		else:
			args = []
			for i in node.args:
				self.visit(i)
				if not hasattr(i, 'value'):
					self.raiseError(node, "Unsupported (signal?) argument type for %s()" % f.__name__)
					# self.dbg(node, REDBG, "SYNTH_FUNCTION", "synthesized result to func %s" % f.__name__)
				else:
					args.append(i.value) # Static value
			# except AttributeError:
			# 	self.raiseError(node, "Unsupported argument type %s" % node.args)

			self.dbg(node, REDBG, "FUNCTION ", "fn: %s args: %s" % (f.__name__, repr(args)))

			result = f(*args)
			if isinstance(result, intbv):
				self.dbg(node, VIOBG, "FUNCTION intbv", "size: %d" % len(result))
				l = len(result)
			elif isinstance(result, int):
				l = result.bit_length()
			else:
				self.raiseError(node, "Unsupported return type from %s" % f.__name__)

			sm = SynthesisMapper(SM_WIRE)
			sm.q = ConstSignal(result, l)
			node.syn = sm
			

	def visit_Compare(self, node):
		name = None
		# print("Add wire with name %s" % (name))
		self.generic_visit(node)
		a = node.left
		b = node.comparators[0]
		l = a.syn.q.size()
		if hasattr(b, 'value'):
			if l > 1 or isinstance(b.value, ast.Name):
				# print("apply_binop() name %s" % (name))
				sm = self.context.apply_compare(node, a.syn, b.syn)
			else:
				node.defer = DEFER_MUX
				sm = SynthesisMapper(SM_BOOL)
				if b.value in [True, 1]:
					sm.q = a.syn.q
				elif b.value in [False, 0]:
					sm.q = self.context.addSignal(None, 1)
					name = NEW_ID(__name__, node, "not")
					sin = SigBit(a.syn.q)
					self.context.addNotGate(name, sin, SigBit(sm.q))
				else:
					self.raiseError(node, "Incorrect assignment to '%s' of value %s" % (a.id, type(b.value)))
		elif hasattr(b, 'syn'):
			sm = self.context.apply_compare(node, a.syn, b.syn)
		else:
			self.raiseError(node, "Unsupported right hand type %s" % (type(b)))
				
		node.syn = sm

	def visit_Num(self, node):
		try:
			node.syn = ConstDriver(node.value)
		except OverflowError:
			self.raiseError(node, "Overflow error for value %d" % (node.value))

#
#	def visit_Str(self, node):
#		print(_n())
#
#	def visit_Continue(self, node, *args):
#		print(_n())
#
#	def visit_Expr(self, node):
#		print(_n())


# #	def visit_If(self, node):
#		if node.ignore:
#			return
#
#
#		node.syn = sm

	def from_condition(self, cond):
		q = cond.syn.q
		"Return a yosys signal from a condition synthesis mapper element"
		if isinstance(q, ast.Name):
			s = self.context.findWireByName(q.id)
		elif isinstance(q, ys.SigSpec):
			s = q
		elif isinstance(q, Wire):
			s = Signal(q)
		else:
			# print(type(q))
			raise Synth_Nosupp("Unsupported MapMux selector type ")

		return s

	def visit_If(self, node):
		if node.ignore:
			return

		self.generic_visit(node)

		if hasattr(node, "isFullCase"):
			if node.isFullCase:
				self.mapToPmux(node)
			else:
				self.mapToMux(node)

		else:
			self.dbg(node, VIOBG, "NOTICE", "no fullcase attr in sync process")

	def visit_IfExp(self, node):
		self.generic_visit(node)

	############################################################
	# These are procedural nodes that need special attention.
	# Normally, we'd synthesize event driven structures only.
	# But for verification, we might have to mimic some sequential
	# logic as well

	def visit_While(self, node):
		print(_n())

	def visit_Yield(self, node):
		print(_n())


	def visit_For(self, node):
		"""A for loop just instances an up/down counter and tracks the
		yield statements to try to infer something"""
		# print(_n())
		var = node.target.id
		cf = node.iter
		f = self.getObj(cf.func)
		args = cf.args
		assert len(args) <= 3
		self.require(node, len(args) < 3, "explicit step not supported")
		self.require(node, len(args) > 0, "at least one argument requested")

		if f is range:
			if len(args) == 1:
				b = args[0]
				a = 0
			else:
				a, b = args
			# print(args)
			if not isinstance(a, int):
				a = a.value
			if not isinstance(b, int):
				b = b.value

			self.dbg(node, BLUEBG, "UP ", " (%s) %d .. %d" % (var, a, b))
	
			for i in range(a, b):
				self.loopvars[var] = i
				self.visit_stmt(node.body)

		else:
			self.raiseError(node, "Unsupported down range")


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
		v = node.value
		if isinstance(v, int) or isinstance(v, bool):
			sm = ConstDriver(v)
		else:
			self.raiseError(node, "Unsupported constant")
		node.syn = sm

	def visit_Name(self, node):
		m = self.context
		# Try to find a wire first:
		is_signed = False

		if hasattr(node, 'obj') and isinstance(node.obj, _Signal):
			min = node.obj.min
			if min:
				is_signed = min < 0
		
		w = m.findWireByName(node.id)
		if w:
			if isinstance(w, (tuple, list)):
				sm = SynthesisMapper(SM_ARRAY, False)
			else:
				sm = SynthesisMapper(SM_WIRE, is_signed)
			sm.q = w
			node.syn = sm
		elif node.id in self.tree.vardict:
			if node.id in self.variables:
				node.syn = self.variables[node.id]
			elif node.id in self.loopvars:
				val = self.loopvars[node.id]
				node.value = val # Stick cur value into .value
			else:
				self.variables[node.id] = None
		else:
			if hasattr(node, "value") and isinstance(node.value, int):
				self.dbg(node, VIOBG, "possibly accessing module wide variable", node.id)
				sm = ConstDriver(node.value)
			elif node.id in m.memories:
				mdesc = m.memories[node.id]
				sm = SynthesisMapper(SM_MEMPORT)
				name = NEW_ID(__name__, node, "mem")
				sm.q = m.addSignal(name, len(mdesc.elObj))
			elif node.id in self.tree.symdict:
				obj = self.tree.symdict[node.id]
				self.dbg(node, VIOBG, "OTHER SYMBOL (DEFINE)", "id: %s, type: %s" % (node.id, repr(obj)))
				return
			else:
				self.raiseError(node, "'%s' not in dictionary" % node.id)

			node.syn = sm

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
		obj = node.value.obj

		self.generic_visit(node.slice)

		if isinstance(node.slice, ast.Slice):
			# Special case of intbv slicing upon assignment:
			# TODO: Move into accessSlice()
			if isinstance(obj, intbv):
				if len(obj) == 0:
					if node.slice.upper:
						downto = node.slice.upper.n
					else:
						downto = 0

					n = node.slice.lower.obj - downto
					node.syn = ConstDriver(obj, n)
				else:
					self.accessSlice(node)
			else:
				try:
					self.accessSlice(node)
				except AttributeError:
					self.raiseError(node, "Bad index type, %s" % sys.exc_info()[1])
		elif isinstance(obj, _Rom):
			self.visit(node.slice)
			node.syn = node.slice.value.syn
		elif isinstance(obj, (list, tuple)):
			self.visit(node.slice)
			v = node.slice.value
			# If we have a static index, it's not a memory, rather
			# a register chain. We then create the accessed signals on the fly
			if isinstance(v, ast.Num):
				INDEX_FORMAT = "%s[%d]"
				i = self.const_eval(v)
				# self.visit(node.value)
				identifier = node.value.id
				m = self.context
				if identifier in m.memories:
					mem = m.memories[identifier]
					n = mem.depth
					siglist = []
					for j, s in enumerate(node.value.obj):
						sig = self.context.addSignal(None, len(s))
						siglist.append(sig)
						el_id = INDEX_FORMAT % (identifier, j)
						s._name = el_id
						self.dbg(node, REDBG, "REMOVE_MEMORY", \
							"%s not a memory, convert to array" % identifier)
						m.arrays[el_id] = sig

					m.memories.pop(identifier) # Remove from memories

				el_id = INDEX_FORMAT % (identifier, i)
				# Hack: Stick subscript identifier into Subscript node
				node.id = el_id
				node.obj = obj[i]  # Stick current indexed object into node
				sig = m.arrays[el_id]
				sm = SynthesisMapper(SM_WIRE)
				sm.q = sig
				node.syn = sm
			elif isinstance(v.obj, _Signal):
				# Memory parameters:
				node.syn = node.value.syn # Pass on
				node.syn.memid = node.value.id
				node.syn.addrsig = node.slice.value.obj
				self.dbg(node, REDBG, "MEMORY PORT FOR '%s', addr: %s" % (node.value.id, v.obj._name))
			else:
				self.raiseError(node, "Unsupported indexing construct for type %s" % type(v))

		elif isinstance(obj, (_Signal, intbv) ):
			self.accessIndex(node)
		else:
			self.dbg(node, REDBG, "UNHANDLED INDEX", type(v))
			raise Synth_Nosupp("Can't handle this YET")
	

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

		for stmt in node.body:
			self.dbg(stmt, GREEN, "STMT_SIMPLE", stmt)
			self.visit(stmt)
			if isinstance(stmt, ast.If):
				raise AssertionError
			elif isinstance(stmt, ast.Assign):
				lhs = stmt.targets[0]
				if isinstance(lhs, ast.Name):
					pass
				elif isinstance(lhs.obj, _Signal):
					self.handle_toplevel_assignment(stmt)				
			else:
				raise AssertionError

class _ConvertAlwaysDecoVisitor(_ConvertVisitor):
	"""Visitor for @always(sens_signal) type modules"""
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

	def visit_FunctionDef(self, node, *args):
		def handle_dff(m, stmt, clk, clkpol = True):
			clk = m.findWireByName(clk._name)

			for name, sig in stmt.syn.drivers.items():
				gsig = m.findWireByName(name)
				if gsig:
					l = gsig.size()
					self.dbg(node, BLUEBG, "FLIPFLOP_REGISTER", "%s" % name)
					sig_ff = m.addSignal(PID(name + "_ff"), l)
					m.addDff(self.genid(node, name), clk, sig[0], sig_ff, clkpol)
					m.connect(gsig, sig_ff)
				else:
					self.dbg(node, BLUEBG, "FLIPFLOP_VARIABLE", "%s" % name)
					self.variables[name].q = sig[0]

		def handle_comb(m, stmt, clk, clkpol = True):
			for name, sig in stmt.syn.drivers.items():
				gsig = m.findWireByName(name)
				if gsig:
					gsig = m.findWireByName(name)
					m.connect(gsig, sig[0])
				else:
					self.variables[name].q = sig[0]
	
		assert self.tree.senslist
		m = self.context
		self.cur_module = node.name
		senslist = self.tree.senslist
		senslist = self.manageEdges(node.body[-1], senslist)
		singleEdge = (len(senslist) == 1) and isinstance(senslist[0], _WaiterList)
		if singleEdge:
			for i in senslist:
				for j in i:
					print(type(j), dir(j))
			clknode = senslist[0]
			clk = clknode.sig
			if isinstance(clknode, _PosedgeWaiterList):
				clkpol = True
			elif isinstance(clknode, _NegedgeWaiterList):
				clkpol = False
			else:
				self.raiseError(clknode, "Invalid clk type")

			self.dbg(node, VIOBG, "PROCESS", "%s() Single edge:" % self.tree.name + clk._name)
			self.clk = clk
			self.clkpol = clkpol
			# print(clk)
			self.handle_toplevel_process(node, handle_dff, clk, clkpol)
		else:
			self.handle_toplevel_process(node, handle_comb, None)



class _ConvertAlwaysSeqVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)

	def visit_FunctionDef(self, node, *args):
		def handle_dff(m, stmt, reset, clk, clkpol = True):
			# print("Look for clk '%s'" % clk._name)
			clk = m.findWireByName(clk._name)
			for name, sig in stmt.syn.drivers.items():
				gsig = m.findWireByName(name)
				if gsig:
					l = gsig.size()
					self.dbg(node, BLUEBG, "FLIPFLOP_REGISTER", "%s" % name)
					sig_ff = m.addSignal(PID(name + "_ff"), l)
					y = m.addSignal(PID(name + "_rst"), l)
					reset_val = Signal(Const(m.defaults[name], l)) # Value when in reset
					# Create synchronous reset circuit
					rst = m.findWireByName(reset._name)
					if reset.active:
						m.addMux(self.genid(node, name + "_rst"), sig[0], reset_val, rst, y)
					else:
						m.addMux(self.genid(node, name + "_!rst"), reset_val, sig[0], rst, y)

					m.addDff(self.genid(node, name), clk, y, sig_ff, clkpol)

					m.connect(gsig, sig_ff)
				else:
					self.dbg(node, BLUEBG, "FLIPFLOP_RST_VARIABLE", "%s" % name)
					self.variables[name].q = sig[0]

		def handle_adff(m, stmt, reset, clk, clkpol = True):
			clk = m.findWireByName(clk._name)
			for name, sig in stmt.syn.drivers.items():
				gsig = m.findWireByName(name)
				if gsig:
					l = gsig.size()
					sig_ff = m.addSignal(PID(name + "_aff"), l)
					reset_val = Const(m.defaults[name], l) # Value when in reset
					arst = m.findWireByName(reset._name)
					m.addAdff(self.genid(node, name), clk, arst, sig[0], sig_ff, reset_val.get(), \
						clkpol, reset.active)

					m.connect(gsig, sig_ff)
				else:
					self.dbg(node, BLUEBG, "FLIPFLOP_ARST_VARIABLE", "%s" % name)
					self.variables[name].q = sig[0]

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
		self.clk = clk

		if isasync:
			self.handle_toplevel_reset_process(node, handle_adff, reset, clk, clkpol)
		else:
			self.handle_toplevel_reset_process(node, handle_dff, reset, clk, clkpol)

class _ConvertAlwaysCombVisitor(_ConvertVisitor):
	def __init__(self, context, tree):
		_ConvertVisitor.__init__(self, context, tree)
		self.clk = None

	def visit_FunctionDef(self, node):
		self.cur_module = node.name
		# a local function works nicely too
		if self.debug:
			print("Sensitivity list for %s:" % node.name)
			for e in self.tree.senslist:
				print('\t', e)

		m = self.context

		def handle_comb(m, stmt, clk, clkpol = True):
			for name, sig in stmt.syn.drivers.items():
				gsig = m.findWireByName(name)
				if gsig:
					gsig = m.findWireByName(name)
					m.connect(gsig, sig[0])
				else:
					self.variables[name].q = sig[0]


		self.handle_toplevel_process(node, handle_comb, None)

	def visit_If(self, node):
		"always_comb If"
		if node.ignore:
			return

		self.generic_visit(node)

		if hasattr(node, "isFullCase"):
			if node.isFullCase:
				self.mapToPmux(node)
			else:
				self.mapToMux(node)
		else:
			self.dbg(node, VIOBG, "NOTICE", "no fullcase attr in async process")

def _TYPE(x):
	return type(x).__name__
		
import sys
PY2 = sys.version_info[0] == 2

if not PY2:
	from .auxiliaries import dump_hierarchy



def collect_generators(instance, absnames):
	genlist = []
	
	for i in instance.subs:
		if isinstance(i, (_AlwaysComb, _AlwaysSeq, _Always)):
			pass
		else:
			raise TypeError("Unsupported function type")
 
	return genlist


def convert_wires(m, c, a, n):
	if isinstance(a, _Signal):
		try:
			sig = m.findWire(a)
			if not sig:
				raise KeyError("Wire %s not found in signal list" % a._name)
			if a._driven:
				# print("ACTIVE wire %s -> %s" % (a._name, n))
				# port.get().port_output = True
				# s = Signal(port)
				c.setPort(n, sig)
				# m.connect(sig, s)
			elif a._read:
				port = m.addWire(None, len(a))
				# print("PASSIVE wire %s <- %s" % (a._name, n))
				port.get().port_input = True
				s = Signal(port)
				c.setPort(n, s)
				m.connect(s, sig)
			else:
				print("FLOATING wire", a._name)
		except KeyError:
			print("UNDEFINED/UNUSED wire, localname: %s, origin: %s" % (a._name, a._origname))

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
		print("CONST wire")
		print("WARNING: Parameter '%s' handled as constant signal" % n)
		# FIXME:
		# Parameters should only be passed on this way to
		# black box instances
		# c.setParam(n, a)
	elif a == None:
		pass
	elif hasattr(a, '__dict__'):
		print("Resolve class (bus wire)")
		for i in a.__dict__.items():
			convert_wires(m, c, i[1], n + "_" + i[0])
	else:
		raise TypeError("Unsupported wire type for %s: %s" % (n, type(a).__name__))
		
def infer_handle_interface(design, instance, parent_wires):
	blk = instance.obj
	infer_interface(blk)
	# Add module with implementation (not instance) name
	# The name is a unique key mangled from the interface
	key = create_key(blk)
	m = design.addModule(key, instance)

#	for i in siglist:
#		print(i._name)
	# print(blk.argdict)
	argnames = inspect.signature(blk.func).parameters.keys()
	# print("ARGS", blk.args)
	# print("ARGN", argnames)

	impl = blk
	for i, n in enumerate(argnames):
		try:
			a = impl.args[i]
		except IndexError:
			print("ERROR, index out of range")
			print(argnames)
			print(i, impl.args)
			# raise AssertionError

	instance.symdict = parent_wires # XXX
	m.collectWires(instance, argnames)

	return m

def infer_rtl(h, instance, design, module_signals):
	print(BLUEBG + "\tInfer blackbox: '%s'" % instance.name + OFF)
	m = infer_handle_interface(design, instance, module_signals)
	intf = BBInterface("bb_" + instance.name, m)
	instance.obj.infer(m, intf)
	# Connect wires
	impl = instance.obj
	# print(impl.func.__name__)

	# Connect/wire up all interface connections to blackbox:
	intf.wireup()

	# infer_obj.dump()
	m.finish(design) # Hack

def wireup(m, c, inst):
	for n, i in inst.wiring.items():
		print("WIRE", n, i[0], i[1])
		a = i[1]
		sig = m.findWireByName(n)
		if not sig:
			raise ValueError("%s not found" % i[0])
		if a._driven:
			print("ACTIVE wire %s -> %s" % (a._name, n))
			# port.get().port_output = True
			# s = Signal(port)
			c.setPort(n, sig)
			# m.connect(sig, s)
		elif a._read:
			port = m.addWire(None, len(a))
			print("PASSIVE wire %s <- %s" % (a._name, n))
			port.get().port_input = True
			s = Signal(port)
			c.setPort(n, s)
			m.connect(s, sig)

def convert_rtl(h, instance, design, module_signals):
	m = infer_handle_interface(design, instance, module_signals)

	m.collectMemories(instance)

	# Visit generators:
	for tree in instance.genlist:
		print("CONVERT_RTL tree >>>>>> '%s' " % tree.name)
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

	# Create submodule instances as cells:
	print(76 * '=')
	for name, inst in instance.instances:
		key = create_key(inst)
		impl = inst
		infer_interface(impl)
		print("++++++++  %s  ++++++++" % key)

		c = m.addCell(name, key)
		# print(impl.argnames)

		inst_decl = h.instdict[name]
#		wireup(m, c, inst_decl)

		# Grab implementation function argument names
		argnames = inspect.signature(impl.func).parameters.keys()

		for i, n in enumerate(argnames):
			try:
				a = impl.args[i]
			except IndexError:
				print(argnames)
				print(i, impl.args)
				raise AssertionError

			# z = input("--- HIT RETURN")

			convert_wires(m, c, a, n)
	m.finish(design) # Hack
	print("DONE instancing submodules")

def convert_hierarchy(h, func, design, trace = False):

	# print(arglist)

#	genlist = _analyzeGens(arglist, h.absnames)
#
#	print(">>>>>>>>>>>>>>>>>>>")
#	for tree in genlist:
#		print(">>  '%s'" % tree.name)
#		v = _AnnotateTypesVisitor(tree)
#		v.visit(tree)
#	print(">>>>>>>>>>>>>>>>>>>")

	symdict = {}

	for inst in h.hierarchy:
		# print(GREEN + "========================================================" + OFF)
		l = []
		block_instances = []
		for nm, elem in inst.subs:
			if isinstance(elem, (_Block, _BlackBox)):
				block_instances.append((nm, elem))
			else:
				l.append(elem)

		for m in inst.memdict.items():
			print(GREEN + "Memory: %s" % m[0] + OFF)

		inst.instances = block_instances

		# Insert instance id name into hierarchy's instance dict:
		if not inst.name in h.instdict:
			h.instdict[inst.name] = inst
		else:
			print(REDBG + "Instance %s not found" % inst.name + OFF)

		inst.genlist = _analyzeGens(inst, l, h.absnames)
		inst.analyze_signals(symdict)


#	print("##########################")
#	for n, s in symdict.items():
#		print("MODULE signal '%s' : [%d]" % (n, len(s)))
#
#	print("##########################")

	for inst in h.hierarchy:
		print(GREEN + "========================================================" + OFF)
		print(GREEN + "CREATE Module: '%s'" % inst.name + OFF)

		if not inst.cell:
			infer_obj = inst.obj
			fn = infer_obj.func
			if isinstance(infer_obj, _BlackBox):
				infer_rtl(h, inst, design, symdict)
			else:
				convert_rtl(h, inst, design, symdict)

	top = h.hierarchy[0]

	write_tb = True

	if write_tb:
		tbname = top.name
		tbfile = open("tb_%s_mapped.v" % tbname, 'w')
		top.obj.name = tbname # Hack to overwrite DUT name
		_writeTestBench(tbfile, top.obj, trace, "1ps/1ps")
		tbfile.close()

	return top

class YosysModuleConvertor:
	def __init__(self):
		self.name = None
		self.design = None
		self.trace = False

	def __call__(self, blkfunc, *args, **kwargs):

		if self.name is None:
			name = blkfunc.func.__name__
		else:
			name = str(self.name)

		h = Hierarchy(name, blkfunc)

		_genUniqueSuffix.reset()
		_enumTypeSet.clear()
		_slice_constDict.clear()
		# _enumPortTypeSet = set()

		infer_interface(blkfunc)
		# dump_hierarchy(h, blkfunc)
		top = convert_hierarchy(h, blkfunc, self.design, self.trace)
		self.design.set_top_module(top)


toYosysModule = YosysModuleConvertor()