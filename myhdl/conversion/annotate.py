"""Temporary auxiliary module for debugging purposes. Volatile."""

import ast
from myhdl.conversion._misc import _ConversionMixin

WARN = "\033[7;31m"
MARK = "\033[7;33m"
ANNOTATE = "\033[7;30m"
OFF = "\033[0m"

class _AnnotateTypesVisitor(ast.NodeVisitor, _ConversionMixin):

	def __init__(self, tree):
		self.tree = tree
		self.depth = 0

	def generic_visit(self, node):
		self.dbg(node, ANNOTATE, "ANNOTATE", type(node).__name__)
		self.depth += 1
		ast.NodeVisitor.generic_visit(self, node)
		self.depth -= 1

	def dbg(self, node, kind, msg = "ANNOTATE", details = "MARK"):
		lineno = self.getLineNo(node)
		lineno += self.tree.lineoffset
		tab = self.depth * "  "
		print("%s: %s:%d %s" % (kind + msg + OFF, self.tree.sourcefile, lineno, tab + details))

	def visit_FunctionDef(self, node):
		# don't visit arguments and decorators
		for stmt in node.body:
			self.visit(stmt)

	def visit_Attribute(self, node):
		self.generic_visit(node)

	def visit_Assert(self, node):
		self.visit(node.test)
		# node.test.vhd = vhd_boolean()

	def visit_AugAssign(self, node):
		self.visit(node.target)
		self.visit(node.value)

	def visit_Assign(self, node):
		lhs = node.targets[0]
		rhs = node.value

		self.visit(lhs)
		self.visit(rhs)

#		if self.state == S_COLLECT:
#			self.cases.append

	def visit_Call(self, node):
		fn = node.func
		# assert isinstance(fn, astNode.Name)
		if hasattr(node, 'tree'):
			v = _AnnotateTypesVisitor(node.tree)
			v.visit(node.tree)

	def visit_Compare(self, node):
		self.generic_visit(node)

	def visit_Str(self, node):
		sm = SynthesisMapper(SM_STRING)
		sm.q = Const(node.value)
		node.syn = sm

	def visit_For(self, node):
		var = node.target.id
		# make it possible to detect loop variable
		self.tree.vardict[var] = _loopInt(-1)
		self.generic_visit(node)

	def visit_Eq(self, node):
		self.generic_visit(node)

	def visit_Store(self, node):
		self.generic_visit(node)

	def visit_NameConstant(self, node):
		pass

	def visit_Name(self, node):
		self.dbg(node, ANNOTATE, "ANNOTATE", "--- Name: %s" % node.id)

	def visit_Num(self, node):
		pass

	def visit_BinOp(self, node):
		self.visit(node.left)
		self.visit(node.right)
		self.generic_visit(node)

	def inferShiftType(self, node):
		pass

	def inferBitOpType(self, node):
		pass

	def inferBinOpType(self, node):
		pass

	def visit_BoolOp(self, node):
		self.generic_visit(node)

	def visit_If(self, node):
		# self.generic_visit(node)
		if hasattr(node, "isFullCase"):
			if node.isFullCase:
				print("\t" + MARK + "switch(%s)" % node.tests[0][0].case[0].id)
				for i, test in enumerate(node.tests):
					print("\t\t" + MARK + "case" + OFF, "", test[1])
			else:
				for i, test in enumerate(node.tests):
					print("\t" + MARK + "if" + OFF, test[0], test[1])
		else:
			print("\t" + WARN + "if" + OFF, test[0].case[0].id, test[1])

	def visit_IfExp(self, node):
		self.generic_visit(node)

	def visit_ListComp(self, node):
		pass  # do nothing

	def visit_Subscript(self, node):
		pass

	def accessSlice(self, node):
		self.generic_visit(node)

	def accessIndex(self, node):
		self.generic_visit(node)

	def visit_UnaryOp(self, node):
		self.visit(node.operand)

	def visit_While(self, node):
		self.generic_visit(node)

