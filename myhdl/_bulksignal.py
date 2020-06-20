mangle = lambda p, a : "%s_%s" % (p, a)

class _BulkSignalBase:
	"""Preliminary bulk signal type
Inside the blackbox environment, this is a non-nestable container
for unidirectional signals. The direction is defined by the (possibly static) _otype
attribute in the class definition.

Details:

By default, MyHDL puts signals in the `sigdict` of an instance object only when 
they are used. In some cases however, it is required to have a fixed set of
signals, for example for a predefined black box interface.

When a BulkSignal is found as argument, it is therefore always completely
expanded. However, it is except from analysis, therefore it must be treated
separately.

When parts of it are used by third party logik, members of a bulk signal
appear in the signal list.

"""

	def __init__(self, name = "", is_out = False):
		self._name = name
		self._otype = is_out
		for member in self.__slots__:
			s = getattr(self, member)
			n = mangle(self._name, member)
			s._name = n
			s._id = n

	def members(self):
		"Returns members"
		return ( (i, getattr(self, i)) for i in self.__slots__ )

	def expand(self, argdict, argnames):
		"Function to expand bulk signal to argument specs"
		for n, i in self.members():
			name = mangle(self._name, n)
			argdict[name] = i
			argnames.append(name)

	def collect(self, module, public = True):
		print("============ BULK COLLECT <%s> for %s ============" % (self._name, module.name))
		if self._otype:
			otype = self._otype
			impl = module.implementation
		else:
			otype = None
			impl = None
		for n, s in self.members():
			# Set origin and driver explicitely
#			if self.blackbox:
#				s._driven = otype
			if not otype:
				s.read = True
			s._source = impl
			module.iomap_set_output(s._id, s, otype)
			# First look up in module if signal was already instanced:
			if not s._id in module.wireid:
				module.collectArg(s._id, s, public, True)
			else:
				print("Member %s already instanced" % s._id)

	def convert_wires(self):
		raise SystemError("You must implement this function in your derived class")
			
BulkSignalBase = _BulkSignalBase
