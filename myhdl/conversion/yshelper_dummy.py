# Yosys synthesis interface helper
#
# (c) 2020 section5.ch
#
import inspect

class Synth_Nosupp(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

def ID(x):
	return None

def PID(x):
	return None

def lineno():
	return 0


class SynthesisMapper:
	def __init__(self, el_type):
		self.el_type = el_type
		self.q = None
		self.is_signed = False

def NEW_ID(name, node, ext):
	return None

def OBJ_ID(name, src, ext):
	return None

def Signal(x):
	return None

def ConstSignal(x, l):
	c = Const(x, l)
	return None

def SigBit(x):
	return None


class Design:
	"Simple design wrapper"
	def __init__(self, name="top"):
		raise AssertionError("Yosys module not present")

class Module:
	"Yosys module wrapper"
	def __init__(self, m):
		self.module = m
		self.wires = {}
		self.variables = {}
		self.guard = {}
	
class VisitorHelper:
	"""Visitor helper class for yosys interfacing
Used for separation of common functionality of visitor classes"""
	def __init__(self):
		pass
